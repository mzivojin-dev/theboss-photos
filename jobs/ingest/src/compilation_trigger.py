"""
Starts the Compilation Job (and the photo grouping job) once an ingestion run has indexed new media, so trips get their
Compilations without anyone pressing a button. One start per run, however much was indexed.
"""
import logging
import threading
from typing import Callable, Optional, TypeVar

from .index_outcome import IndexResult, Outcome

log = logging.getLogger(__name__)

RUN_JOB_URL = "https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"

M = TypeVar("M")
D = TypeVar("D")


class CloudRunJob:
    """A Cloud Run Job started through the Cloud Run Admin API (jobs.run)."""

    def __init__(self, session, project: str, region: str, name: str):
        self._session = session  # an authorized requests session
        self._url = RUN_JOB_URL.format(project=project, region=region, job=name)
        self.name = name

    def start(self) -> None:
        response = self._session.post(self._url, json={}, timeout=60)
        response.raise_for_status()


def start_all(starts: list[Callable[[], None]]) -> Callable[[], None]:
    """Starts every job even if one fails to start, then raises the first failure."""
    def start() -> None:
        failures = []
        for start_job in starts:
            try:
                start_job()
            except Exception as err:
                failures.append(err)
        if failures:
            raise failures[0]
    return start


class CompilationTrigger:
    def __init__(self, start_compilation_job: Optional[Callable[[], None]]):
        self._start = start_compilation_job
        self._indexed = 0
        self._lock = threading.Lock()

    def counting(self, index_media: Callable[[M, D], IndexResult]) -> Callable[[M, D], IndexResult]:
        """Wraps the indexer to count what it indexes. Media is indexed on a thread pool."""
        def index_and_count(media: M, metadata: D) -> IndexResult:
            result = index_media(media, metadata)
            if result.outcome is Outcome.INDEXED:
                with self._lock:
                    self._indexed += 1
            return result
        return index_and_count

    def after_run(self) -> None:
        """Start the Compilation Job if this run indexed anything. A failure to start it is logged,
        not raised: the media is indexed either way, and the next run starts it again."""
        if self._start is None:
            log.info("No Compilation Job configured; not starting one")
            return
        if self._indexed == 0:
            log.info("Nothing new was indexed; not starting the Compilation Job")
            return
        try:
            self._start()
        except Exception:
            log.exception("Could not start the Compilation Job")
        else:
            log.info("Started the Compilation Job for %d newly indexed file(s)", self._indexed)
