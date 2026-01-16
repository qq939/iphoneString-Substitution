import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch('comfy_utils.ComfyUIClient'):
    import app


@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with app.app.test_client() as client:
        yield client


def test_upload_audio_without_file_sets_input_video_path_none(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b'fake wav bytes']

    with patch('app.ensure_comfy_connection') as mock_ensure, \
         patch('app.requests.get', return_value=mock_response) as mock_get, \
         patch('app.comfy_utils.client.upload_file', return_value={'name': 'uploaded_tone.wav'}) as mock_upload, \
         patch('app.comfy_utils.client.queue_prompt', return_value='prompt_123') as mock_queue:
        res = client.post('/upload_audio', data={'text': 'hello'})
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'success'
        assert data['prompt_id'] == 'prompt_123'

        assert 'prompt_123' in app.AUDIO_TASKS
        assert app.AUDIO_TASKS['prompt_123']['input_video_path'] is None

        assert mock_ensure.called
        assert mock_get.called
        assert mock_upload.called
        assert mock_queue.called
