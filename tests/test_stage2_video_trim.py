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

    mock_clip = MagicMock()
    mock_clip.duration = 12
    mock_subclip = MagicMock()
    mock_clip.subclip.return_value = mock_subclip

    with patch('app.os.path.exists', return_value=True), \
         patch('app.VideoFileClip', return_value=mock_clip) as mock_videofileclip, \
         patch('app.comfy_utils.client.upload_file', side_effect=Exception("stop_after_video_upload")) as mock_upload:
        app.process_digital_human_video(audio_path, input_video_path=input_video_path)

        mock_videofileclip.assert_called_with(input_video_path)
        mock_clip.subclip.assert_called_with(0, 3)
        assert mock_subclip.write_videofile.called

        uploaded_arg = mock_upload.call_args[0][0]
        assert uploaded_arg != input_video_path
        assert uploaded_arg.endswith(".mp4")
