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
    video_content = b'fake video content'
    filename = 'test_video.mp4'

    with patch('app.ffmpeg_utils.get_video_info', return_value={'duration': 8.0, 'has_audio': True}) as mock_get_info, \
         patch('app.ffmpeg_utils.extract_audio') as mock_extract_audio, \
         patch('app.ffmpeg_utils.cut_video') as mock_cut_video, \
         patch('app.ffmpeg_utils.concatenate_videos') as mock_concat, \
         patch('app.ffmpeg_utils.merge_audio_video') as mock_merge, \
         patch('app.comfy_utils.client') as mock_client, \
         patch('app.comfy_utils.queue_workflow_template') as mock_queue_template, \
         patch('app.comfy_utils.check_status') as mock_check_status, \
         patch('app.comfy_utils.download_result') as mock_download_result, \
         patch('app.obs_utils.upload_file', return_value="http://obs/final.mp4") as mock_upload, \
         patch('app.time.sleep', return_value=None), \
         patch('app.os.path.exists', return_value=True), \
         patch('app.os.remove'):

        mock_client.upload_file.side_effect = [
            {'name': 'seg_0.mp4'},
            {'name': 'character.png'},
            {'name': 'seg_1.mp4'},
            {'name': 'character.png'}
        ]

        mock_queue_template.side_effect = [
            ("task_1", "server1", None),
            ("task_2", "server1", None)
        ]

        def check_status_side_effect(task_id, server=None):
            if task_id in ("task_1", "task_2"):
                return "SUCCEEDED", {'filename': f"{task_id}.mp4", 'subfolder': '', 'type': 'output'}
            return "PENDING", None

        mock_check_status.side_effect = check_status_side_effect

        def download_side_effect(result, folder, server=None):
            path = os.path.join(folder, result['filename'])
            return path

        mock_download_result.side_effect = download_side_effect

        with patch('app.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b'fake character image']
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value.__enter__.return_value = mock_response

            data = {
                'video': (io.BytesIO(video_content), filename)
            }
            response = client.post('/upload_and_cut', data=data, content_type='multipart/form-data')

            assert response.status_code == 200
            json_data = response.get_json()
            assert 'group_id' in json_data
            group_id = json_data['group_id']

        start_time = time.time()
        final_status = None

        while time.time() - start_time < 5:
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
        assert final_status['status'] == 'completed'
        assert final_status['final_url'] == "http://obs/final.mp4"

        assert mock_queue_template.call_count == 2
        assert mock_concat.called
        assert mock_upload.called
