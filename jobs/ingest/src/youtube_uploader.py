import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import google.oauth2.credentials
from google.cloud import secretmanager
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle


_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
           "https://www.googleapis.com/auth/youtube"]


@dataclass
class LocalTokenAuth:
    token_path: str
    client_id: str
    client_secret: str


@dataclass
class SecretManagerAuth:
    secret_name: str
    project_id: str


def build_youtube_client(credentials):
    return build("youtube", "v3", credentials=credentials)


def _local_credentials(auth: LocalTokenAuth):
    creds = None
    if os.path.exists(auth.token_path):
        with open(auth.token_path, "rb") as f:
            creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": auth.client_id,
                    "client_secret": auth.client_secret,
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=_SCOPES,
        )
        creds = flow.run_local_server(port=0)
        with open(auth.token_path, "wb") as f:
            pickle.dump(creds, f)
    return creds


def _secret_manager_credentials(auth: SecretManagerAuth):
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{auth.project_id}/secrets/{auth.secret_name}/versions/latest"
    response = client.access_secret_version(name=secret_path)
    refresh_token = response.payload.data.decode("utf-8").strip()
    return google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=_SCOPES,
    )


class YouTubeUploader:
    def __init__(self, auth: LocalTokenAuth | SecretManagerAuth):
        if isinstance(auth, LocalTokenAuth):
            creds = _local_credentials(auth)
        else:
            creds = _secret_manager_credentials(auth)
        self._youtube = build_youtube_client(creds)
        self._playlist_cache: dict[str, str] = {}

    def _get_or_create_playlist(self, title: str) -> str:
        if title in self._playlist_cache:
            return self._playlist_cache[title]

        response = (
            self._youtube.playlists()
            .list(part="snippet", mine=True, maxResults=50)
            .execute()
        )
        for item in response.get("items", []):
            if item["snippet"]["title"] == title:
                playlist_id = item["id"]
                self._playlist_cache[title] = playlist_id
                return playlist_id

        new_playlist = (
            self._youtube.playlists()
            .insert(
                part="snippet,status",
                body={
                    "snippet": {"title": title},
                    "status": {"privacyStatus": "private"},
                },
            )
            .execute()
        )
        playlist_id = new_playlist["id"]
        self._playlist_cache[title] = playlist_id
        return playlist_id

    def upload(self, file_path: str, taken_at: datetime) -> str:
        playlist_title = taken_at.strftime("%Y-%m")
        playlist_id = self._get_or_create_playlist(playlist_title)

        media = MediaFileUpload(file_path, resumable=True)
        request = self._youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": os.path.basename(file_path)},
                "status": {"privacyStatus": "private"},
            },
            media_body=media,
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response["id"]

        self._youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()

        return video_id
