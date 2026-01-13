import pytest
from unittest.mock import MagicMock, patch
import io
import os
import app

@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    with app.app.test_client() as client:
        yield client

def test_upload_and_cut_success(client):
    # Mock data
    video_content = b'fake video content'
    filename = 'test_video.mp4'
    
    # We need to mock:
    # 1. requests.get (for character download) - needs context manager support
    # 2. VideoFileClip
    # 3. comfy_utils.submit_job
    # 4. obs_utils (though not called in the sync part of upload_and_cut, only in async monitor, but let's be safe)
    
    with patch('app.requests.get') as mock_get, \
         patch('app.VideoFileClip') as MockVideoFileClip, \
         patch('app.comfy_utils.submit_job') as mock_submit_job:
         
        # Setup requests.get mock for context manager
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'fake character image']
        
        # When called as context manager
        mock_get.return_value.__enter__.return_value = mock_response
        
        # Setup VideoFileClip
        mock_clip = MagicMock()
        mock_clip.duration = 4 # 2 segments
        mock_subclip = MagicMock()
        mock_clip.subclipped.return_value = mock_subclip
        MockVideoFileClip.return_value = mock_clip
        
        # Setup submit_job
        mock_submit_job.return_value = ("prompt_123", None)
        
        # Make request
        data = {
            'video': (io.BytesIO(video_content), filename)
        }
        response = client.post('/upload_and_cut', data=data, content_type='multipart/form-data')
        
        # Debug output if fails
        if response.status_code != 200:
            print(response.get_json())
            
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['status'] == 'processing'
        assert 'group_id' in json_data
        
        # Verify character download was attempted
        args, _ = mock_get.call_args
        assert args[0] == "http://obs.dimond.top/character.png"
        
        # Verify submit_job was called with the downloaded character path
        # The path should be in UPLOAD_FOLDER and start with character_for_
        submit_args, _ = mock_submit_job.call_args
        char_path_arg = submit_args[0]
        assert "character_for_test_video.mp4" in char_path_arg
