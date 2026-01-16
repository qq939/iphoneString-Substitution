import pytest
import time
import json
import os
import io
import threading
from unittest.mock import MagicMock, patch

# Patch ComfyUIClient init to avoid network calls during import
with patch('comfy_utils.ComfyUIClient') as MockClient:
    from app import app, TASKS_STORE

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Create tmp directory if not exists
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with app.test_client() as client:
        yield client

def test_async_process_flow(client):
    # Mock data
    video_content = b'fake video content'
    filename = 'test_video.mp4'
    
    with patch('app.VideoFileClip') as MockVideoFileClip, \
         patch('app.comfy_utils') as mock_comfy, \
         patch('app.obs_utils') as mock_obs, \
         patch('app.concatenate_videoclips') as mock_concat, \
         patch('app.os.remove') as mock_remove, \
         patch('app.vfx') as mock_vfx:
         
        # Setup VideoFileClip mock
        mock_clip = MagicMock()
        mock_clip.duration = 8
        mock_clip.audio = None
        mock_clip.resize.return_value = mock_clip
        mock_vfx.resize.return_value = mock_clip
        mock_subclip = MagicMock()
        mock_clip.subclip.return_value = mock_subclip
        MockVideoFileClip.return_value = mock_clip
        
        mock_comfy.client.upload_file.side_effect = [
            {'name': 'seg_0.mp4'},
            {'name': 'character.png'},
            {'name': 'seg_1.mp4'},
            {'name': 'character.png'}
        ]
        mock_comfy.queue_workflow_template.side_effect = [("task_1", None), ("task_2", None)]
        
        # Setup check_status mock
        # We need to handle multiple calls.
        # Background thread will call check_status for task_1 and task_2.
        # Let's make them succeed immediately for speed.
        # Returns (status, result)
        def check_status_side_effect(task_id):
            if task_id == "task_1":
                return "SUCCEEDED", {"filename": "out1.mp4"}
            elif task_id == "task_2":
                return "SUCCEEDED", {"filename": "out2.mp4"}
            return "FAILED", "Unknown task"
            
        mock_comfy.check_status.side_effect = check_status_side_effect
        
        # Setup download_result mock
        # Returns local_path
        def download_side_effect(result, folder):
            path = os.path.join(folder, result['filename'])
            # Create dummy file so os.path.exists returns True
            with open(path, 'wb') as f:
                f.write(b'dummy content')
            return path
            
        mock_comfy.download_result.side_effect = download_side_effect
        
        # Setup obs upload mock
        mock_obs.upload_file.return_value = "http://obs/final.mp4"
        
        # Setup concat mock
        mock_final_clip = MagicMock()
        mock_final_clip.audio = None
        mock_concat.return_value = mock_final_clip
        
        # Mock requests.get for character download
        with patch('app.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b'fake character image']
            mock_response.raise_for_status = MagicMock()
            
            # Setup context manager return value
            mock_get.return_value.__enter__.return_value = mock_response
            
            # 1. Upload Video
            data = {
                'video': (io.BytesIO(video_content), filename)
            }
            response = client.post('/upload_and_cut', data=data, content_type='multipart/form-data')
            
            assert response.status_code == 200
            json_data = response.get_json()
            assert 'group_id' in json_data
            group_id = json_data['group_id']
            
            # 2. Wait for background thread to finish
        # We can loop check_group_status
        start_time = time.time()
        final_status = None
        
        while time.time() - start_time < 5: # 5 seconds timeout
            status_res = client.get(f'/check_group_status/{group_id}')
            status_data = status_res.get_json()
            if status_data['status'] == 'completed':
                final_status = status_data
                break
            if status_data['status'] == 'failed':
                final_status = status_data
                break
            time.sleep(0.1)
            
        assert final_status is not None
        if final_status['status'] == 'failed':
            print(f"Failed with error: {final_status.get('error')}")
            
        assert final_status['status'] == 'completed'
        assert final_status['final_url'] == "http://obs/final.mp4"
        
        # Verify calls
        assert mock_comfy.queue_workflow_template.call_count == 2
        assert mock_concat.called
        assert mock_obs.upload_file.called
