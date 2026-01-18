import io
import os
import sys
import signal
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

sys.path.append(os.getcwd())
import app


class TransitionWorkflowTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TransitionWorkflowTimeoutError("transition workflow api test timeout")


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


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client


def test_upload_transition_video_initial_group(client):
    video_content = b"fake video for transition"
    filename = "transition_test_1.mp4"

    with timeout_scope(5):
        with patch("app.ffmpeg_utils.resize_video") as mock_resize, patch(
            "app.ffmpeg_utils.get_video_info"
        ) as mock_info, patch(
            "app.ffmpeg_utils.extract_frame"
        ) as mock_extract, patch(
            "app.comfy_utils.client.upload_file"
        ) as mock_upload, patch(
            "app.comfy_utils.queue_transition_workflow"
        ) as mock_queue_transition, patch(
            "app.ensure_comfy_connection"
        ) as mock_ensure:
            mock_ensure.return_value = None
            mock_resize.return_value = None
            mock_info.return_value = {"duration": 4.0}
            mock_extract.return_value = None
            mock_upload.side_effect = [
                {"name": "frame_start.png"},
                {"name": "frame_end.png"},
            ]
            mock_queue_transition.return_value = (
                "prompt_transition_1",
                "server_1",
                None,
            )

            data = {"video": (io.BytesIO(video_content), filename)}
            response = client.post(
                "/upload_transition_video",
                data=data,
                content_type="multipart/form-data",
            )

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data["status"] in ("processing", "collecting")
            assert "group_id" in json_data

            assert mock_resize.called
            resize_args = mock_resize.call_args[0]
            assert resize_args[2] == 640
            assert resize_args[3] == 16
