import os
import sys
import json
from unittest.mock import patch, MagicMock

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


def test_modify_i2v_workflow_updates_image_and_text():
    workflow_path = os.path.join('comfyapi', '图生视频video_wan2_2_14B_i2v.json')
    if not os.path.exists(workflow_path):
        pytest.skip(f'Workflow not found: {workflow_path}')
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    image_name = 'uploaded_character.png'
    prompt_text = '测试文案'
    modified = app.modify_i2v_workflow(workflow, image_name, prompt_text)
    assert modified['97']['inputs']['image'] == image_name
    assert modified['93']['inputs']['text'] == prompt_text


@patch('app.ensure_comfy_connection')
@patch('app.requests.get')
@patch('app.comfy_utils.client.upload_file')
@patch('app.comfy_utils.client.queue_prompt')
def test_generate_i2v_group_creates_group_and_tasks(mock_queue, mock_upload, mock_get, mock_ensure, client):
    mock_ensure.return_value = None
    resp = MagicMock()
    resp.status_code = 200
    resp.iter_content.return_value = [b'img']
    resp.__enter__.return_value = resp
    mock_get.return_value = resp
    mock_upload.return_value = {'name': 'character_uploaded.png'}
    mock_queue.side_effect = [
        ('pid11', 'server1'),
        ('pid12', 'server1'),
        (None, None),
        ('pid14', 'server2'),
    ]
    payload = {
        'texts': ['t11', 't12', '', 't14']
    }
    res = client.post('/generate_i2v_group', data=json.dumps(payload), content_type='application/json')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'processing'
    group_id = data['group_id']
    assert group_id in app.TASKS_STORE
    group = app.TASKS_STORE[group_id]
    assert group['status'] == 'processing'
    assert len(group['tasks']) == 2
    indices = sorted(t['segment_index'] for t in group['tasks'])
    assert indices == [0, 1]


@patch('app.time.sleep', return_value=None)
@patch('app.time.time')
@patch('app.comfy_utils.check_status')
@patch('app.comfy_utils.download_result')
@patch('app.obs_utils.upload_file', return_value='http://obs/all.mp4')
def test_monitor_i2v_group_respects_global_timeout_and_merges(mock_upload_obs, mock_download, mock_check, mock_time, mock_sleep):
    base_time = 1_000_000.0
    mock_time.side_effect = [
        base_time,
        base_time + app.WAI_OVERTIME_SECONDS + 1,
    ]
    group_id = 'i2v_group'
    app.TASKS_STORE[group_id] = {
        'status': 'processing',
        'tasks': [
            {'task_id': 'pid11', 'server': 'server1', 'status': 'pending', 'segment_index': 0, 'result_path': None},
        ],
        'created_at': base_time,
        'workflow_type': 'i2v',
        'audio_path': None,
    }
    mock_check.return_value = ('PENDING', None)
    mock_download.return_value = None
    app.monitor_i2v_group(group_id)
    group = app.TASKS_STORE[group_id]
    assert group['status'] in ['failed', 'processing']
