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


def test_upload_transition_video_logging_steps(client, monkeypatch):
    video_content = b"fake video for transition"
    filename = "transition_log_test.mp4"

    captured_logs = []

    def fake_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        captured_logs.append(msg)

    monkeypatch.setattr("builtins.print", fake_print)

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

            group_id = response.get_json()["group_id"]

            data2 = {
                "video": (io.BytesIO(video_content), filename),
                "group_id": group_id,
            }
            response2 = client.post(
                "/upload_transition_video",
                data=data2,
                content_type="multipart/form-data",
            )
            assert response2.status_code == 200

    log_text = "\n".join(captured_logs)
    assert "已预处理转场视频为640x640" in log_text
    assert "已将视频追加到转场列表" in log_text
    assert "准备生成第" in log_text
    assert "提交ComfyUI收尾帧工作流" in log_text


def test_monitor_group_task_logging_after_all_done(monkeypatch):
    from app import monitor_group_task, TASKS_STORE, UPLOAD_FOLDER

    captured_logs = []

    def fake_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        captured_logs.append(msg)

    monkeypatch.setattr("builtins.print", fake_print)

    group_id = "test_group_logging"
    seg1_path = os.path.join(UPLOAD_FOLDER, "seg1.mp4")
    seg2_path = os.path.join(UPLOAD_FOLDER, "seg2.mp4")

    TASKS_STORE[group_id] = {
        "status": "processing",
        "tasks": [
            {
                "task_id": "t1",
                "server": None,
                "status": "completed",
                "segment_index": 0,
                "result_path": seg1_path,
            },
            {
                "task_id": "t2",
                "server": None,
                "status": "completed",
                "segment_index": 1,
                "result_path": seg2_path,
            },
        ],
            "created_at": None,
        "audio_path": None,
        "workflow_type": "transition",
    }

    with timeout_scope(5):
        def fake_exists(path):
            return path in (seg1_path, seg2_path)

        with patch("app.os.path.exists", side_effect=fake_exists), patch(
            "app.ffmpeg_utils.concatenate_videos"
        ), patch(
            "app.obs_utils.upload_file", return_value="http://obs/example_all.mp4"
        ), patch("app.time.sleep", return_value=None), patch(
            "app.shutil.move"
        ):
            monitor_group_task(group_id)

    log_text = "\n".join(captured_logs)
    assert "检测到组" in log_text
    assert "开始拼接+上传OBS" in log_text
