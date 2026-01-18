import os
import sys
import signal
from contextlib import contextmanager

import pytest

sys.path.append(os.getcwd())
import app


class GlobalsPagingTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise GlobalsPagingTimeoutError("globals and paging tests timeout")


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


def test_app_globals_exist_and_types():
    with timeout_scope(5):
        assert isinstance(app.SUBSTITUTION_FILE, str)
        assert isinstance(app.UPLOAD_FOLDER, str)
        assert isinstance(app.COMFY_STATUS, dict)
        assert isinstance(app.TASKS_STORE, dict)
        assert isinstance(app.AUDIO_TASKS, dict)
        assert hasattr(app, "BACKEND_TASK_TIMEOUT_SECONDS")
        assert hasattr(app, "BACKEND_POLL_INTERVAL_SECONDS")


def test_index_has_sector_titles_and_paging_controls():
    with timeout_scope(5):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(base_dir)
        index_path = os.path.join(project_root, "templates", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        for i in range(1, 33):
            assert f"Sector{i}" in content
        assert "page-container" in content
        assert "page-nav-bar" in content
        assert "page-nav-prev" in content
        assert "page-nav-next" in content


def test_sector8_and_9_have_content():
    with timeout_scope(5):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(base_dir)
        index_path = os.path.join(project_root, "templates", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Sector8" in content
        assert "latestAudioPreview" in content
        assert "Sector9" in content
        assert "RESERVED SLOT" in content
