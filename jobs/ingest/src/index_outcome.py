"""
The outcome of indexing one media file. Has no dependencies, so ingestion can use it without the imaging stack.
"""
import enum
from dataclasses import dataclass
from typing import Optional


class Outcome(enum.Enum):
    INDEXED = "indexed"
    ALREADY_INDEXED = "already indexed"
    FAILED = "failed"


@dataclass(frozen=True)
class IndexResult:
    outcome: Outcome
    reason: Optional[str] = None
