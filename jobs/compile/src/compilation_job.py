"""
The Compilation Job's run: find the trips, and make a Compilation for each trip whose media changed
since its last one. The record of each Compilation (status, chapters, video path) lives in the
compilations collection, so re-running is safe:

- A trip another execution is rendering is left to it.
- A failed trip is retried next run, but given up after MAX_ATTEMPTS. An attempt is counted when it
  starts, so a task killed mid-render (out of memory, timeout) counts too, and one trip can't block
  the trips after it forever. New media for the trip resets the count.
- A record whose trip no longer exists (new media moved the trip's first or last day) is marked
  superseded, and its video deleted.
"""
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from .media_item import MediaItem
from .renderer import Rendered
from .trips import Trip, find_trips

log = logging.getLogger(__name__)


# A record still "rendering" after this long belongs to an execution that died (the job times out
# at 6 hours).
RENDER_TIMEOUT = timedelta(hours=6)
MAX_ATTEMPTS = 2


class CompilationStore(Protocol):
    def get(self, trip_id: str) -> Optional[dict]: ...

    def save(self, trip_id: str, fields: dict) -> None: ...

    def all(self) -> dict[str, dict]: ...


class VideoStore(Protocol):
    def upload_file(self, path: str, local_path: str, content_type: str) -> None: ...

    def delete(self, path: str) -> None: ...


@dataclass(frozen=True)
class Made:
    rendered: Rendered
    title: str
    dates: str
    look: str
    clips: int
    photos: int


@dataclass(frozen=True)
class Skipped:
    reason: str


MakeCompilation = Callable[[Trip, str], "Made | Skipped"]


@dataclass
class RunSummary:
    made: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    given_up: list[str] = field(default_factory=list)
    superseded: list[str] = field(default_factory=list)


class CompilationJob:
    def __init__(self, store: CompilationStore, videos: VideoStore, make: MakeCompilation,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._store = store
        self._videos = videos
        self._make = make
        self._now = now

    def run(self, items: list[MediaItem], task_index: int = 0, task_count: int = 1) -> RunSummary:
        """Items must be localised. With several Cloud Run tasks, each takes every task_count-th trip."""
        summary = RunSummary()
        trips = find_trips(items)
        log.info("Found %d trip(s) with video: %s", len(trips), ", ".join(t.id for t in trips) or "none")
        for index, trip in enumerate(trips):
            if index % task_count == task_index:
                self._compile(trip, summary)
        if task_index == 0:
            self._supersede({trip.id for trip in trips}, summary)
        log.info("Compilations: %d made, %d unchanged, %d skipped, %d in progress elsewhere, %d failed, "
                 "%d given up, %d superseded", len(summary.made), len(summary.unchanged), len(summary.skipped),
                 len(summary.in_progress), len(summary.failed), len(summary.given_up), len(summary.superseded))
        if summary.given_up:
            log.warning("Gave up on %s after %d attempts each; new media for a trip retries it",
                        ", ".join(summary.given_up), MAX_ATTEMPTS)
        return summary

    def _compile(self, trip: Trip, summary: RunSummary) -> None:
        existing = self._store.get(trip.id)
        attempts = 0
        if existing and existing.get("membership") == trip.membership:
            status = existing.get("status")
            if status in {"ready", "skipped"}:
                summary.unchanged.append(trip.id)
                return
            if status == "rendering" and self._now() - existing["updated_at"] < RENDER_TIMEOUT:
                summary.in_progress.append(trip.id)
                return
            attempts = existing.get("attempts", 0)
            if attempts >= MAX_ATTEMPTS:
                summary.given_up.append(trip.id)
                return
        record = {
            "first_day": trip.first_day.isoformat(),
            "last_day": trip.last_day.isoformat(),
            "membership": trip.membership,
            "attempts": attempts + 1,
        }
        self._save(trip, record, status="rendering")
        log.info("Making the Compilation for %s: %d clip(s), %d photo(s)", trip.id, len(trip.clips), len(trip.photos))
        try:
            with tempfile.TemporaryDirectory() as workdir:
                outcome = self._make(trip, workdir)
                if isinstance(outcome, Skipped):
                    log.info("Skipped %s: %s", trip.id, outcome.reason)
                    self._save(trip, record, status="skipped", reason=outcome.reason)
                    summary.skipped.append(trip.id)
                    return
                path = f"{trip.id}.mp4"
                self._videos.upload_file(path, outcome.rendered.path, content_type="video/mp4")
        except Exception as error:
            log.exception("Failed to make the Compilation for %s", trip.id)
            self._save(trip, record, status="failed", error=f"{type(error).__name__}: {error}")
            summary.failed.append(trip.id)
            return
        rendered = outcome.rendered
        self._save(trip, record, status="ready", video_gcs_path=path, seconds=round(rendered.seconds, 1),
                   title=outcome.title, dates=outcome.dates, look=outcome.look,
                   clips=outcome.clips, photos=outcome.photos,
                   chapters=[{"start": round(start, 1), "title": title} for start, title in rendered.chapters],
                   music_credits=rendered.music_credits)
        log.info("Compilation ready: %s (%.1f min)", path, rendered.seconds / 60)
        summary.made.append(trip.id)

    def _supersede(self, trip_ids: set[str], summary: RunSummary) -> None:
        for trip_id, record in self._store.all().items():
            if trip_id in trip_ids or record.get("status") == "superseded":
                continue
            if record.get("video_gcs_path"):
                self._videos.delete(record["video_gcs_path"])
            self._store.save(trip_id, {**record, "status": "superseded", "video_gcs_path": None,
                                       "updated_at": self._now()})
            summary.superseded.append(trip_id)

    def _save(self, trip: Trip, record: dict, status: str, **fields) -> None:
        self._store.save(trip.id, {**record, **fields, "status": status, "updated_at": self._now()})
