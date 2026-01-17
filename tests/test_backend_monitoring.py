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
    Test that the backend proactively monitors the task and completes it 
    without the frontend calling /check_audio_status.
    """
    prompt_id = 'test_prompt_monitor'
    
    # Mock dependencies
    with patch('app.ensure_comfy_connection'), \
         patch('app.comfy_utils.client.upload_file', return_value={'name': 'test.wav'}), \
         patch('app.comfy_utils.client.queue_prompt', return_value=prompt_id), \
         patch('app.comfy_utils.check_status') as mock_check_status, \
         patch('app.comfy_utils.download_result', return_value='tmp/test_result.wav'), \
         patch('app.obs_utils.upload_file', return_value='http://obs/result.wav'), \
         patch('app.process_digital_human_video') as mock_stage2, \
         patch('shutil.copy'), \
         patch('os.remove'):

        # Create a dummy result file for download_result to "find"
        with open('tmp/test_result.wav', 'w') as f:
            f.write('dummy audio')

        # Setup mock check_status behavior:
        # First few calls -> RUNNING
        # Then -> SUCCEEDED
        # Note: Since the monitor runs in a thread, we need to be careful with side effects
        mock_check_status.side_effect = [
            ('RUNNING', None),
            ('RUNNING', None),
            ('SUCCEEDED', {'filename': 'test_result.wav', 'subfolder': '', 'type': 'output'})
        ]

        # Call upload_audio to start the process
        # We need a file or text. 'text' is required.
        # We simulate uploading a file so we don't hit the download-from-obs path which is slower/complex
        data = {'text': 'test monitoring'}
        # Simulate file upload
        data['file'] = (dict(read=lambda: b'audio content'), 'test.wav')
        
        # We need to mock request.files properly or just use data dict for client.post
        # client.post with data containing file object
        import io
        res = client.post('/upload_audio', data={
            'text': 'test monitoring',
            'file': (io.BytesIO(b'audio'), 'test.wav')
        }, content_type='multipart/form-data')
        
        assert res.status_code == 200
        assert res.get_json()['prompt_id'] == prompt_id
        
        # Verify initial state
        assert prompt_id in app.AUDIO_TASKS
        assert app.AUDIO_TASKS[prompt_id]['status'] == 'pending'
        
        # Now wait for the background thread to do its work.
        # The monitor sleeps for 5 seconds between checks.
        # We need to wait enough time for the mocked checks to pass (3 calls -> ~10-15s).
        
        max_retries = 150 # 15 seconds
        completed = False
        for _ in range(max_retries):
            if app.AUDIO_TASKS[prompt_id]['status'] == 'completed':
                completed = True
                break
            time.sleep(0.1)
            
        # This assertion is expected to FAIL until we implement the background monitoring
        assert completed, "Task status should become completed without calling /check_audio_status"
        
        # Verify Stage 2 was triggered
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
            'created_at': now - (app.BACKEND_TASK_TIMEOUT_SECONDS + 1),
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
