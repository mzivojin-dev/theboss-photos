"""
Compilation Job entry point.

Started by the Ingestion Job after a run that indexed new media (or by hand). Reads the Photo
Index, finds trips, and writes a Compilation video per changed trip to the compilations bucket.
With --tasks N, Cloud Run splits the trips across N tasks.
"""
import logging
import os
import sys

import reverse_geocoder
from google.cloud import firestore, storage
from timezonefinder import TimezoneFinder

from .compilation_job import CompilationJob
from .gcp import FirestoreCompilationStore, GcsMediaSource, GcsVideoStore, load_photo_index
from .make_compilation import CompilationMaker
from .trips import localise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REQUIRED = ["GCP_PROJECT_ID", "STAGING_BUCKET", "ORIGINALS_BUCKET", "PREVIEWS_BUCKET", "COMPILATIONS_BUCKET"]
MUSIC = os.environ.get("COMPILATION_MUSIC", "true").lower() == "true"
TASK_INDEX = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
TASK_COUNT = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))


def place_names(points: list[tuple[float, float]]) -> list[str]:
    """Offline: the nearest town of 1000+ people."""
    return [place["name"] for place in reverse_geocoder.search(points, mode=1)]


def run() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        # Fail before any work: with an empty bucket name every trip would fail, some only after rendering.
        log.error("Set %s (see .env.example)", ", ".join(missing))
        return 2
    env = os.environ
    db = firestore.Client(project=env["GCP_PROJECT_ID"], database="photo-lib")
    gcs = storage.Client(project=env["GCP_PROJECT_ID"])

    items = load_photo_index(db)
    log.info("Task %d/%d: %d item(s) in the Photo Index", TASK_INDEX + 1, TASK_COUNT, len(items))
    finder = TimezoneFinder()
    localise(items, lambda lat, lng: finder.timezone_at(lat=lat, lng=lng), place_names)

    job = CompilationJob(
        store=FirestoreCompilationStore(db),
        videos=GcsVideoStore(gcs.bucket(env["COMPILATIONS_BUCKET"])),
        make=CompilationMaker(
            GcsMediaSource(gcs.bucket(env["STAGING_BUCKET"]), gcs.bucket(env["ORIGINALS_BUCKET"]),
                           gcs.bucket(env["PREVIEWS_BUCKET"])),
            music=MUSIC,
        ),
    )
    summary = job.run(items, TASK_INDEX, TASK_COUNT)
    # A failed trip is recorded and retried next run; the exit code makes the failure visible.
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(run())
