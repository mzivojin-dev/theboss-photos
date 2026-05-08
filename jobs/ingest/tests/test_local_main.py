"""Tests for local_main — cookie session loading, resume skip, and mark-done."""
import http.cookiejar
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Test 1 — cookie-file loads cookies into session
# ---------------------------------------------------------------------------

def test_cookie_file_loads_cookies_into_session(tmp_path):
    from src.local_main import _make_cookie_session

    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".google.com\tTRUE\t/\tFALSE\t0\tSID\tabc123\n",
        encoding="utf-8",
    )

    session = _make_cookie_session([str(cookie_file)])
    assert session.cookies.get("SID", domain=".google.com") == "abc123"


def test_multiple_cookie_files_are_merged(tmp_path):
    from src.local_main import _make_cookie_session

    file1 = tmp_path / "takeout.txt"
    file1.write_text(
        "# Netscape HTTP Cookie File\n"
        "takeout.google.com\tFALSE\t/\tFALSE\t0\tTAKEOUT_SESSION\ttoken1\n",
        encoding="utf-8",
    )
    file2 = tmp_path / "google.txt"
    file2.write_text(
        "# Netscape HTTP Cookie File\n"
        ".google.com\tTRUE\t/\tFALSE\t0\tSID\tabc123\n",
        encoding="utf-8",
    )

    session = _make_cookie_session([str(file1), str(file2)])
    assert session.cookies.get("SID", domain=".google.com") == "abc123"
    assert session.cookies.get("TAKEOUT_SESSION", domain="takeout.google.com") == "token1"


# ---------------------------------------------------------------------------
# Test 2 — Already-completed URLs are skipped
# ---------------------------------------------------------------------------

def test_completed_url_is_skipped(tmp_path):
    url = "https://takeout.google.com/takeout/download?j=abc&i=0&user=99"

    url_file = tmp_path / "urls.txt"
    url_file.write_text(url + "\n", encoding="utf-8")

    mock_state = MagicMock()
    mock_state.is_done.return_value = True

    mock_download = MagicMock()

    with (
        patch("src.local_main.ResumeState", return_value=mock_state),
        patch("src.local_main._download_zip", mock_download),
        patch("src.local_main._get_firestore_repo", return_value=MagicMock()),
        patch("src.local_main._get_youtube_uploader", return_value=MagicMock()),
    ):
        from src import local_main
        local_main.run(url_file=str(url_file), state_dir=str(tmp_path), temp_dir=str(tmp_path))

    mock_download.assert_not_called()
    mock_state.mark_done.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — mark_done called after successful processing
# ---------------------------------------------------------------------------

def test_mark_done_called_after_zip_processed(tmp_path):
    url = "https://takeout.google.com/takeout/download?j=abc&i=0&user=99"

    url_file = tmp_path / "urls.txt"
    url_file.write_text(url + "\n", encoding="utf-8")

    fake_zip = tmp_path / "takeout.zip"
    fake_zip.write_bytes(b"fake-zip")

    mock_state = MagicMock()
    mock_state.is_done.return_value = False

    with (
        patch("src.local_main.ResumeState", return_value=mock_state),
        patch("src.local_main._download_zip", return_value=str(fake_zip)),
        patch("src.local_main._process_zip", return_value=None),
        patch("src.local_main._get_firestore_repo", return_value=MagicMock()),
        patch("src.local_main._get_youtube_uploader", return_value=MagicMock()),
    ):
        from src import local_main
        local_main.run(url_file=str(url_file), state_dir=str(tmp_path), temp_dir=str(tmp_path))

    mock_state.mark_done.assert_called_once_with(url)


# ---------------------------------------------------------------------------
# Test 4 — --zip-path processes directly, no download or state tracking
# ---------------------------------------------------------------------------

def test_zip_path_processes_directly_without_download(tmp_path):
    fake_zip = tmp_path / "takeout.zip"
    fake_zip.write_bytes(b"fake-zip")

    mock_process = MagicMock()

    with (
        patch("src.local_main._process_zip", mock_process),
        patch("src.local_main._get_firestore_repo", return_value=MagicMock()),
        patch("src.local_main._get_youtube_uploader", return_value=MagicMock()),
    ):
        from src import local_main
        local_main.run(zip_path=str(fake_zip), state_dir=str(tmp_path), temp_dir=str(tmp_path))

    mock_process.assert_called_once()
    assert mock_process.call_args[0][0] == str(fake_zip)
