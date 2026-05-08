"""
Local CLI entry point for ingesting Google Takeout ZIPs.

Reads download URLs from a text file (one per line), downloads each ZIP
using an optional authenticated requests session, and runs the full
ingestion pipeline.

Usage:
    python -m src.local_main --url-file takeout_urls.txt [--cookie-file cookies.txt ...]
"""
import argparse
import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(".env.local", usecwd=True, raise_error_if_not_found=False), override=False)

from google.cloud import firestore
from PIL import Image

from .image_processor import process as generate_preview
from .photo_index_repository import PhotoIndexRepository, PhotoDoc
from .resume_state import ResumeState
from .sidecar_parser import parse as parse_sidecar
from .youtube_uploader import YouTubeUploader, LocalTokenAuth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_DEFAULT_TEMP_DIR = os.path.join(tempfile.gettempdir(), "theboss-ingest")
_DEFAULT_STATE_DIR = str(Path.home() / ".theboss-ingest")

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
PREVIEWS_BUCKET = os.environ.get("PREVIEWS_BUCKET", "")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")


def _make_cookie_session(cookie_files: list[str]):
    import http.cookiejar
    import requests

    session = requests.Session()
    for path in cookie_files:
        cj = http.cookiejar.MozillaCookieJar()
        cj.load(path, ignore_discard=True, ignore_expires=True)
        session.cookies.update(cj)
        log.info("Loaded cookies from file: %s", path)
    return session


def _get_firestore_repo() -> PhotoIndexRepository:
    db = firestore.Client(project=GCP_PROJECT_ID, database="photo-lib")
    return PhotoIndexRepository(db=db)


def _get_youtube_uploader(state_dir: str) -> Optional[YouTubeUploader]:
    if not YT_CLIENT_ID or not YT_CLIENT_SECRET:
        log.warning(
            "YT_CLIENT_ID / YT_CLIENT_SECRET not set — videos will be skipped. "
            "Set them in .env.local to enable YouTube upload."
        )
        return None
    token_path = str(Path(state_dir) / "token.json")
    return YouTubeUploader(LocalTokenAuth(
        token_path=token_path,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
    ))


def _download_zip(url: str, dest_dir: str, session) -> str:
    filename = f"takeout-{abs(hash(url))}.zip"
    dest_path = str(Path(dest_dir) / filename)

    log.info("Downloading %s → %s", url, dest_path)
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if "text/html" in content_type:
            preview = r.text[:400]
            hint = (
                "Re-export cookies from google.com (not takeout.google.com) — "
                "auth cookies live on the parent domain."
                if "accounts.google.com" in preview else ""
            )
            raise RuntimeError(
                f"Download returned HTML instead of a ZIP.\n"
                f"{hint}\n"
                f"Content-Type: {content_type}\nResponse preview:\n{preview}"
            )
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    with open(dest_path, "rb") as f:
        magic = f.read(4)
    if magic[:2] != b"PK":
        with open(dest_path, "r", encoding="utf-8", errors="replace") as f:
            preview = f.read(800)
        os.unlink(dest_path)
        raise RuntimeError(
            f"Downloaded file is not a ZIP (got: {magic!r}).\n"
            f"File preview:\n{preview}"
        )

    return dest_path


def _process_zip(
    zip_path: str,
    all_sidecars: dict[str, bytes],
    repo: PhotoIndexRepository,
    uploader: Optional[YouTubeUploader],
) -> None:
    """Two-pass processing: collect sidecars then process media."""
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        # Pass 1 — collect sidecars
        for name in zf.namelist():
            if name.endswith(".json"):
                all_sidecars[name] = zf.read(name)

        # Pass 2 — process media
        for name in zf.namelist():
            basename = name.split("/")[-1]
            is_image = basename.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp"))
            is_video = basename.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))
            if not is_image and not is_video:
                continue

            sidecar_bytes = next(
                (data for path, data in all_sidecars.items()
                 if path.split("/")[-1].startswith(basename) and path.endswith(".json")),
                None,
            )
            if sidecar_bytes is None:
                log.warning("No sidecar for %s — skipping", name)
                continue

            try:
                metadata = parse_sidecar(sidecar_bytes)
            except ValueError as e:
                log.warning("Sidecar parse error for %s: %s — skipping", name, e)
                continue

            if repo.exists(metadata.google_photos_id):
                log.debug("Already indexed: %s — skipping", metadata.google_photos_id)
                continue

            raw_bytes = zf.read(name)

            if is_video:
                if uploader is None:
                    log.warning("Skipping video %s — YouTube credentials not configured.", basename)
                    continue
                suffix = os.path.splitext(basename)[1] or ".mp4"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = tmp.name
                try:
                    video_id = uploader.upload(tmp_path, taken_at=metadata.taken_at)
                finally:
                    os.unlink(tmp_path)
                repo.upsert(PhotoDoc(
                    google_photos_id=metadata.google_photos_id,
                    filename=basename,
                    taken_at=metadata.taken_at,
                    youtube_video_id=video_id,
                    latitude=metadata.latitude,
                    longitude=metadata.longitude,
                    media_type="video",
                ))
            else:
                preview_bytes = generate_preview(raw_bytes)
                preview_path = f"{metadata.google_photos_id}.webp"
                original_path = f"{metadata.google_photos_id}_{basename}"

                from google.cloud import storage
                gcs = storage.Client(project=GCP_PROJECT_ID)
                previews_bucket = gcs.bucket(PREVIEWS_BUCKET)
                previews_bucket.blob(preview_path).upload_from_string(preview_bytes, content_type="image/webp")
                previews_bucket.blob(original_path).upload_from_string(raw_bytes, content_type="image/jpeg")

                img = Image.open(BytesIO(preview_bytes))
                width, height = img.size
                repo.upsert(PhotoDoc(
                    google_photos_id=metadata.google_photos_id,
                    filename=basename,
                    taken_at=metadata.taken_at,
                    preview_gcs_path=preview_path,
                    original_gcs_path=original_path,
                    width=width,
                    height=height,
                    latitude=metadata.latitude,
                    longitude=metadata.longitude,
                    media_type="photo",
                ))

            log.info("Indexed: %s", basename)


def run(
    url_file: Optional[str] = None,
    cookie_files: Optional[list[str]] = None,
    state_dir: Optional[str] = None,
    temp_dir: Optional[str] = None,
    zip_path: Optional[str] = None,
) -> None:
    if url_file is None and zip_path is None:
        parser = argparse.ArgumentParser(
            description="Ingest Google Takeout ZIPs from a URL list file or a pre-downloaded ZIP."
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--url-file", type=str,
                           help="Path to text file with one Takeout download URL per line")
        group.add_argument("--zip-path", type=str,
                           help="Path to a pre-downloaded Takeout ZIP file to ingest directly")
        parser.add_argument("--cookie-file", type=str, action="append", dest="cookie_files",
                            metavar="FILE",
                            help="Netscape cookies.txt for authenticated download (repeat for multiple files)")
        args = parser.parse_args()
        url_file = args.url_file
        zip_path = args.zip_path
        cookie_files = args.cookie_files or []

    if state_dir is None:
        state_dir = os.environ.get("LOCAL_STATE_DIR", _DEFAULT_STATE_DIR)
    if temp_dir is None:
        temp_dir = os.environ.get("LOCAL_TEMP_DIR", _DEFAULT_TEMP_DIR)

    Path(temp_dir).mkdir(parents=True, exist_ok=True)

    repo = _get_firestore_repo()
    uploader = _get_youtube_uploader(state_dir)
    all_sidecars: dict[str, bytes] = {}

    if zip_path:
        log.info("Processing pre-downloaded ZIP: %s", zip_path)
        _process_zip(zip_path, all_sidecars, repo, uploader)
        log.info("Local ingestion complete.")
        return

    urls = [u.strip() for u in Path(url_file).read_text(encoding="utf-8").splitlines() if u.strip()]
    log.info("Loaded %d URL(s) from %s", len(urls), url_file)

    if cookie_files:
        session = _make_cookie_session(cookie_files)
    else:
        import requests
        session = requests.Session()

    state = ResumeState(state_dir=state_dir)

    for url in urls:
        if state.is_done(url):
            log.info("Skipping already-completed: %s", url)
            continue

        try:
            downloaded_path = _download_zip(url, dest_dir=temp_dir, session=session)
        except Exception as e:
            log.error("Download failed for %s: %s", url, e)
            continue

        try:
            _process_zip(downloaded_path, all_sidecars, repo, uploader)
        finally:
            if os.path.exists(downloaded_path):
                os.unlink(downloaded_path)
        state.mark_done(url)
        log.info("Completed: %s", url)

    log.info("Local ingestion complete.")


if __name__ == "__main__":
    run()
