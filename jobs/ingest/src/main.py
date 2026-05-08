"""
Ingestion Job entry point.

Reads Takeout Archive ZIPs from the configured Google Drive folder,
extracts photos via byte-range requests, generates Preview Images,
and writes Previews + Originals to GCS and metadata to Firestore.
Videos are uploaded to YouTube as private and stored by youtube_video_id.
"""
import os
import logging
import tempfile
from io import BytesIO

import requests
from PIL import Image
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage, firestore
from googleapiclient.discovery import build

from .drive_zip_streamer import DriveZipStreamer
from .image_processor import process as generate_preview
from .sidecar_parser import parse as parse_sidecar
from .photo_index_repository import PhotoIndexRepository, PhotoDoc
from .youtube_uploader import YouTubeUploader, SecretManagerAuth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
PREVIEWS_BUCKET = os.environ["PREVIEWS_BUCKET"]
ORIGINALS_BUCKET = os.environ["ORIGINALS_BUCKET"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
YOUTUBE_REFRESH_TOKEN_SECRET = os.environ["YOUTUBE_REFRESH_TOKEN_SECRET"]


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

    uploader = YouTubeUploader(SecretManagerAuth(
        secret_name=YOUTUBE_REFRESH_TOKEN_SECRET,
        project_id=PROJECT_ID,
    ))

    # List all ZIP files in the Drive folder
    results = drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name contains '.zip' and trashed=false",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    zip_files = results.get("files", [])
    log.info("Found %d Takeout Archive(s) to process", len(zip_files))

    auth_session = requests.Session()
    auth_session.headers["Authorization"] = f"Bearer {credentials.token}"

    sidecars: dict[str, bytes] = {}

    for zip_file in zip_files:
        file_id = zip_file["id"]
        file_name = zip_file["name"]
        log.info("Processing archive: %s (%s)", file_name, file_id)

        streamer = DriveZipStreamer(http_client=auth_session, file_id=file_id)

        # First pass: collect sidecars
        for entry in streamer.list_entries():
            if entry.is_sidecar:
                sidecars[entry.name] = entry.read()

        # Second pass: process images and videos
        for entry in streamer.list_entries():
            if not entry.is_image and not entry.is_video:
                continue

            # Match sidecar by filename prefix: photo.jpg -> photo.jpg.json or photo.jpg(1).json
            image_filename = entry.name.split("/")[-1]
            sidecar_bytes = next(
                (data for path, data in sidecars.items()
                 if path.split("/")[-1].startswith(image_filename) and path.endswith(".json")),
                None,
            )
            if sidecar_bytes is None:
                log.warning("No sidecar for %s — skipping", entry.name)
                continue

            try:
                metadata = parse_sidecar(sidecar_bytes)
            except ValueError as e:
                log.warning("Sidecar parse error for %s: %s — skipping", entry.name, e)
                continue

            if repo.exists(metadata.google_photos_id):
                log.debug("Already indexed: %s — skipping", metadata.google_photos_id)
                continue

            raw_bytes = entry.read()
            filename = entry.name.split("/")[-1]
            base_name = metadata.google_photos_id

            original_path = f"{base_name}_{filename}"
            if entry.is_video:
                suffix = os.path.splitext(filename)[1] or ".mp4"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = tmp.name
                try:
                    video_id = uploader.upload(tmp_path, taken_at=metadata.taken_at)
                finally:
                    os.unlink(tmp_path)
                repo.upsert(PhotoDoc(
                    google_photos_id=metadata.google_photos_id,
                    filename=filename,
                    taken_at=metadata.taken_at,
                    youtube_video_id=video_id,
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
                img = Image.open(BytesIO(preview_bytes))
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

        drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        log.info("Deleted archive from Drive: %s", file_name)

    log.info("Ingestion complete.")


if __name__ == "__main__":
    run()
