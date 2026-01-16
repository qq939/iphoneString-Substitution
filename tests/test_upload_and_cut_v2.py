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
    
    with patch('app.requests.get') as mock_get, \
         patch('app.VideoFileClip') as MockVideoFileClip, \
         patch('app.comfy_utils.client.upload_file') as mock_upload_file, \
         patch('app.comfy_utils.queue_workflow_template') as mock_queue_workflow:
         
        # Setup requests.get mock for context manager
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'fake character image']
        
        # When called as context manager
        mock_get.return_value.__enter__.return_value = mock_response
        
        # Setup VideoFileClip
        mock_clip = MagicMock()
        mock_clip.duration = 4
        mock_clip.audio = None
        mock_clip.resize.return_value = mock_clip
        mock_subclip = MagicMock()
        mock_clip.subclip.return_value = mock_subclip
        MockVideoFileClip.return_value = mock_clip
        
        mock_upload_file.side_effect = [
            {'name': 'seg_0.mp4'},
            {'name': 'character.png'}
        ]
        mock_queue_workflow.return_value = ("prompt_123", None)
        
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
        
        assert mock_upload_file.call_count == 2
        assert mock_queue_workflow.call_count == 1
