"""
Tests for compilation_trigger: the Compilation Job is started once after a run that indexed media.
"""
import pytest

from src.compilation_trigger import CloudRunJob, CompilationTrigger
from src.index_outcome import IndexResult, Outcome


class Starts:
    def __init__(self, fail_with: Exception | None = None):
        self.count = 0
        self._fail_with = fail_with

    def __call__(self) -> None:
        self.count += 1
        if self._fail_with is not None:
            raise self._fail_with


def _run(trigger: CompilationTrigger, outcomes: list[Outcome]) -> None:
    index_media = trigger.counting(lambda media, metadata: IndexResult(outcomes.pop(0)))
    for _ in range(len(outcomes)):
        index_media("media", "metadata")
    trigger.after_run()


def test_the_compilation_job_is_started_once_after_a_run_that_indexed_media():
    starts = Starts()

    _run(CompilationTrigger(starts), [Outcome.INDEXED, Outcome.ALREADY_INDEXED, Outcome.INDEXED])

    assert starts.count == 1


@pytest.mark.parametrize("outcomes", [[], [Outcome.ALREADY_INDEXED], [Outcome.FAILED, Outcome.ALREADY_INDEXED]])
def test_the_compilation_job_is_not_started_when_nothing_new_was_indexed(outcomes):
    starts = Starts()

    _run(CompilationTrigger(starts), outcomes)

    assert starts.count == 0


def test_no_compilation_job_configured_is_not_an_error():
    _run(CompilationTrigger(None), [Outcome.INDEXED])


def test_a_failure_to_start_the_compilation_job_does_not_fail_the_run(caplog):
    starts = Starts(fail_with=OSError("403 Forbidden"))

    _run(CompilationTrigger(starts), [Outcome.INDEXED])

    assert starts.count == 1
    assert "Could not start the Compilation Job" in caplog.text


def test_the_cloud_run_job_is_started_through_the_admin_api():
    class Session:
        def post(self, url, json, timeout):
            self.call = (url, json)

            class Response:
                def raise_for_status(self):
                    pass
            return Response()

    session = Session()

    CloudRunJob(session, "photolib-405112", "us-central1", "theboss-photos-compile").start()

    assert session.call == (
        "https://run.googleapis.com/v2/projects/photolib-405112/locations/us-central1/jobs/theboss-photos-compile:run",
        {},
    )
