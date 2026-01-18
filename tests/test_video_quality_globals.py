import os
import sys
import signal
from contextlib import contextmanager
from unittest.mock import patch

import pytest

sys.path.append(os.getcwd())
import app


class VideoQualityTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise VideoQualityTimeoutError("video quality globals tests timeout")


@contextmanager
def timeout_scope(seconds):
    original_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)


def test_video_quality_globals_exist_and_types():
    with timeout_scope(5):
        assert hasattr(app, "VIDEO_WIDTH")
        assert hasattr(app, "VIDEO_HEIGHT")
        assert hasattr(app, "VIDEO_FPS")
        assert isinstance(app.VIDEO_WIDTH, int)
        assert isinstance(app.VIDEO_HEIGHT, int)
        assert isinstance(app.VIDEO_FPS, int)
        assert app.VIDEO_WIDTH > 0
        assert app.VIDEO_HEIGHT > 0
        assert app.VIDEO_FPS > 0


def test_generate_1s_video_uses_global_fps():
    with timeout_scope(5):
        with patch("app.ffmpeg_utils.image_to_video") as mock_image_to_video:
            image_path = os.path.join("tmp", "test_image.png")
            output_path = os.path.join("tmp", "test_output.mp4")
            app.generate_1s_video(image_path, output_path)
            assert mock_image_to_video.called
            _, _, kwargs = mock_image_to_video.mock_calls[0]
            assert "fps" in kwargs
            assert kwargs["fps"] == app.VIDEO_FPS

