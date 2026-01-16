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
