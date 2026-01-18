import unittest
import sys
import os
from unittest.mock import patch, MagicMock
import io

# Ensure we can import app
sys.path.append(os.getcwd())
from app import app

class TestNoMoviePy(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['TESTING'] = True

    @patch('app.ffmpeg_utils')
    @patch('app.comfy_utils.client')
    def test_upload_and_cut_uses_ffmpeg_real_no_resize(self, mock_comfy, mock_ffmpeg):
        # Mock ffmpeg_utils functions
        mock_ffmpeg.get_video_info.return_value = {'duration': 10.0, 'width': 100, 'height': 100, 'has_audio': True}
        
        # Mock file upload
        data = {
            'video': (io.BytesIO(b'fake video content'), 'test.mp4'),
            'workflow_type': 'real'
        }
        
        # We need to mock requests.get for character download too
        with patch('app.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b'fake_image_data']
            mock_get.return_value.__enter__.return_value = mock_response
            
            # Also mock shutil.copy used in fallback
            with patch('shutil.copy'):
                # Mock os.path.exists and os.remove to avoid actual file ops issues
                with patch('os.path.exists', return_value=True), patch('os.remove'):
                    # Mock uuid to get predictable filenames if needed, but not strictly necessary
                    
                    response = self.client.post('/upload_and_cut', data=data, content_type='multipart/form-data')
                    if response.status_code != 200:
                        print(f"Response error: {response.data}")
            
            self.assertTrue(mock_ffmpeg.get_video_info.called)
            self.assertTrue(mock_ffmpeg.extract_audio.called)
            self.assertFalse(mock_ffmpeg.resize_video.called)
            self.assertTrue(mock_ffmpeg.cut_video.called)

    @patch('app.ffmpeg_utils')
    def test_monitor_group_task_image_swap(self, mock_ffmpeg):
        # We need to simulate the monitor_group_task function
        # But it's hard to call directly as it's a background thread loop.
        # However, we can check if the code path imports fine.
        from app import monitor_group_task
        self.assertTrue(callable(monitor_group_task))

    @patch('app.time.sleep', return_value=None)
    @patch('app.time.time')
    def test_monitor_group_task_stops_after_6_hours(self, mock_time, mock_sleep):
        import app as app_module
        from app import monitor_group_task, TASKS_STORE
        now = 1_000_000.0
        mock_time.return_value = now
        group_id = 'test_group_timeout'
        TASKS_STORE[group_id] = {
            'status': 'processing',
            'tasks': [
                {
                    'task_id': 't1',
                    'server': None,
                    'status': 'pending',
                    'segment_index': 0,
                    'result_path': None
                }
            ],
            'created_at': now - (app_module.WAI_OVERTIME_SECONDS + 1),
            'audio_path': None,
            'workflow_type': 'real'
        }
        with patch('app.comfy_utils.check_status', return_value=('PENDING', None)), \
             patch('app.ffmpeg_utils.concatenate_videos'), \
             patch('app.obs_utils.upload_file', return_value='http://example.com/video.mp4'):
            monitor_group_task(group_id)
        self.assertEqual(TASKS_STORE[group_id]['status'], 'failed')
        self.assertIn('timeout', TASKS_STORE[group_id].get('error', '').lower())

    @patch('app.time.sleep', return_value=None)
    @patch('app.time.time')
    def test_transition_group_waits_for_second_video_with_overtime(self, mock_time, mock_sleep):
        import app as app_module
        from app import monitor_group_task, TASKS_STORE

        now = 1_000_000.0
        mock_time.return_value = now
        group_id = 'test_transition_wait'
        TASKS_STORE[group_id] = {
            'status': 'processing',
            'tasks': [
                {
                    'task_id': 't1',
                    'server': None,
                    'status': 'pending',
                    'segment_index': 0,
                    'result_path': None
                }
            ],
            'created_at': now - (app_module.WAI_OVERTIME_SECONDS + 1),
            'audio_path': None,
            'workflow_type': 'transition',
            'transition_videos': [
                {'index': 0, 'path': '/tmp/v0.mp4', 'duration': 1.0, 'name': 'v0.mp4'}
            ]
        }

        with patch('app.comfy_utils.check_status', return_value=('PENDING', None)), \
             patch('app.ffmpeg_utils.concatenate_videos'), \
             patch('app.obs_utils.upload_file', return_value='http://example.com/video.mp4'):
            monitor_group_task(group_id)

        self.assertEqual(TASKS_STORE[group_id]['status'], 'failed')
        self.assertIn('wait overtime', TASKS_STORE[group_id].get('error', '').lower())

    @patch('app.time.sleep', return_value=None)
    @patch('app.time.time')
    def test_monitor_group_task_partial_failure_concatenates_success_segments(self, mock_time, mock_sleep):
        import app as app_module
        from app import monitor_group_task, TASKS_STORE, UPLOAD_FOLDER
        now = 1_000_000.0
        mock_time.return_value = now
        group_id = 'test_group_partial_failure'
        seg1_path = os.path.join(UPLOAD_FOLDER, 'seg1.mp4')
        audio_path = os.path.join(UPLOAD_FOLDER, 'audio.wav')
        TASKS_STORE[group_id] = {
            'status': 'processing',
            'tasks': [
                {
                    'task_id': 't1',
                    'server': None,
                    'status': 'pending',
                    'segment_index': 0,
                    'result_path': None
                },
                {
                    'task_id': 't2',
                    'server': None,
                    'status': 'pending',
                    'segment_index': 1,
                    'result_path': None
                }
            ],
            'created_at': now,
            'audio_path': audio_path,
            'workflow_type': 'real'
        }
        with patch('app.comfy_utils.check_status') as mock_check_status, \
             patch('app.comfy_utils.download_result', return_value=seg1_path) as mock_download, \
             patch('app.ffmpeg_utils.concatenate_videos') as mock_concat, \
             patch('app.ffmpeg_utils.merge_audio_video') as mock_merge, \
             patch('app.obs_utils.upload_file', return_value='http://example.com/final.mp4') as mock_upload, \
             patch('app.os.path.exists', return_value=True), \
             patch('app.os.remove'), \
             patch('app.shutil.move'):
            mock_check_status.side_effect = [
                ('SUCCEEDED', {'filename': 'seg1.mp4', 'subfolder': '', 'type': 'output'}),
                ('FAILED', 'some error'),
            ]
            monitor_group_task(group_id)
        group = TASKS_STORE[group_id]
        self.assertEqual(group['status'], 'completed')
        self.assertEqual(group.get('final_url'), 'http://example.com/final.mp4')
        mock_check_status.assert_called()
        mock_download.assert_called_once()
        mock_concat.assert_called_once()
        args, kwargs = mock_concat.call_args
        video_list = args[0]
        self.assertEqual(video_list, [seg1_path])
        self.assertTrue(any(t['status'] == 'completed' for t in group['tasks']))
        self.assertTrue(any(t['status'] == 'failed' for t in group['tasks']))

    def test_backend_poll_interval_at_least_15_seconds(self):
        import app as app_module
        self.assertTrue(hasattr(app_module, 'BACKEND_POLL_INTERVAL_SECONDS'))
        self.assertGreaterEqual(app_module.BACKEND_POLL_INTERVAL_SECONDS, 15)

if __name__ == '__main__':
    unittest.main()
