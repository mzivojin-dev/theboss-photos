import json
import os
import pytest
from src.resume_state import ResumeState


def test_is_done_returns_false_for_unknown_url(tmp_path):
    state = ResumeState(state_dir=str(tmp_path))
    assert state.is_done("https://takeout.google.com/download/abc") is False


def test_mark_done_then_is_done_returns_true(tmp_path):
    url = "https://takeout.google.com/download/abc"
    state = ResumeState(state_dir=str(tmp_path))
    state.mark_done(url)
    assert state.is_done(url) is True


def test_state_persists_across_instances(tmp_path):
    url = "https://takeout.google.com/download/abc"
    ResumeState(state_dir=str(tmp_path)).mark_done(url)
    assert ResumeState(state_dir=str(tmp_path)).is_done(url) is True


def test_state_dir_created_automatically(tmp_path):
    state_dir = str(tmp_path / "nested" / "state")
    ResumeState(state_dir=state_dir).mark_done("https://example.com/x")
    assert os.path.isdir(state_dir)


def test_local_state_dir_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_STATE_DIR", str(tmp_path))
    url = "https://takeout.google.com/download/abc"
    ResumeState().mark_done(url)
    assert ResumeState().is_done(url) is True


def test_multiple_urls_tracked_independently(tmp_path):
    url_a = "https://takeout.google.com/download/a"
    url_b = "https://takeout.google.com/download/b"
    state = ResumeState(state_dir=str(tmp_path))
    state.mark_done(url_a)
    assert state.is_done(url_a) is True
    assert state.is_done(url_b) is False


def test_state_file_format(tmp_path):
    url = "https://takeout.google.com/download/abc"
    ResumeState(state_dir=str(tmp_path)).mark_done(url)
    data = json.loads((tmp_path / "state.json").read_text())
    assert data[url]["status"] == "completed"
    assert "completed_at" in data[url]
