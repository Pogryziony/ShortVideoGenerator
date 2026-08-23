from unittest import mock

import pytest

from app.services import video_validation


def _clip(width=1080, height=1920, duration=45, has_audio=True):
    clip = mock.Mock()
    clip.w = width
    clip.h = height
    clip.duration = duration
    clip.audio = mock.Mock() if has_audio else None
    return clip


@mock.patch("app.services.video_validation.os.path.getsize", return_value=1024)
@mock.patch("app.services.video_validation.os.path.isfile", return_value=True)
@mock.patch("app.services.video_validation.VideoFileClip")
def test_accepts_vertical_video_near_45_seconds(video_clip, _isfile, _getsize):
    video_clip.return_value = _clip()
    report = video_validation.validate_story_videos(["final.mp4"])
    assert report["passed"] is True
    assert report["videos"][0]["width"] == 1080


@pytest.mark.parametrize(
    "clip,error",
    [
        (_clip(width=1920, height=1080), "9:16"),
        (_clip(duration=60), "duration"),
        (_clip(has_audio=False), "audio track"),
    ],
)
@mock.patch("app.services.video_validation.os.path.getsize", return_value=1024)
@mock.patch("app.services.video_validation.os.path.isfile", return_value=True)
def test_rejects_invalid_render(_isfile, _getsize, clip, error):
    with mock.patch(
        "app.services.video_validation.VideoFileClip", return_value=clip
    ):
        with pytest.raises(video_validation.VideoValidationError, match=error):
            video_validation.validate_story_videos(["final.mp4"])
