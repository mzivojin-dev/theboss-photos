import json
import os
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_STATE_DIR = Path.home() / ".theboss-ingest"
_STATE_FILE = "state.json"


class ResumeState:
    def __init__(self, state_dir: str | None = None):
        if state_dir is not None:
            self._dir = Path(state_dir)
        else:
            env = os.environ.get("LOCAL_STATE_DIR")
            self._dir = Path(env) if env else _DEFAULT_STATE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / _STATE_FILE
        self._state: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def is_done(self, url: str) -> bool:
        return self._state.get(url, {}).get("status") == "completed"

    def mark_done(self, url: str) -> None:
        self._state[url] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._save()
