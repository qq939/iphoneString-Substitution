import pytest
from unittest.mock import MagicMock, patch
import sys
import os
import io

# We need to ensure app is imported, but we might need to mock dependencies if they are not installed or for testing isolation.
# Since we installed dependencies, we can import, but for the test logic we want to mock the heavy lifting.

from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Create tmp directory if not exists, as app might need it
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with app.test_client() as client:
        yield client

def test_upload_and_cut(client):
    # Mock video file content
    data = {
        'video': (io.BytesIO(b'fake video content'), 'test.mp4')
    }
    
    # We patch the classes/functions where they are USED in app.py
    # Assuming app.py will have: from moviepy import VideoFileClip
    # so we patch 'app.VideoFileClip'
    
    # Also patch os.remove to avoid errors on missing files
    with patch('app.VideoFileClip') as MockVideoFileClip, \
         patch('app.requests.post') as mock_post, \
         patch('os.remove') as mock_remove:
        
        # Setup mock clip
        mock_clip = MagicMock()
        mock_clip.duration = 7  # Should result in 3 segments: 0-3, 3-6, 6-7
        
        mock_subclip = MagicMock()
        mock_clip.subclipped.return_value = mock_subclip
        
        # Side effect to create dummy segment files when write_videofile is called
        def create_dummy_segment(filename, *args, **kwargs):
            # Create a dummy file so open() can read it later
            with open(filename, 'wb') as f:
                f.write(b'dummy segment content')
        
        mock_subclip.write_videofile.side_effect = create_dummy_segment
        
        MockVideoFileClip.return_value = mock_clip
        
        # Setup mock post response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'ok'}
        mock_post.return_value = mock_response
        
        # Make request
        response = client.post('/upload_and_cut', data=data, content_type='multipart/form-data')
        
        # Assertions
        assert response.status_code == 200
        # Check response structure
        json_data = response.get_json()
        assert json_data['status'] == 'processed'
        assert len(json_data['results']) == 3
        
        # Verify calls
        assert MockVideoFileClip.called
        # Check subclipped calls
        args_list = mock_clip.subclipped.call_args_list
        assert len(args_list) == 3
        assert args_list[0][0] == (0, 3)
        assert args_list[1][0] == (3, 6)
        assert args_list[2][0] == (6, 7)
        
        assert mock_subclip.write_videofile.call_count == 3
        assert mock_post.call_count == 3
