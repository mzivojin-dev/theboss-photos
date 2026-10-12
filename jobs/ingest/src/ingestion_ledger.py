"""
The Ingestion Ledger: what ingestion could not index (`takeout_problems`) and what each Takeout export
covered (`takeout_exports`). The app reads it to decide which days are safe to delete from Google Photos.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol

# takeout-20261005T232735Z-1-003.zip -> 20261005T232735Z
_EXPORT_ID = re.compile(r"^takeout-(\d{8}T\d{6}Z)\b", re.IGNORECASE)
_EXPORT_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
_PHOTOS_YEAR_FOLDER = re.compile(r"^Takeout/Google Photos/Photos from (\d{4})/")

UNKNOWN_EXPORT = "unknown"


@dataclass(frozen=True)
class Problem:
    export: str
    archive: str
    path: str  # the media file's path inside the ZIP
    kind: str  # "failed" | "no_sidecar" | "bad_sidecar"
    reason: str
    taken_at: Optional[datetime] = None  # known only when the Sidecar was read


class IngestionLedger(Protocol):
    def unresolved(self) -> set[tuple[str, str]]:
        """(export, path) of every problem not resolved yet."""
        ...

    def record_problem(self, problem: Problem) -> None: ...

    def resolve(self, export: str, path: str) -> None: ...

    def record_export(self, export: str, exported_at: Optional[datetime], archives: Iterable[str],
                      years: Iterable[int]) -> None:
        """Merges into the export's document: the union of archives and years, never an overwrite."""
        ...


def export_of(archive_name: str) -> str:
    match = _EXPORT_ID.match(archive_name)
    return match.group(1).upper() if match else UNKNOWN_EXPORT


def exported_at(export: str) -> Optional[datetime]:
    try:
        return datetime.strptime(export, _EXPORT_TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def year_of(entry_name: str) -> Optional[int]:
    """The year of a `Photos from YYYY` folder an entry sits in. A year folder is all-or-nothing in
    Takeout, so seeing one means that whole year was exported."""
    match = _PHOTOS_YEAR_FOLDER.match(entry_name)
    return int(match.group(1)) if match else None


def problem_id(export: str, path: str) -> str:
    # Firestore document ids can't contain "/".
    return f"{export}__{path.replace('/', '__')}"


class FirestoreIngestionLedger:
    PROBLEMS = "takeout_problems"
    EXPORTS = "takeout_exports"

    def __init__(self, db):
        self._db = db

    def unresolved(self) -> set[tuple[str, str]]:
        docs = self._db.collection(self.PROBLEMS).where("resolved_at", "==", None).stream()
        return {(doc.get("export"), doc.get("path")) for doc in docs}

    def record_problem(self, problem: Problem) -> None:
        ref = self._db.collection(self.PROBLEMS).document(problem_id(problem.export, problem.path))
        data = {
            "export": problem.export,
            "archive": problem.archive,
            "path": problem.path,
            "kind": problem.kind,
            "reason": problem.reason,
            "taken_at": problem.taken_at,
            "resolved_at": None,
        }
        if ref.get().exists:
            ref.update(data)  # keeps first_seen_at
        else:
            ref.set({**data, "first_seen_at": datetime.now(timezone.utc)})

    def resolve(self, export: str, path: str) -> None:
        self._db.collection(self.PROBLEMS).document(problem_id(export, path)).update(
            {"resolved_at": datetime.now(timezone.utc)}
        )

    def record_export(self, export: str, exported_at: Optional[datetime], archives: Iterable[str],
                      years: Iterable[int]) -> None:
        from google.cloud.firestore import ArrayUnion  # only the Firestore adapter needs the client library
        data = {"archives": ArrayUnion(sorted(archives)), "years": ArrayUnion(sorted(years))}
        if exported_at is not None:
            data["exported_at"] = exported_at
        self._db.collection(self.EXPORTS).document(export).set(data, merge=True)
