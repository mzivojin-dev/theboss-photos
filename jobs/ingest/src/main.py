"""
Ingestion Job entry point.

Reads Takeout Archive ZIPs from the configured Google Drive folder,
extracts photos via byte-range requests, generates Preview Images,
and writes Previews + Originals to GCS and metadata to Firestore.
"""
import os
import logging
from io import BytesIO

import requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage, firestore
from googleapiclient.discovery import build

from .drive_zip_streamer import DriveZipStreamer
from .image_processor import process as generate_preview
from .sidecar_parser import parse as parse_sidecar
from .photo_index_repository import PhotoIndexRepository, PhotoDoc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
PREVIEWS_BUCKET = os.environ["PREVIEWS_BUCKET"]
ORIGINALS_BUCKET = os.environ["ORIGINALS_BUCKET"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]


def run() -> None:
    credentials, _ = google_auth_default(scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/cloud-platform",
    ])
    credentials.refresh(GoogleAuthRequest())

    drive = build("drive", "v3", credentials=credentials)
    gcs = storage.Client(project=PROJECT_ID)
    db = firestore.Client(project=PROJECT_ID)
    repo = PhotoIndexRepository(db=db)

    previews_bucket = gcs.bucket(PREVIEWS_BUCKET)
    originals_bucket = gcs.bucket(ORIGINALS_BUCKET)

    # List all ZIP files in the Drive folder
    results = drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/zip' and trashed=false",
        fields="files(id, name)",
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

        # Second pass: process images
        for entry in streamer.list_entries():
            if not entry.is_image:
                continue

            # Match sidecar: photo.jpg -> photo.jpg.json
            sidecar_name = entry.name + ".json"
            sidecar_bytes = sidecars.get(sidecar_name)
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

            # Generate and upload Preview
            preview_bytes = generate_preview(raw_bytes)
            preview_path = f"{base_name}.webp"
            previews_bucket.blob(preview_path).upload_from_string(
                preview_bytes, content_type="image/webp"
            )

            # Upload Original
            original_path = f"{base_name}_{filename}"
            originals_bucket.blob(original_path).upload_from_string(
                raw_bytes, content_type="image/jpeg"
            )

            # Determine dimensions from preview
            from PIL import Image
            from io import BytesIO as _BytesIO
            img = Image.open(_BytesIO(preview_bytes))
            width, height = img.size

            repo.upsert(PhotoDoc(
                google_photos_id=metadata.google_photos_id,
                filename=filename,
                taken_at=metadata.taken_at,
                preview_gcs_path=preview_path,
                original_gcs_path=original_path,
                width=width,
                height=height,
                latitude=metadata.latitude,
                longitude=metadata.longitude,
            ))
            log.info("Indexed: %s", filename)

    log.info("Ingestion complete.")


if __name__ == "__main__":
    run()
