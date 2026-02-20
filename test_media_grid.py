import os
import signal
import json
from unittest.mock import patch

from app import app


def timeout(seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            def handler(signum, frame):
                raise TimeoutError("Test timed out")

            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


@timeout(5)
def test_latest_video_route_uses_obs_helper():
    test_client = app.test_client()

    with patch("app.get_latest_file_from_obs") as mock_helper:
        mock_helper.return_value = "20260114000123all.mp4"
        resp = test_client.get("/latest_video")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["url"] == "http://obs.dimond.top/20260114000123all.mp4"
    mock_helper.assert_called_once_with("all.mp4")


@timeout(5)
def test_latest_audio_route_uses_obs_helper():
    test_client = app.test_client()

    with patch("app.get_latest_file_from_obs") as mock_helper:
        mock_helper.return_value = "20260114000123audio.wav"
        resp = test_client.get("/latest_audio")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["url"] == "http://obs.dimond.top/20260114000123audio.wav"
    assert data["filename"] == "20260114000123audio.wav"
    mock_helper.assert_called_once_with("audio.wav")


@timeout(5)
def test_index_has_video_cache_definition():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_dir, "templates", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "var videoCache" in content


@timeout(5)
def test_grid_layout_is_2x4():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    css_path = os.path.join(base_dir, "static", "css", "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    assert "grid-template-columns: repeat(4, 1fr);" in css
    assert "grid-template-rows: repeat(2, 1fr);" in css
