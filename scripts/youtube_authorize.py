#!/usr/bin/env python3
"""Create the local OAuth token used by private-first YouTube uploads."""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.services.youtube_publisher import YOUTUBE_SCOPE, YOUTUBE_UPLOAD_SCOPE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secrets", required=True)
    parser.add_argument("--output", default="storage/youtube-token.json")
    args = parser.parse_args()
    flow = InstalledAppFlow.from_client_secrets_file(
        args.client_secrets, scopes=[YOUTUBE_SCOPE, YOUTUBE_UPLOAD_SCOPE]
    )
    credentials = flow.run_local_server(port=0)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(credentials.to_json(), encoding="utf-8")
    print(f"YouTube token saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
