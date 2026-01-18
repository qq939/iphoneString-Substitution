import os
import sys
import signal
from contextlib import contextmanager
from unittest.mock import patch

import pytest

sys.path.append(os.getcwd())
import comfy_utils


class TransitionTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TransitionTimeoutError("transition comfy_utils test timeout")


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


def test_queue_transition_workflow_basic():
    workflow_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "comfyapi",
        "收尾帧wan2.1_flf2v_720_f16.json",
    )
    if not os.path.exists(workflow_path):
        pytest.skip("transition workflow json not found")

    with timeout_scope(5):
        with patch("comfy_utils.client.queue_prompt") as mock_queue, patch(
            "comfy_utils._load_switch_prompt", return_value="测试转场文案abcdef"
        ):
            mock_queue.return_value = ("prompt_transition_1", "server_1")
            start_image = "start_image.png"
            end_image = "end_image.png"

            prompt_id, server_address, error = comfy_utils.queue_transition_workflow(
                start_image, end_image
            )

            assert error is None
            assert prompt_id == "prompt_transition_1"
            assert server_address == "server_1"
            assert mock_queue.called

            sent_workflow = mock_queue.call_args[0][0]

            assert sent_workflow["52"]["inputs"]["image"] == start_image
            assert sent_workflow["72"]["inputs"]["image"] == end_image

            node83_inputs = sent_workflow.get("83", {}).get("inputs", {})
            assert node83_inputs.get("width") == 640
            assert node83_inputs.get("height") == 640
            assert node83_inputs.get("length") == 16

            node6_inputs = sent_workflow.get("6", {}).get("inputs", {})
            assert node6_inputs.get("text") == "测试转场文案abcdef"


def test_load_switch_prompt_uses_root_file_if_exists():
    with timeout_scope(5):
        text = comfy_utils._load_switch_prompt()
        assert text is not None
        assert isinstance(text, str)
