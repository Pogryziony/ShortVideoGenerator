"""Automatic quality gate for rendered story shorts."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Sequence

from moviepy import VideoFileClip


class VideoValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedVideo:
    path: str
    width: int
    height: int
    duration_seconds: float
    has_audio: bool


def validate_story_videos(
    video_paths: Sequence[str],
    *,
    target_seconds: float = 45,
    tolerance_seconds: float = 6,
    aspect_tolerance: float = 0.02,
) -> dict:
    if not video_paths:
        raise VideoValidationError("no rendered videos were provided")

    validated = []
    expected_ratio = 9 / 16
    for video_path in video_paths:
        if not os.path.isfile(video_path) or os.path.getsize(video_path) == 0:
            raise VideoValidationError(f"rendered video is missing or empty: {video_path}")
        clip = VideoFileClip(video_path)
        try:
            width, height = (int(clip.w), int(clip.h))
            duration = float(clip.duration or 0)
            has_audio = clip.audio is not None
        finally:
            clip.close()

        if height <= 0 or not math.isclose(
            width / height, expected_ratio, abs_tol=aspect_tolerance
        ):
            raise VideoValidationError(
                f"video must be 9:16; received {width}x{height}"
            )
        if abs(duration - target_seconds) > tolerance_seconds:
            raise VideoValidationError(
                f"video duration must be {target_seconds:.0f}±{tolerance_seconds:.0f} "
                f"seconds; received {duration:.1f}"
            )
        if not has_audio:
            raise VideoValidationError("rendered video does not contain an audio track")

        validated.append(
            ValidatedVideo(video_path, width, height, duration, has_audio)
        )

    return {
        "passed": True,
        "target_seconds": target_seconds,
        "tolerance_seconds": tolerance_seconds,
        "videos": [asdict(item) for item in validated],
    }
