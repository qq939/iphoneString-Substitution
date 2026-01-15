import unittest
import os
import json
import sys
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import modify_extend_video_workflow, generate_1s_video

class TestExtendVideoWorkflow(unittest.TestCase):
    def test_modify_extend_video_workflow(self):
        # Mock workflow
        workflow = {
            "14": {"inputs": {"video": "old.mp4"}},
            "66": {"inputs": {"audio": "old.wav"}}
        }
        
        new_video = "new_video.mp4"
        new_audio = "new_audio.wav"
        
        modified = modify_extend_video_workflow(workflow, new_video, new_audio)
        
        self.assertEqual(modified["14"]["inputs"]["video"], new_video)
        self.assertEqual(modified["66"]["inputs"]["audio"], new_audio)

    @patch('app.ImageClip')
    def test_generate_1s_video(self, mock_image_clip):
        # Mock MoviePy
        mock_clip_instance = MagicMock()
        mock_image_clip.return_value = mock_clip_instance
        mock_clip_instance.set_duration.return_value = mock_clip_instance
        mock_clip_instance.set_fps.return_value = mock_clip_instance
        
        image_path = "test.png"
        output_path = "test.mp4"
        
        generate_1s_video(image_path, output_path)
        
        mock_image_clip.assert_called_with(image_path)
        mock_clip_instance.set_duration.assert_called_with(1)
        mock_clip_instance.set_fps.assert_called_with(25)
        mock_clip_instance.write_videofile.assert_called()
        args, kwargs = mock_clip_instance.write_videofile.call_args
        self.assertEqual(args[0], output_path)
        self.assertEqual(kwargs['fps'], 25)

if __name__ == '__main__':
    unittest.main()
