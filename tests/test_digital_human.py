import os
import sys
import json
import random

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import modify_digital_human_workflow

def test_modify_workflow():
    # 1. Load the original workflow
    workflow_path = os.path.join('comfyapi', '数字人video_humo.json')
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 2. Define inputs
    image_filename = "test_character.png"
    audio_filename = "test_audio.wav"
    
    # 3. Modify
    modified_workflow = modify_digital_human_workflow(workflow, image_filename, audio_filename)
    
    # 4. Assertions
    # Check Image Node (49)
    assert modified_workflow["49"]["inputs"]["image"] == image_filename, "Image filename not updated"
    
    # Check Audio Node (58)
    assert modified_workflow["58"]["inputs"]["audio"] == audio_filename, "Audio filename not updated"
    
    # Check Seed Randomization (Node 64)
    # Note: original seed is 1067760026265042. We check if it's changed (very likely)
    # and within range.
    new_seed = modified_workflow["64"]["inputs"]["seed"]
    assert isinstance(new_seed, int), "Seed should be an integer"
    assert 1 <= new_seed <= 1000000000000000, "Seed out of range"
    
    print("Workflow modification test passed!")

if __name__ == "__main__":
    test_modify_workflow()
