import os
import sys
import time
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ComfyUIClient before importing app to avoid initialization issues
with patch('comfy_utils.ComfyUIClient'):
    import app

@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with app.app.test_client() as client:
        yield client

def test_backend_proactive_monitoring(client):
    """
    Test that monitor_audio_task can complete an audio task and trigger Stage 2
    without relying on /check_audio_status.
    """
    prompt_id = 'test_prompt_monitor'

    with patch('app.comfy_utils.check_status') as mock_check_status, \
         patch('app.comfy_utils.download_result', return_value='tmp/test_result.wav'), \
         patch('app.obs_utils.upload_file', return_value='http://obs/result.wav'), \
         patch('app.process_digital_human_video') as mock_stage2, \
         patch('app.AudioSegment', None), \
         patch('app.time.sleep', return_value=None):

        # Prepare dummy downloaded file
        if not os.path.exists('tmp'):
            os.makedirs('tmp')
        with open('tmp/test_result.wav', 'w') as f:
            f.write('dummy audio')

        mock_check_status.return_value = ('SUCCEEDED', {'filename': 'test_result.wav', 'subfolder': '', 'type': 'output'})

        with app.AUDIO_LOCK:
            app.AUDIO_TASKS[prompt_id] = {
                'status': 'pending',
                'url': None,
                'input_video_path': None,
                'server': None,
                'created_at': time.time(),
            }

        app.monitor_audio_task(prompt_id)

        with app.AUDIO_LOCK:
            assert app.AUDIO_TASKS[prompt_id]['status'] == 'completed'
            assert app.AUDIO_TASKS[prompt_id]['url'] == 'http://obs/result.wav'

        assert mock_stage2.called


@patch('app.time.sleep', return_value=None)
@patch('app.time.time')
def test_monitor_audio_task_stops_after_global_timeout(mock_time, mock_sleep):
    prompt_id = 'timeout_prompt'
    now = 1_000_000.0
    mock_time.return_value = now

    # Prepare AUDIO_TASKS entry with created_at far in the past
    with app.AUDIO_LOCK:
        app.AUDIO_TASKS[prompt_id] = {
            'status': 'pending',
            'url': None,
            'input_video_path': None,
            'server': None,
            'created_at': now - (app.WAI_OVERTIME_SECONDS + 1),
        }

    with patch('app.comfy_utils.check_status', return_value=('PENDING', None)):
        app.monitor_audio_task(prompt_id)

    with app.AUDIO_LOCK:
        assert app.AUDIO_TASKS[prompt_id]['status'] == 'failed'
        assert 'timeout' in app.AUDIO_TASKS[prompt_id].get('error', '').lower()


@patch('app.get_latest_file_from_obs')
def test_stage2_uses_obs_character_when_no_input_video(mock_get_latest):
    mock_get_latest.return_value = 'character.mp4'
    from app import process_digital_human_video

    with patch('app.requests.get') as mock_get, \
         patch('app.os.path.exists', return_value=True), \
         patch('builtins.open'), \
         patch('app.comfy_utils.client.upload_file', return_value={'name': 'uploaded_character.mp4'}) as mock_upload, \
         patch('app.json.load', return_value={}), \
         patch('app.modify_extend_video_workflow', return_value={}) as mock_modify, \
         patch('app.comfy_utils.client.queue_prompt', return_value=('pid', 'server')):

        resp = MagicMock()
        resp.status_code = 200
        resp.iter_content.return_value = [b'video']
        resp.__enter__.return_value = resp
        mock_get.return_value = resp

        process_digital_human_video('dummy_audio.wav', None)

        mock_get_latest.assert_called_with('character.mp4')
        mock_upload.assert_called()
