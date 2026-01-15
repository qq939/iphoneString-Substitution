import os
import sys
import json
import random
import math

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import modify_digital_human_workflow, modify_extend_video_workflow

def test_modify_extend_workflow():
    # 1. Load the extend video workflow
    workflow_path = os.path.join('comfyapi', '扩展视频到音频长度.json')
    if not os.path.exists(workflow_path):
        print(f"Skipping test_modify_extend_workflow: {workflow_path} not found")
        return

    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 2. Define inputs
    video_filename = "test_input_video.mp4"
    audio_filename = "test_audio.wav"
    
    # 3. Modify
    modified_workflow = modify_extend_video_workflow(workflow, video_filename, audio_filename)
    
    # 4. Assertions
    # Check Video Node (14)
    assert modified_workflow["14"]["inputs"]["video"] == video_filename, "Video filename not updated"
    
    # Check Audio Node (66)
    assert modified_workflow["66"]["inputs"]["audio"] == audio_filename, "Audio filename not updated"
    
    print("Extend workflow modification test passed!")

def test_modify_workflow():
    # 1. Load the original workflow
    workflow_path = os.path.join('comfyapi', '数字人video_humo.json')
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 2. Define inputs
    image_filename = "test_character.png"
    audio_filename = "test_audio.wav"
    audio_duration = 5.0 # seconds
    
    # 3. Modify
    modified_workflow = modify_digital_human_workflow(workflow, image_filename, audio_filename, audio_duration)
    
    # 4. Assertions
    # Check Image Node (49)
    assert modified_workflow["49"]["inputs"]["image"] == image_filename, "Image filename not updated"
    
    # Check Audio Node (58)
    assert modified_workflow["58"]["inputs"]["audio"] == audio_filename, "Audio filename not updated"
    
    # Check Seed Randomization (Node 64)
    # New logic: Seed should be 0
    new_seed = modified_workflow["64"]["inputs"]["seed"]
    assert new_seed == 0, "Seed should be 0"
    
    # Check Frame Length Calculation
    fps = workflow["60"]["inputs"]["fps"]
    expected_length = int(math.ceil(audio_duration * fps))
    
    new_length = modified_workflow["65"]["inputs"]["length"]
    assert new_length == expected_length, f"Expected length {expected_length}, got {new_length}"
    
    print("Workflow modification test passed!")

def test_audio_slicing_logic():
    # This test simulates the audio slicing logic without actually processing heavy files
    total_duration = 25 # seconds
    segment_duration = 5 # Updated to 5s
    
    import math
    num_segments = math.ceil(total_duration / segment_duration)
    
    assert num_segments == 5, f"Expected 5 segments, got {num_segments}"
    
    # Verify time ranges
    segments = []
    for i in range(num_segments):
        start_time = i * segment_duration
        end_time = min((i + 1) * segment_duration, total_duration)
        segments.append((start_time, end_time))
        
    assert segments[0] == (0, 5)
    assert segments[1] == (5, 10)
    assert segments[2] == (10, 15)
    assert segments[3] == (15, 20)
    assert segments[4] == (20, 25)
    
    print("Audio slicing logic test passed!")

if __name__ == "__main__":
    test_modify_workflow()
    test_modify_extend_workflow()
    test_audio_slicing_logic()
