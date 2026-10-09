"""
Ingestion Job entry point.

Reads Takeout Archive ZIPs from the configured Google Drive folder,
extracts photos via byte-range requests, generates Preview Images,
and writes Previews + Originals to GCS and metadata to Firestore.
When configured, it also stages new media and starts the Compilation Job.
"""
import os
import logging
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession, Request as GoogleAuthRequest
from google.cloud import storage, firestore
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .compilation_trigger import CloudRunJob, CompilationTrigger, start_all
from .drive_zip_streamer import DriveZipStreamer
from .gcs_blob_store import GcsBlobStore
from .media_indexer import MediaIndexer
from .photo_index_repository import PhotoIndexRepository
from .takeout_ingestion import TakeoutArchive, ingest_archives

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INGEST_SERVER_PORT = int(os.environ.get("INGEST_SERVER_PORT", "8080"))
_delete_archives_setting = os.environ.get("DELETE_PROCESSED_DRIVE_FILES", "true").lower()
if _delete_archives_setting not in {"true", "false"}:
    raise ValueError("DELETE_PROCESSED_DRIVE_FILES must be 'true' or 'false'")
DELETE_PROCESSED_DRIVE_FILES = _delete_archives_setting == "true"

_state_lock = threading.Lock()
_state: dict[str, str | None] = {
    "status": "IDLE",
    "startedAt": None,
    "completedAt": None,
    "error": None,
}

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
PREVIEWS_BUCKET = os.environ["PREVIEWS_BUCKET"]
ORIGINALS_BUCKET = os.environ["ORIGINALS_BUCKET"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
# Optional: stage new media for the Compilation Job, and start that job after a run.
STAGING_BUCKET = os.environ.get("STAGING_BUCKET")
COMPILE_JOB_NAME = os.environ.get("COMPILE_JOB_NAME")
# Optional: the job that groups similar photos behind a cover; started alongside the Compilation Job.
GROUP_JOB_NAME = os.environ.get("GROUP_JOB_NAME")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")


def _run_ingestion() -> None:
    try:
        run()
    except Exception as error:
        log.exception("Ingestion failed")
        with _state_lock:
            _state.update(
                status="FAILED",
                completedAt=datetime.now(timezone.utc).isoformat(),
                error=str(error),
            )
    else:
        with _state_lock:
            _state.update(
                status="SUCCEEDED",
                completedAt=datetime.now(timezone.utc).isoformat(),
                error=None,
            )


class _IngestRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict[str, str | None]) -> None:
        encoded_body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded_body)))
        self.end_headers()
        self.wfile.write(encoded_body)

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/status":
            self._send_json(404, {"error": "Not found"})
            return

        with _state_lock:
            state = _state.copy()
        self._send_json(200, state)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/trigger":
            self._send_json(404, {"error": "Not found"})
            return

        with _state_lock:
            if _state["status"] == "RUNNING":
                self._send_json(409, {"error": "Ingestion is already running"})
                return

            _state.update(
                status="RUNNING",
                startedAt=datetime.now(timezone.utc).isoformat(),
                completedAt=None,
                error=None,
            )
            try:
                threading.Thread(target=_run_ingestion, daemon=True).start()
            except RuntimeError as error:
                _state.update(
                    status="FAILED",
                    completedAt=datetime.now(timezone.utc).isoformat(),
                    error=str(error),
                )
                self._send_json(500, {"error": str(error)})
                return

        self._send_json(202, {"status": "RUNNING"})

    def log_message(self, format: str, *args: object) -> None:
        log.info("Ingestion API: " + format, *args)


def serve() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", INGEST_SERVER_PORT), _IngestRequestHandler)
    log.info("Local ingestion API listening on port %d", INGEST_SERVER_PORT)
    server.serve_forever()


def run() -> None:
    credentials, _ = google_auth_default(scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/cloud-platform",
    ])
    credentials.refresh(GoogleAuthRequest())

    drive = build("drive", "v3", credentials=credentials)
    gcs = storage.Client(project=PROJECT_ID)
    db = firestore.Client(project=PROJECT_ID, database="photo-lib")
    indexer = MediaIndexer(
        originals=GcsBlobStore(gcs.bucket(ORIGINALS_BUCKET)),
        previews=GcsBlobStore(gcs.bucket(PREVIEWS_BUCKET)),
        photo_index=PhotoIndexRepository(db=db),
        staging=GcsBlobStore(gcs.bucket(STAGING_BUCKET)) if STAGING_BUCKET else None,
    )

    # List all ZIP files in the Drive folder
    results = drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name contains '.zip' and trashed=false",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    zip_files = results.get("files", [])
    log.info("Found %d Takeout Archive(s) to process", len(zip_files))

    # Refreshes the token on expiry; a run downloading many GB can outlast the one-hour token.
    auth_session = AuthorizedSession(credentials)

    def archive_fully_ingested(archive: TakeoutArchive) -> None:
        if not DELETE_PROCESSED_DRIVE_FILES:
            log.info("Leaving processed archive in Drive: %s", archive.name)
            return
        # Only a file's owner can delete it from a My Drive folder, so the service account is usually
        # refused for ZIPs you uploaded. That must not stop the run: everything in the ZIP is indexed.
        try:
            drive.files().delete(fileId=archive.file_id, supportsAllDrives=True).execute()
        except HttpError as error:
            log.warning("Could not delete %s from Drive (%s); remove it by hand", archive.name, error.status_code)
        else:
            log.info("Deleted archive from Drive: %s", archive.name)

    archives = [
        TakeoutArchive(
            file_id=zip_file["id"],
            name=zip_file["name"],
            streamer=DriveZipStreamer(http_client=auth_session, file_id=zip_file["id"]),
        )
        for zip_file in zip_files
    ]
    job_names = [name for name in (GROUP_JOB_NAME, COMPILE_JOB_NAME) if name]
    compilation = CompilationTrigger(
        start_all([CloudRunJob(auth_session, PROJECT_ID, GCP_REGION, name).start for name in job_names])
        if job_names else None
    )
    ingest_archives(archives, compilation.counting(indexer.index), archive_fully_ingested)
    compilation.after_run()

    log.info("Ingestion complete.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--server"]:
        serve()
    elif sys.argv[1:]:
        raise SystemExit("Usage: python -m src.main [--server]")
    else:
        run()
