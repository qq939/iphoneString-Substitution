import unittest
from unittest.mock import patch
import sys
import os

sys.path.append(os.getcwd())
import ffmpeg_utils


class TestFfmpegResize(unittest.TestCase):
    @patch("ffmpeg_utils.subprocess.run")
    def test_resize_video_max_side_800_aspect_ratio(self, mock_run):
        ffmpeg_utils.resize_video("in.mp4", "out.mp4")
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        self.assertIn("-vf", cmd)
        vf_index = cmd.index("-vf") + 1
        scale_arg = cmd[vf_index]
        self.assertIn("800", scale_arg)
        self.assertIn("if(gt(iw,ih),800,-2)", scale_arg)
        self.assertIn("if(gt(iw,ih),-2,800)", scale_arg)


if __name__ == "__main__":
    unittest.main()
