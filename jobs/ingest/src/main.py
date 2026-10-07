"""
Ingestion Job entry point.

Reads Takeout Archive ZIPs from the configured Google Drive folder,
extracts photos via byte-range requests, generates Preview Images,
and writes Previews + Originals to GCS and metadata to Firestore.
"""
import os
import logging
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urlparse

from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession, Request as GoogleAuthRequest
from google.cloud import storage, firestore
from googleapiclient.discovery import build

from .drive_zip_streamer import DriveZipStreamer, ZipEntry
from .image_processor import process as generate_preview
from .sidecar_parser import PhotoMetadata
from .photo_index_repository import PhotoIndexRepository, PhotoDoc
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
    repo = PhotoIndexRepository(db=db)

    previews_bucket = gcs.bucket(PREVIEWS_BUCKET)
    originals_bucket = gcs.bucket(ORIGINALS_BUCKET)

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

    def index_media(entry: ZipEntry, metadata: PhotoMetadata) -> None:
        if repo.exists(metadata.google_photos_id):
            log.debug("Already indexed: %s — skipping", metadata.google_photos_id)
            return

        raw_bytes = entry.read()
        filename = entry.name.split("/")[-1]
        base_name = metadata.google_photos_id

        # Upload Original
        original_path = f"{base_name}_{filename}"
        if entry.is_video:
            content_type = "video/mp4" if filename.lower().endswith(".mp4") else "video/quicktime"
            originals_bucket.blob(original_path).upload_from_string(raw_bytes, content_type=content_type)
            repo.upsert(PhotoDoc(
                google_photos_id=metadata.google_photos_id,
                filename=filename,
                taken_at=metadata.taken_at,
                original_gcs_path=original_path,
                latitude=metadata.latitude,
                longitude=metadata.longitude,
                media_type="video",
            ))
        else:
            # Generate and upload Preview
            preview_bytes = generate_preview(raw_bytes)
            preview_path = f"{base_name}.webp"
            previews_bucket.blob(preview_path).upload_from_string(
                preview_bytes, content_type="image/webp"
            )
            originals_bucket.blob(original_path).upload_from_string(
                raw_bytes, content_type="image/jpeg"
            )
            from PIL import Image
            from io import BytesIO as _BytesIO
            img = Image.open(_BytesIO(preview_bytes))
            width, height = img.size
            repo.upsert(PhotoDoc(
                google_photos_id=metadata.google_photos_id,
                filename=filename,
                taken_at=metadata.taken_at,
                original_gcs_path=original_path,
                latitude=metadata.latitude,
                longitude=metadata.longitude,
                media_type="photo",
                preview_gcs_path=preview_path,
                width=width,
                height=height,
            ))

        log.info("Indexed: %s", filename)

    def archive_fully_ingested(archive: TakeoutArchive) -> None:
        if DELETE_PROCESSED_DRIVE_FILES:
            drive.files().delete(fileId=archive.file_id, supportsAllDrives=True).execute()
            log.info("Deleted archive from Drive: %s", archive.name)
        else:
            log.info("Leaving processed archive in Drive: %s", archive.name)

    archives = [
        TakeoutArchive(
            file_id=zip_file["id"],
            name=zip_file["name"],
            streamer=DriveZipStreamer(http_client=auth_session, file_id=zip_file["id"]),
        )
        for zip_file in zip_files
    ]
    ingest_archives(archives, index_media, archive_fully_ingested)

    log.info("Ingestion complete.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--server"]:
        serve()
    elif sys.argv[1:]:
        raise SystemExit("Usage: python -m src.main [--server]")
    else:
        run()
