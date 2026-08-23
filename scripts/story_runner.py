#!/usr/bin/env python3
"""Submit one automated fictional-short run to the API."""

from __future__ import annotations

import json
import os
import sys

import requests


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    api_url = os.getenv(
        "SHORT_VIDEO_API_URL", "http://127.0.0.1:8080/api/v1/videos"
    )
    subject = os.getenv(
        "SHORT_VIDEO_SUBJECT",
        "Invent a completely original high-retention fictional story",
    )
    language = os.getenv("SHORT_VIDEO_LANGUAGE", "English")
    api_key = os.getenv("MPT_API_KEY", "")
    payload = {
        "video_subject": subject,
        "video_language": language,
        "story_mode": True,
        "video_source": "local",
        "video_aspect": "9:16",
        "target_narration_seconds": 45,
        "narration_tolerance_seconds": 6,
        "auto_publish_after_validation": _as_bool(
            os.getenv("SHORT_VIDEO_AUTO_PUBLISH", "false")
        ),
        "video_count": 1,
        "paragraph_number": 1,
    }
    headers = {"x-api-key": api_key} if api_key else {}
    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"story run submission failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
