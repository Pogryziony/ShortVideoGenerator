# Automated 45-second story shorts

This fork adds an opinionated production path for fictional YouTube Shorts. It
generates a random story category, enforces 100–115 words, renders at 9:16 over
local Minecraft/ASMR footage, checks semantic similarity in PostgreSQL, validates
the output and uploads it to YouTube as **private** before publication.

## 1. Configure the services

Copy `config.example.toml` to `config.toml`, then configure an LLM/TTS provider.
For semantic duplicate detection, set `story_embedding_api_key` (and optionally
`story_embedding_base_url`). Use an embeddings endpoint compatible with the
OpenAI Python client.

Set a non-default database password and start the stack:

```bash
export POSTGRES_PASSWORD='replace-with-a-long-random-password'
docker compose up -d --build
```

Place only footage you own or are licensed to reuse in
`storage/local_videos/`. Long Minecraft parkour and ASMR videos are segmented
automatically; the exact source path and time range used by every output is
stored in PostgreSQL.

## 2. Authorize YouTube

Create an OAuth Desktop client in Google Cloud, enable YouTube Data API v3, then
run this command on a machine with a browser:

```bash
uv run python scripts/youtube_authorize.py \
  --client-secrets /secure/path/client_secret.json \
  --output storage/youtube-token.json
```

Keep both OAuth files out of Git. The generated token is mounted into the API
container. Set `youtube_publish_required = true` after authorization.

## 3. Generate one private short

```bash
uv run python scripts/story_runner.py
```

The API returns a task ID immediately. Query `/api/v1/tasks/{task_id}` until the
task completes. A successful manual-review run ends with
`approval_state=pending_manual_approval` and one or more private YouTube IDs.

Publish or reject it:

```bash
curl -X POST -H "x-api-key: $MPT_API_KEY" \
  http://127.0.0.1:8080/api/v1/tasks/TASK_ID/approve

curl -X POST -H "x-api-key: $MPT_API_KEY" \
  http://127.0.0.1:8080/api/v1/tasks/TASK_ID/reject
```

`reject` leaves the YouTube video private. For automatic publication after all
checks pass, set `SHORT_VIDEO_AUTO_PUBLISH=true` for the runner or send
`auto_publish_after_validation=true` in the API request.

## 4. Schedule it

- Cron: edit the checkout path in `deploy/cron/short-video-generator`, then run
  `crontab deploy/cron/short-video-generator`.
- n8n: import `deploy/n8n/story-factory-workflow.json`, configure
  `SHORT_VIDEO_API_URL` and `MPT_API_KEY`, then activate the workflow.

The cron example uses `flock`, so overlapping runs are skipped.
