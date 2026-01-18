
import os
import time
import uuid
import sys
import logging
import shutil
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock ffmpeg_utils to bypass missing ffmpeg binary
def mock_resize_video(input_path, output_path, *args, **kwargs):
    logger.info(f"Mock resize_video: {input_path} -> {output_path}")
    shutil.copy(input_path, output_path)

def mock_get_video_info(file_path):
    logger.info(f"Mock get_video_info: {file_path}")
    return {'duration': 4.0, 'width': 640, 'height': 640, 'has_audio': False}

def mock_extract_frame(video_path, output_path, time_offset):
    logger.info(f"Mock extract_frame: {video_path} -> {output_path} at {time_offset}")
    # Copy a dummy image or create one
    if os.path.exists("test_img.png"):
        shutil.copy("test_img.png", output_path)
    else:
        # Create a dummy file
        with open(output_path, 'wb') as f:
            f.write(b'fake image content')

def mock_concatenate_videos(video_paths, output_path):
    logger.info(f"Mock concatenate_videos: {video_paths} -> {output_path}")
    # Just copy the first video as result
    if video_paths:
        shutil.copy(video_paths[0], output_path)
    else:
        with open(output_path, 'wb') as f:
            f.write(b'fake video')

def mock_merge_audio_video(video_path, audio_path, output_path, loop_audio=False):
    logger.info(f"Mock merge_audio_video: {video_path} + {audio_path} -> {output_path}")
    shutil.copy(video_path, output_path)

def mock_extract_audio(video_path, output_path):
    logger.info(f"Mock extract_audio: {video_path} -> {output_path}")
    with open(output_path, 'wb') as f:
        f.write(b'fake audio')

# Apply mocks
app.ffmpeg_utils.resize_video = mock_resize_video
app.ffmpeg_utils.get_video_info = mock_get_video_info
app.ffmpeg_utils.extract_frame = mock_extract_frame
app.ffmpeg_utils.concatenate_videos = mock_concatenate_videos
app.ffmpeg_utils.merge_audio_video = mock_merge_audio_video
app.ffmpeg_utils.extract_audio = mock_extract_audio

def run_real_test():
    # Use the Flask test client
    client = app.app.test_client()
    
    # Generate a group_id (simulating frontend behavior)
    group_id = str(uuid.uuid4())
    logger.info(f"Starting real transition test with Group ID: {group_id}")
    
    video_files = [
        "tests/20260117213002all.mp4",
        "tests/20260117213444all.mp4",
        "tests/20260117214002all.mp4",
        "tests/20260117214452all.mp4"
    ]
    
    # Verify files exist
    for v in video_files:
        if not os.path.exists(v):
            logger.error(f"Video file not found: {v}")
            # create dummy files if not exist for testing
            logger.info(f"Creating dummy video file: {v}")
            with open(v, 'wb') as f:
                f.write(b'fake video content')
            
    # Upload videos
    for i, video_path in enumerate(video_files):
        logger.info(f"Uploading video {i+1}/{len(video_files)}: {video_path}")
        with open(video_path, 'rb') as f:
            data = {
                'video': (f, os.path.basename(video_path)),
                'group_id': group_id
            }
            response = client.post('/upload_transition_video', data=data, content_type='multipart/form-data')
            
            if response.status_code != 200:
                logger.error(f"Upload failed: {response.status_code} - {response.data}")
                return
            
            json_data = response.get_json()
            logger.info(f"Upload response: {json_data}")
            
            # Simulate a small delay between uploads as in real user interaction
            time.sleep(1)

    # Monitor status
    logger.info("All videos uploaded. Monitoring status...")
    
    # Check which server was selected
    logger.info(f"ComfyUI Client Base URL: {app.comfy_utils.client.base_url}")
    
    start_time = time.time()
    while True:
        response = client.get(f'/check_group_status/{group_id}')
        status_data = response.get_json()
        
        status = status_data.get('status')
        progress = status_data.get('progress')
        error = status_data.get('error')
        tasks = status_data.get('tasks', [])
        
        logger.info(f"Status: {status}, Progress: {progress}")
        for task in tasks:
            logger.info(f"  Task {task.get('task_id')}: {task.get('status')} (Server: {task.get('server')})")
        
        if status == 'completed':
            logger.info(f"Task completed! Final URL: {status_data.get('final_url')}")
            break
        elif status == 'failed':
            logger.error(f"Task failed: {error}")
            break
            
        if time.time() - start_time > 600: # 10 minutes timeout
            logger.error("Test timed out")
            break
            
        time.sleep(5)

if __name__ == "__main__":
    try:
        run_real_test()
    except KeyboardInterrupt:
        print("Test interrupted")
