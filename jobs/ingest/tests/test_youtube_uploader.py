from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import pytest

from src.youtube_uploader import YouTubeUploader, LocalTokenAuth, SecretManagerAuth


@pytest.fixture()
def mock_youtube():
    return MagicMock()


@pytest.fixture()
def mock_media():
    with patch("src.youtube_uploader.MediaFileUpload") as m:
        yield m


@pytest.fixture()
def uploader(mock_youtube, mock_media):
    auth = LocalTokenAuth(
        token_path="/tmp/token.json",
        client_id="client-id",
        client_secret="client-secret",
    )
    mock_creds = MagicMock()
    with (
        patch("src.youtube_uploader._local_credentials", return_value=mock_creds),
        patch("src.youtube_uploader.build_youtube_client", return_value=mock_youtube),
    ):
        yield YouTubeUploader(auth), mock_youtube


def _taken_at(year=2023, month=7):
    return datetime(year, month, 15, tzinfo=timezone.utc)


def _setup_upload(mock_youtube, video_id="vid123"):
    mock_youtube.videos.return_value.insert.return_value.next_chunk.return_value = (
        None,
        {"id": video_id},
    )


def _setup_no_playlists(mock_youtube):
    mock_youtube.playlists.return_value.list.return_value.execute.return_value = {
        "items": []
    }


def _setup_existing_playlist(mock_youtube, title="2023-07", playlist_id="pl123"):
    mock_youtube.playlists.return_value.list.return_value.execute.return_value = {
        "items": [{"id": playlist_id, "snippet": {"title": title}}]
    }


def _setup_playlist_insert(mock_youtube, playlist_id="pl_new"):
    mock_youtube.playlists.return_value.insert.return_value.execute.return_value = {
        "id": playlist_id
    }


def test_upload_returns_video_id(uploader):
    u, mock_yt = uploader
    _setup_no_playlists(mock_yt)
    _setup_playlist_insert(mock_yt)
    _setup_upload(mock_yt, video_id="abc123")
    result = u.upload("/tmp/video.mp4", _taken_at())
    assert result == "abc123"


def test_new_playlist_created_when_none_exists(uploader):
    u, mock_yt = uploader
    _setup_no_playlists(mock_yt)
    _setup_playlist_insert(mock_yt, playlist_id="new_pl")
    _setup_upload(mock_yt)
    u.upload("/tmp/video.mp4", _taken_at(2023, 7))
    mock_yt.playlists.return_value.insert.assert_called_once()
    insert_call = mock_yt.playlists.return_value.insert.call_args
    body = insert_call[1]["body"]
    assert body["snippet"]["title"] == "2023-07"
    assert body["status"]["privacyStatus"] == "private"


def test_existing_playlist_reused_no_duplicate(uploader):
    u, mock_yt = uploader
    _setup_existing_playlist(mock_yt, title="2023-07", playlist_id="existing_pl")
    _setup_upload(mock_yt)
    u.upload("/tmp/video.mp4", _taken_at(2023, 7))
    mock_yt.playlists.return_value.insert.assert_not_called()


def test_playlist_id_cached_across_uploads(uploader):
    u, mock_yt = uploader
    _setup_existing_playlist(mock_yt, title="2023-07", playlist_id="cached_pl")
    _setup_upload(mock_yt)
    u.upload("/tmp/video.mp4", _taken_at(2023, 7))
    u.upload("/tmp/video2.mp4", _taken_at(2023, 7))
    # playlists.list should only be called once (second call uses cache)
    assert mock_yt.playlists.return_value.list.call_count == 1


def test_video_added_to_playlist(uploader):
    u, mock_yt = uploader
    _setup_existing_playlist(mock_yt, title="2023-07", playlist_id="pl_abc")
    _setup_upload(mock_yt, video_id="vid_xyz")
    u.upload("/tmp/video.mp4", _taken_at(2023, 7))
    mock_yt.playlistItems.return_value.insert.assert_called_once()
    body = mock_yt.playlistItems.return_value.insert.call_args[1]["body"]
    assert body["snippet"]["playlistId"] == "pl_abc"
    assert body["snippet"]["resourceId"]["videoId"] == "vid_xyz"


def test_secret_manager_auth_reads_secret():
    auth = SecretManagerAuth(secret_name="youtube-refresh-token", project_id="my-project")
    mock_sm = MagicMock()
    mock_sm.access_secret_version.return_value.payload.data = b"my-refresh-token"
    mock_creds = MagicMock()
    mock_yt = MagicMock()
    _setup_no_playlists(mock_yt)
    _setup_playlist_insert(mock_yt)
    _setup_upload(mock_yt)
    with (
        patch("src.youtube_uploader._secret_manager_credentials", return_value=mock_creds) as mock_sm_creds,
        patch("src.youtube_uploader.build_youtube_client", return_value=mock_yt),
        patch("src.youtube_uploader.MediaFileUpload"),
    ):
        u = YouTubeUploader(auth)
        u.upload("/tmp/video.mp4", _taken_at())
    mock_sm_creds.assert_called_once_with(auth)
