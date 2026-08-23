"""Private-first YouTube upload and explicit publication."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from app.config import config


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"


class YouTubePublisherError(RuntimeError):
    pass


def _token_file() -> str:
    return os.getenv(
        "YOUTUBE_TOKEN_FILE",
        str(config.app.get("youtube_token_file", "") or ""),
    ).strip()


def is_configured() -> bool:
    token_file = _token_file()
    return bool(token_file and Path(token_file).is_file())


def _client():
    token_file = _token_file()
    if not token_file:
        raise YouTubePublisherError("youtube_token_file is not configured")
    if not Path(token_file).is_file():
        raise YouTubePublisherError(f"YouTube token file does not exist: {token_file}")
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - installation error path
        raise YouTubePublisherError(
            "YouTube publishing dependencies are not installed"
        ) from exc
    credentials = Credentials.from_authorized_user_file(
        token_file, scopes=[YOUTUBE_SCOPE, YOUTUBE_UPLOAD_SCOPE]
    )
    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            Path(token_file).write_text(credentials.to_json(), encoding="utf-8")
        else:
            raise YouTubePublisherError(
                "YouTube OAuth token is invalid; run scripts/youtube_authorize.py"
            )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def upload_private(
    video_paths: Sequence[str], *, title: str, description: str = ""
) -> list[str]:
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:  # pragma: no cover
        raise YouTubePublisherError(
            "YouTube publishing dependencies are not installed"
        ) from exc

    youtube = _client()
    video_ids = []
    for index, video_path in enumerate(video_paths, start=1):
        upload = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title if len(video_paths) == 1 else f"{title} ({index})",
                    "description": description,
                    "categoryId": "24",
                },
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": True,
                },
            },
            media_body=MediaFileUpload(video_path, resumable=True),
        )
        response = None
        while response is None:
            _, response = upload.next_chunk()
        video_ids.append(response["id"])
    return video_ids


def publish(video_ids: Sequence[str]) -> None:
    youtube = _client()
    for video_id in video_ids:
        youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": True,
                },
            },
        ).execute()
