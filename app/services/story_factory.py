"""Fictional story generation policy and PostgreSQL persistence.

The module is intentionally independent from the rendering pipeline.  It owns the
story contract (category, length and hook), semantic duplicate detection and the
durable audit trail used by scheduled runs.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from loguru import logger
from openai import OpenAI

from app.config import config


STORY_CATEGORIES = (
    "an impossible coincidence",
    "a hidden identity",
    "a betrayal between best friends",
    "a moral dilemma with no clean answer",
    "an eerie technology glitch",
    "a survival decision made in seconds",
    "a time loop with one changing detail",
    "revenge that backfires",
    "an urban legend that becomes real",
    "a workplace secret",
    "a stranger who knows too much",
    "a wholesome act with a dark twist",
)

MIN_STORY_WORDS = 100
MAX_STORY_WORDS = 115
DEFAULT_TARGET_SECONDS = 45
DEFAULT_DURATION_TOLERANCE_SECONDS = 6

FICTIONAL_STORY_SYSTEM_PROMPT = f"""
# Role: Viral Fictional Short-Story Writer

Write one original fictional story for a vertical short-form video.

Rules:
1. The story must contain {MIN_STORY_WORDS}–{MAX_STORY_WORDS} spoken words, inclusive.
2. Open with a one-sentence hook that creates immediate curiosity or danger.
3. Use simple, vivid language, escalating tension, and a new reveal every few sentences.
4. End with a satisfying twist, unsettling implication, or open loop that invites comments.
5. Write one continuous narration suitable for roughly {DEFAULT_TARGET_SECONDS} seconds.
6. Never use a title, labels, stage directions, markdown, hashtags, or calls to subscribe.
7. Do not describe background footage; it will be Minecraft parkour or ASMR video.
8. Invent all people, places, dialogue, and events. Do not present real claims as fact.
9. Return only the narration, in the requested language.
""".strip()

_WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")


class StoryFactoryError(RuntimeError):
    """Base error for a story-factory run."""


class DuplicateStoryError(StoryFactoryError):
    def __init__(self, similarity: float, threshold: float):
        super().__init__(
            f"story is too similar to an existing story "
            f"({similarity:.3f} >= {threshold:.3f})"
        )
        self.similarity = similarity
        self.threshold = threshold


class StoryLengthError(StoryFactoryError):
    pass


@dataclass(frozen=True)
class StoryRecord:
    task_id: str
    category: str
    subject: str
    hook: str
    script: str
    word_count: int
    max_similarity: float


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def extract_hook(text: str) -> str:
    normalized = " ".join((text or "").strip().split())
    if not normalized:
        return ""
    first = _SENTENCE_END_RE.split(normalized, maxsplit=1)[0]
    return first[:500]


def choose_category(requested: str | None = None, rng=None) -> str:
    requested = (requested or "").strip()
    if requested:
        return requested
    chooser = rng or random.SystemRandom()
    return chooser.choice(STORY_CATEGORIES)


def validate_story_length(script: str) -> int:
    word_count = count_words(script)
    if not MIN_STORY_WORDS <= word_count <= MAX_STORY_WORDS:
        raise StoryLengthError(
            f"story must contain {MIN_STORY_WORDS}-{MAX_STORY_WORDS} words; "
            f"received {word_count}"
        )
    return word_count


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def reject_if_similar(
    embedding: Sequence[float],
    existing_embeddings: Iterable[Sequence[float]],
    threshold: float,
) -> float:
    max_similarity = max(
        (cosine_similarity(embedding, item) for item in existing_embeddings),
        default=0.0,
    )
    if max_similarity >= threshold:
        raise DuplicateStoryError(max_similarity, threshold)
    return max_similarity


def _database_url() -> str:
    return os.getenv(
        "MPT_APP_DATABASE_URL", str(config.app.get("database_url", "") or "")
    ).strip()


def _embedding_client() -> OpenAI:
    api_key = os.getenv(
        "STORY_EMBEDDING_API_KEY",
        str(
            config.app.get("story_embedding_api_key", "")
            or config.app.get("openai_api_key", "")
            or ""
        ),
    ).strip()
    base_url = os.getenv(
        "STORY_EMBEDDING_BASE_URL",
        str(config.app.get("story_embedding_base_url", "") or ""),
    ).strip()
    if not api_key:
        raise StoryFactoryError(
            "semantic duplicate detection requires story_embedding_api_key "
            "or STORY_EMBEDDING_API_KEY"
        )
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def create_embedding(text: str) -> list[float]:
    model = str(
        config.app.get("story_embedding_model", "text-embedding-3-small")
    ).strip()
    response = _embedding_client().embeddings.create(model=model, input=text)
    return list(response.data[0].embedding)


class StoryRepository:
    """PostgreSQL story repository with transaction-level duplicate protection."""

    def __init__(
        self,
        database_url: str | None = None,
        embedding_factory: Callable[[str], list[float]] = create_embedding,
    ):
        self.database_url = (database_url if database_url is not None else _database_url()).strip()
        self.embedding_factory = embedding_factory

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - installation error path
            raise StoryFactoryError(
                "PostgreSQL support requires the psycopg dependency"
            ) from exc
        return psycopg.connect(self.database_url)

    def ensure_schema(self) -> None:
        if not self.enabled:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_stories (
                    id BIGSERIAL PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    hook TEXT NOT NULL,
                    script TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    embedding DOUBLE PRECISION[] NOT NULL,
                    max_similarity DOUBLE PRECISION NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'reserved',
                    validation_report JSONB,
                    youtube_video_ids TEXT[],
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS footage_segments (
                    id BIGSERIAL PRIMARY KEY,
                    story_id BIGINT NOT NULL REFERENCES generated_stories(id)
                        ON DELETE CASCADE,
                    output_index INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    start_seconds DOUBLE PRECISION NOT NULL,
                    end_seconds DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS generated_stories_created_idx "
                "ON generated_stories (created_at DESC)"
            )

    def reserve_story(
        self,
        *,
        task_id: str,
        category: str,
        subject: str,
        script: str,
        threshold: float | None = None,
    ) -> StoryRecord:
        word_count = validate_story_length(script)
        hook = extract_hook(script)
        duplicate_threshold = float(
            threshold
            if threshold is not None
            else config.app.get("story_similarity_threshold", 0.88)
        )
        recent_limit = int(config.app.get("story_similarity_history_limit", 500))

        if not self.enabled:
            required = bool(config.app.get("story_database_required", False))
            if required:
                raise StoryFactoryError("database_url is required for story generation")
            logger.warning(
                "story database is disabled; semantic duplicate history is not persistent"
            )
            return StoryRecord(
                task_id, category, subject, hook, script, word_count, 0.0
            )

        embedding = self.embedding_factory(script)
        self.ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            # Serialize only the short similarity-check/insert critical section.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (734512409,))
            cursor.execute(
                "SELECT embedding FROM generated_stories "
                "ORDER BY created_at DESC LIMIT %s",
                (recent_limit,),
            )
            max_similarity = reject_if_similar(
                embedding,
                (row[0] or [] for row in cursor.fetchall()),
                duplicate_threshold,
            )

            cursor.execute(
                """
                INSERT INTO generated_stories
                    (task_id, category, subject, hook, script, word_count,
                     embedding, max_similarity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    task_id,
                    category,
                    subject,
                    hook,
                    script,
                    word_count,
                    embedding,
                    max_similarity,
                ),
            )
        return StoryRecord(
            task_id, category, subject, hook, script, word_count, max_similarity
        )

    def save_render_result(
        self,
        task_id: str,
        *,
        validation_report: dict,
        segment_manifests: Iterable[str],
        youtube_video_ids: Sequence[str] | None = None,
        status: str = "validated",
    ) -> None:
        if not self.enabled:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE generated_stories
                SET status=%s, validation_report=%s::jsonb,
                    youtube_video_ids=%s, updated_at=NOW()
                WHERE task_id=%s RETURNING id
                """,
                (
                    status,
                    json.dumps(validation_report),
                    list(youtube_video_ids or []),
                    task_id,
                ),
            )
            row = cursor.fetchone()
            if not row:
                raise StoryFactoryError(f"story reservation not found for task {task_id}")
            story_id = row[0]
            cursor.execute("DELETE FROM footage_segments WHERE story_id=%s", (story_id,))
            for output_index, manifest_path in enumerate(segment_manifests, start=1):
                with open(manifest_path, encoding="utf-8") as handle:
                    segments = json.load(handle)
                for segment in segments:
                    cursor.execute(
                        """
                        INSERT INTO footage_segments
                            (story_id, output_index, source_path,
                             start_seconds, end_seconds)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            story_id,
                            output_index,
                            segment["source_path"],
                            segment["start_seconds"],
                            segment["end_seconds"],
                        ),
                    )

    def update_status(
        self, task_id: str, status: str, youtube_video_ids: Sequence[str] | None = None
    ) -> None:
        if not self.enabled:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE generated_stories
                SET status=%s,
                    youtube_video_ids=COALESCE(%s, youtube_video_ids),
                    updated_at=NOW()
                WHERE task_id=%s
                """,
                (status, list(youtube_video_ids) if youtube_video_ids is not None else None, task_id),
            )


repository = StoryRepository()
