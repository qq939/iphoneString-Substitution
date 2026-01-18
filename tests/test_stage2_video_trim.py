import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch('comfy_utils.ComfyUIClient'):
    import app


def test_stage2_trims_video_to_first_3_seconds_before_upload():
    input_video_path = os.path.join(app.UPLOAD_FOLDER, "big_input.mp4")
    audio_path = os.path.join(app.UPLOAD_FOLDER, "audio.wav")

    with patch('app.os.path.exists', return_value=True), \
         patch('app.ffmpeg_utils.get_video_info', return_value={'duration': 12}) as mock_get_info, \
         patch('app.ffmpeg_utils.cut_video') as mock_cut_video, \
         patch('app.comfy_utils.client.upload_file', side_effect=Exception("stop_after_video_upload")) as mock_upload, \
         patch('app.os.remove'):
        try:
            app.process_digital_human_video(audio_path, input_video_path=input_video_path)
        except Exception as e:
            assert "stop_after_video_upload" in str(e)

        mock_get_info.assert_called_with(input_video_path)
        assert mock_cut_video.called
        args, kwargs = mock_cut_video.call_args
        assert args[0] == input_video_path
        trimmed_path = args[1]
        assert trimmed_path != input_video_path
        assert trimmed_path.endswith(".mp4")
        assert args[2] == 0
        assert args[3] == 3
        uploaded_arg = mock_upload.call_args[0][0]
        assert uploaded_arg == trimmed_path
