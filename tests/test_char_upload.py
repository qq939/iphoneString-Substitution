import pytest
import io
import os
from unittest.mock import MagicMock, patch
from PIL import Image

# Patch imports
with patch('comfy_utils.ComfyUIClient'):
    from app import app, UPLOAD_FOLDER

@pytest.fixture
def client():
    app.config['TESTING'] = True
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with app.test_client() as client:
        yield client

def test_upload_character(client):
    # Create a dummy image using PIL
    img = Image.new('RGB', (100, 100), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    
    with patch('app.obs_utils.upload_file') as mock_upload:
        mock_upload.return_value = "http://obs.dimond.top/character.png"
        
        data = {
            'image': (img_byte_arr, 'test.jpg')
        }
        
        response = client.post('/upload_character', data=data, content_type='multipart/form-data')
        
        if response.status_code != 200:
            print(response.get_json())
            
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['status'] == 'success'
        assert json_data['url'] == "http://obs.dimond.top/character.png"
        
        # Verify upload was called with a PNG path
        args, _ = mock_upload.call_args
        uploaded_path = args[0]
        assert uploaded_path.endswith('character.png')
        
        # Verify conversion happened (we can check if open(uploaded_path) is PNG, 
        # but the file is deleted in the route. We can trust the flow if response is ok 
        # and mock was called correctly.)
