"""
Runs ffmpeg and ffprobe.
"""
import json
import subprocess


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{result.stderr[-3000:]}")
    return result.stdout


def duration_of(path: str) -> float:
    return float(json.loads(run(["ffprobe", "-v", "error", "-show_format", "-of", "json", path]))["format"]["duration"])
