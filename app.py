from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
import os
import re
import urllib
import requests
import math
import uuid
import threading
import time
import shutil
import json
from datetime import datetime
from PIL import Image
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, afx
import comfy_utils
import obs_utils

# Add local bin directory to PATH for ffmpeg/ffprobe
local_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
if os.path.exists(local_bin):
    os.environ["PATH"] += os.pathsep + local_bin

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

app = Flask(__name__)
SUBSTITUTION_FILE = 'langchain/substitution.txt'

# Video Cut Config
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ComfyUI Status
COMFY_STATUS = {
    'status': 'unknown',
    'last_checked': 0
}

def check_comfy_status():
    """Background task to check ComfyUI status periodically"""
    while True:
        try:
            # We assume comfy_utils has a way to check connection or we just check the server
            # For now, let's just use comfy_utils.client.check_connection() if available
            # Or just check if we can reach it
            if comfy_utils.client.check_connection():
                if COMFY_STATUS['status'] != 'online':
                    print(f"ComfyUI is ONLINE at {comfy_utils.client.server_address}")
                COMFY_STATUS['status'] = 'online'
            else:
                if COMFY_STATUS['status'] != 'offline':
                    print("ComfyUI is OFFLINE")
                COMFY_STATUS['status'] = 'offline'
        except Exception as e:
            print(f"Error checking ComfyUI status: {e}")
            COMFY_STATUS['status'] = 'offline'
        COMFY_STATUS['last_checked'] = time.time()
        time.sleep(30)

# Start status checker
status_thread = threading.Thread(target=check_comfy_status, daemon=True)
status_thread.start()

# In-memory store for task groups
# Structure:
# {
#   "group_id": {
#       "status": "processing" | "completed" | "failed",
#       "tasks": [
#           {"task_id": "xxx", "status": "pending" | "completed" | "failed", "segment_index": 0, "result_path": "path/to/file"}
#       ],
#       "final_url": "http://...",
#       "error": "..."
#   }
# }
TASKS_STORE = {}

def modify_digital_human_workflow(workflow, image_filename, audio_filename):
    """
    Modifies the digital human video workflow JSON based on inputs.
    """
    # 1. Update Image (Node 49)
    if "49" in workflow and "inputs" in workflow["49"]:
        workflow["49"]["inputs"]["image"] = image_filename

    # 2. Update Audio (Node 58)
    if "58" in workflow and "inputs" in workflow["58"]:
        workflow["58"]["inputs"]["audio"] = audio_filename
        
    # 3. Randomize Seed (Node 64)
    import random
    if "64" in workflow and "inputs" in workflow["64"]:
        workflow["64"]["inputs"]["seed"] = random.randint(1, 1000000000000000)
        
    return workflow

def get_substitutions():
    if not os.path.exists(SUBSTITUTION_FILE):
        return ""
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def save_substitution(char):
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        strings = f.read()
    with open(SUBSTITUTION_FILE, 'w', encoding='utf-8') as f:
        stringset = set(strings)
        stringset.add(char)
        f.write(''.join(stringset))

def remove_substitution(char):
    if not os.path.exists(SUBSTITUTION_FILE):
        return
    content = ""
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    # 删除所有匹配的字符
    new_content = content.replace(char, '')
    with open(SUBSTITUTION_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

def modify_audio_workflow(workflow, text, filename, emotions=None):
    """
    Modifies the audio workflow JSON based on inputs.
    """
    # 1. Update Text (Node 27)
    if "27" in workflow and "inputs" in workflow["27"]:
        workflow["27"]["inputs"]["text"] = text

    # 2. Update Audio File (Node 29)
    if "29" in workflow and "inputs" in workflow["29"]:
        workflow["29"]["inputs"]["audio"] = filename
        
    # 3. Randomize seed (Node 27)
    import random
    if "27" in workflow and "inputs" in workflow["27"]:
        # Max seed for 32-bit/safe integer in some contexts is 2^32 - 1 = 4294967295
        # The error says "Value ... bigger than max of 4294967295"
        workflow["27"]["inputs"]["seed"] = random.randint(1, 4294967295)

    # 4. Update Emotions (Node 47)
    # Emotions list: Happy, Angry, Sad, Fear, Hate, Low, Surprise, Neutral
    all_emotions = ["Happy", "Angry", "Sad", "Fear", "Hate", "Low", "Surprise", "Neutral"]
    if "47" in workflow and "inputs" in workflow["47"]:
        if emotions:
            for emo in all_emotions:
                if emo in emotions:
                    workflow["47"]["inputs"][emo] = 0.75
                else:
                    workflow["47"]["inputs"][emo] = 0
        else:
            # Reset all to 0 if no emotions provided
            for emo in all_emotions:
                workflow["47"]["inputs"][emo] = 0
        
    return workflow

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        text = request.form.get('text')
        action = request.form.get('action')
        
        if text:
            # 取第一个字符
            char = text[0]
            if action == 'add':
                save_substitution(char)
            elif action == 'remove':
                remove_substitution(char)
        return redirect(url_for('index'))
    
    substitutions = get_substitutions()
    return render_template('index.html', substitutions=substitutions)

def core_replace(text):
    # ========== 直接硬编码替换字符串，写在这里 ==========
    hard_encoded = ["登录领番茄.*", 
                    "继续播放.*",
                    r"\d{2}:\d{2}.*", 
                    r"[０-９\d]*[／/][０-９\d]{3,5}.*", 
                    r"原进度.*从本页听"]
    # 遍历所有替换规则
    for pattern in hard_encoded:
        # 用正则替换（re.sub 支持正则，且忽略换行/多行匹配）
        text = re.sub(pattern, "", text, flags=re.MULTILINE)

    # ========== 原有替换逻辑 ==========
    substitutions = get_substitutions()
    for char in substitutions:
        text = text.replace(char, '')
    return text

@app.route('/replace', methods=['POST'])
def replace():
    # ========== 核心修改：解析JSON数据 ==========
    try:
        # 直接解析JSON请求体，自动保留换行符/中文
        json_data = request.get_json(force=True)
        # 获取text参数（默认空字符串）
        text = json_data.get('text', '')
    except Exception as e:
        # 解析失败时返回错误
        return Response(
            response="请传入JSON格式数据",
            status=400,
            mimetype='text/plain; charset=utf-8'
        )
    print("原始文本:\n",text,flush=True)
    text = core_replace(text)
    print("替换后文本:\n",text,flush=True)

    # 方案1：返回纯文本（适配Shortcuts直接取文本）【推荐】
    return Response(
        response=text,
        status=200,
        mimetype='text/plain; charset=utf-8'
    )

@app.route('/comfy_status')
def comfy_status():
    return jsonify(COMFY_STATUS)

@app.route('/upload_character', methods=['POST'])
def upload_character():
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    # Check extension
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ['jpg', 'jpeg', 'png', 'webp']:
        return jsonify({'error': 'Invalid file type. Only jpg, png, webp allowed.'}), 400

    try:
        # Save uploaded file temporarily
        temp_path = os.path.join(UPLOAD_FOLDER, f"temp_char_{uuid.uuid4()}.{ext}")
        file.save(temp_path)
        
        # Convert to PNG
        img = Image.open(temp_path)
        png_filename = "character.png"
        png_path = os.path.join(UPLOAD_FOLDER, png_filename)
        img.save(png_path, "PNG")
        
        # Upload to OBS
        obs_url = obs_utils.upload_file(png_path, png_filename, mime_type='image/png')
        
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(png_path):
            os.remove(png_path)
            
        if obs_url:
            return jsonify({'status': 'success', 'url': obs_url, 'message': 'Character updated successfully'})
        else:
            return jsonify({'error': 'Failed to upload to OBS'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    # Support multiple formats
    allowed_extensions = {'mov', 'mp4', 'mp3', 'wav', 'flac'}
    
    file = request.files.get('file')
    text = request.form.get('text', '')
    emotions = request.form.getlist('emotions') # Get list of selected emotions
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400

    try:
        wav_filename = f"tone_{uuid.uuid4()}.wav"
        wav_path = os.path.join(UPLOAD_FOLDER, wav_filename)
        
        # Check if file is provided and valid
        if file and file.filename != '':
            original_filename = file.filename
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
            
            if ext not in allowed_extensions:
                return jsonify({'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'}), 400
                
            temp_path = os.path.join(UPLOAD_FOLDER, f"temp_audio_{uuid.uuid4()}.{ext}")
            file.save(temp_path)
            
            # Convert to wav
            if AudioSegment:
                try:
                    audio = AudioSegment.from_file(temp_path)
                    audio.export(wav_path, format="wav")
                except Exception as e:
                    print(f"Audio conversion failed: {e}, attempting direct copy/rename if wav")
                    if ext == 'wav':
                        shutil.copy(temp_path, wav_path)
                    else:
                        # Clean up
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        return jsonify({'error': f'Audio conversion failed: {e}'}), 500
            else:
                 # Without pydub, we can only support wav really, or hope ComfyUI handles it if we just upload
                 # But we need "tone.wav" for the workflow? 
                 # Actually node 29 takes a filename.
                 # But let's stick to wav conversion requirement or simple copy if wav
                 if ext == 'wav':
                     shutil.copy(temp_path, wav_path)
                 else:
                     if os.path.exists(temp_path):
                        os.remove(temp_path)
                     return jsonify({'error': 'pydub not installed, cannot convert audio'}), 500
            
            # Clean up temp
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            # Upload to ComfyUI
            comfy_res = comfy_utils.client.upload_file(wav_path)
            if not comfy_res:
                return jsonify({'error': 'Failed to upload to ComfyUI'}), 500
            uploaded_filename = comfy_res.get('name')
            
        else:
            # No file provided, fallback to OBS tone.wav
            # Download tone.wav from OBS
            obs_tone_url = "http://obs.dimond.top/tone.wav"
            print(f"No file uploaded, downloading from OBS: {obs_tone_url}")
            
            try:
                wav_filename = f"tone_{uuid.uuid4()}.wav"
                wav_path = os.path.join(UPLOAD_FOLDER, wav_filename)
                
                # Download
                response = requests.get(obs_tone_url, stream=True)
                if response.status_code == 200:
                    with open(wav_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                else:
                    return jsonify({'error': f'Failed to download tone.wav from OBS: {response.status_code}'}), 500
                    
                # Upload to ComfyUI
                comfy_res = comfy_utils.client.upload_file(wav_path)
                if not comfy_res:
                    return jsonify({'error': 'Failed to upload downloaded tone.wav to ComfyUI'}), 500
                uploaded_filename = comfy_res.get('name')
                
                # Clean up local file
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                    
            except Exception as e:
                return jsonify({'error': f'Error handling OBS fallback: {str(e)}'}), 500

        # Load Workflow
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', 'audio_workflow.json')
        if not os.path.exists(workflow_path):
             return jsonify({"error": "Workflow file not found"}), 500
             
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        workflow = modify_audio_workflow(workflow, text, uploaded_filename, emotions)
        
        # Queue Prompt
        prompt_id = comfy_utils.client.queue_prompt(workflow)
        
        if prompt_id:
            # Clean up generated wav path if we created it
            if file and file.filename != '' and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
                
            return jsonify({"status": "success", "prompt_id": prompt_id})
        else:
            return jsonify({"error": "Failed to queue prompt"}), 500

    except Exception as e:
        # Print full traceback for debugging
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def process_digital_human_video(audio_path):
    """
    Background task to generate digital human video.
    """
    try:
        print(f"Starting digital human video generation for audio: {audio_path}")
        
        # 1. Prepare Inputs
        # Audio is already at audio_path (local)
        
        # Download Character from OBS
        character_url = "http://obs.dimond.top/character.png"
        character_filename = f"character_{uuid.uuid4()}.png"
        character_path = os.path.join(UPLOAD_FOLDER, character_filename)
        
        print(f"Downloading character from {character_url}...")
        try:
            response = requests.get(character_url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(character_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                print(f"Failed to download character: {response.status_code}")
                return
        except Exception as e:
            print(f"Error downloading character: {e}")
            return

        # 2. Upload to ComfyUI
        print("Uploading files to ComfyUI...")
        
        # Upload Audio
        comfy_audio = comfy_utils.client.upload_file(audio_path)
        if not comfy_audio:
            print("Failed to upload audio to ComfyUI")
            return
        uploaded_audio_name = comfy_audio.get('name')
        
        # Upload Image
        comfy_image = comfy_utils.client.upload_file(character_path)
        if not comfy_image:
            print("Failed to upload image to ComfyUI")
            return
        uploaded_image_name = comfy_image.get('name')
        
        # 3. Load and Modify Workflow
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '数字人video_humo.json')
        if not os.path.exists(workflow_path):
            print("Digital human workflow file not found")
            return
            
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        workflow = modify_digital_human_workflow(workflow, uploaded_image_name, uploaded_audio_name)
        
        # 4. Submit Task
        print("Submitting digital human task to ComfyUI...")
        prompt_id = comfy_utils.client.queue_prompt(workflow)
        
        if not prompt_id:
            print("Failed to queue digital human prompt")
            return
            
        print(f"Digital human task queued with ID: {prompt_id}")
        
        # 5. Monitor Task
        while True:
            time.sleep(30) # Check every 30 seconds
            
            try:
                status, result = comfy_utils.check_status(prompt_id)
                print(f"Digital human task {prompt_id} status: {status}")
                
                if status == 'SUCCEEDED':
                    # Download result
                    if isinstance(result, dict):
                        print("Task succeeded, downloading result...")
                        local_path = comfy_utils.download_result(result, UPLOAD_FOLDER)
                        
                        if local_path:
                            # Upload to OBS
                            output_filename = datetime.now().strftime("%Y%m%d%H%M%Sall.mp4")
                            print(f"Uploading result to OBS as {output_filename}...")
                            
                            obs_url = obs_utils.upload_file(local_path, output_filename, mime_type='video/mp4')
                            
                            if obs_url:
                                print(f"Digital human video successfully uploaded: {obs_url}")
                                
                                # Rename local file to match OBS name for /latest_video
                                local_renamed_path = os.path.join(UPLOAD_FOLDER, output_filename)
                                if os.path.exists(local_path):
                                    os.rename(local_path, local_renamed_path)
                            else:
                                print("Failed to upload digital human video to OBS")
                        else:
                            print("Failed to download digital human video result")
                    else:
                        print("Invalid digital human result format")
                    break
                    
                elif status == 'FAILED':
                    print(f"Digital human task failed: {result}")
                    break
                    
            except Exception as e:
                print(f"Error monitoring digital human task: {e}")
                # Don't break immediately on error, retry next loop
                
        # Cleanup
        if os.path.exists(character_path):
            os.remove(character_path)
            
    except Exception as e:
        print(f"Process digital human video error: {e}")
        import traceback
        traceback.print_exc()

@app.route('/check_audio_status/<prompt_id>', methods=['GET'])
def check_audio_status(prompt_id):
    try:
        status, result = comfy_utils.check_status(prompt_id)
        
        if status == 'SUCCEEDED':
            # Download result
            if isinstance(result, dict):
                local_path = comfy_utils.download_result(result, UPLOAD_FOLDER)
                if local_path:
                    # Upload to OBS
                    # Naming: YYYYMMDDHHMMSSaudio.flac
                    output_filename = datetime.now().strftime("%Y%m%d%H%M%Saudio.flac")
                    obs_url = obs_utils.upload_file(local_path, output_filename, mime_type='audio/flac')
                    
                    # Rename local file to match so latest_audio can find it
                    local_renamed_path = os.path.join(UPLOAD_FOLDER, output_filename)
                    if os.path.exists(local_path):
                        os.rename(local_path, local_renamed_path)
                    
                    if obs_url:
                        # Trigger Digital Human Video Generation (Stage 2)
                        # We do this in a background thread to avoid blocking the response
                        print(f"Audio upload successful. Triggering digital human video generation with {local_renamed_path}")
                        thread = threading.Thread(target=process_digital_human_video, args=(local_renamed_path,))
                        thread.daemon = True
                        thread.start()
                        
                        return jsonify({'status': 'completed', 'url': obs_url})
                    else:
                        return jsonify({'status': 'failed', 'error': 'Failed to upload to OBS'})
                else:
                    return jsonify({'status': 'failed', 'error': 'Failed to download result'})
            else:
                return jsonify({'status': 'failed', 'error': 'Invalid result format'})
        elif status == 'FAILED':
             return jsonify({'status': 'failed', 'error': str(result)})
        else:
             return jsonify({'status': status})
             
    except Exception as e:
        return jsonify({'status': 'failed', 'error': str(e)})

@app.route('/latest_audio', methods=['GET'])
def get_latest_audio():
    """
    Returns the URL of the latest generated audio from OBS based on naming convention.
    Naming convention: YYYYMMDDHHMMSSaudio.flac
    """
    try:
        # 1. Try to fetch from OBS directly (Stateless)
        latest_file = get_latest_file_from_obs('audio.flac')
        
        if latest_file:
            obs_url = f"http://obs.dimond.top/{latest_file}"
            return jsonify({'url': obs_url, 'filename': latest_file})
            
        # 2. Fallback to local
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('audio.flac')]
        if not files:
            return jsonify({'url': None})
            
        files.sort(reverse=True)
        latest_file = files[0]
        obs_url = f"http://obs.dimond.top/{latest_file}"
        
        return jsonify({'url': obs_url, 'filename': latest_file})
    except Exception as e:
        print(f"Error fetching latest audio: {e}")
        return jsonify({'error': str(e)}), 500

def monitor_group_task(group_id):
    """
    Background thread to monitor task status.
    """
    print(f"Starting monitor for group {group_id}")
    group_data = TASKS_STORE.get(group_id)
    if not group_data:
        print(f"Group {group_id} not found")
        return

    while True:
        all_done = True
        any_failed = False
        
        # Check each task
        for task in group_data['tasks']:
            if task['status'] == 'completed':
                continue
            
            if task['status'] == 'failed':
                any_failed = True
                continue
                
            # Check status from ComfyUI
            try:
                status, result = comfy_utils.check_status(task['task_id'])
                # print(f"Task {task['task_id']} status: {status}")
                
                if status == 'SUCCEEDED':
                    # Download result
                    if isinstance(result, dict):
                        local_path = comfy_utils.download_result(result, UPLOAD_FOLDER)
                        if local_path:
                            task['result_path'] = local_path
                            task['status'] = 'completed'
                        else:
                            task['status'] = 'failed'
                            task['error'] = 'Download failed'
                            any_failed = True
                    else:
                        task['status'] = 'failed'
                        task['error'] = 'Invalid result format'
                        any_failed = True
                        
                elif status == 'FAILED':
                    task['status'] = 'failed'
                    task['error'] = str(result)
                    any_failed = True
                else:
                    # PENDING or RUNNING
                    all_done = False
            except Exception as e:
                print(f"Error checking task {task['task_id']}: {e}")
                # Don't mark as failed immediately, maybe network glitch?
                # But for now let's not block forever
                # task['status'] = 'failed'
                # task['error'] = str(e)
                # any_failed = True
                all_done = False
        
        if any_failed:
            group_data['status'] = 'failed'
            group_data['error'] = 'One or more tasks failed'
            print(f"Group {group_id} failed")
            break
            
        if all_done:
            task_type = group_data.get('task_type', 'video_swap')
            
            if task_type == 'image_swap':
                print(f"Group {group_id} (Image Swap) all tasks done. Extracting frame...")
                try:
                    # For image swap, we expect only 1 task
                    if not group_data['tasks'] or not group_data['tasks'][0]['result_path']:
                        raise Exception("No result video found for image swap")
                        
                    result_path = group_data['tasks'][0]['result_path']
                    
                    if not os.path.exists(result_path):
                        raise Exception(f"Result video not found at {result_path}")
                        
                    # Extract 5th frame
                    # Frame 5 (0-indexed is 4)
                    # We can use moviepy or ffmpeg
                    # Let's use moviepy
                    clip = VideoFileClip(result_path)
                    
                    # Ensure video is long enough. If < 5 frames, take last one.
                    # fps is usually 25 or 30 from ComfyUI
                    # t = 5 / clip.fps if clip.fps else 5/25
                    # Or simpler: clip.get_frame(t)
                    
                    # Let's try to get frame at index 4 (5th frame)
                    # Time = 4 / clip.fps
                    t = 4.0 / clip.fps if clip.fps else 4.0/25.0
                    if t >= clip.duration:
                        t = clip.duration - 0.01 # Take last frame if shorter
                        
                    frame_path = os.path.join(UPLOAD_FOLDER, datetime.now().strftime("%Y%m%d%H%M%Sone.png"))
                    clip.save_frame(frame_path, t=t)
                    clip.close()
                    
                    # Upload to OBS
                    print(f"Uploading {frame_path} to OBS...")
                    obs_url = obs_utils.upload_file(frame_path, os.path.basename(frame_path), mime_type='image/png')
                    
                    if obs_url:
                        group_data['final_url'] = obs_url
                        group_data['status'] = 'completed'
                    else:
                        group_data['status'] = 'failed'
                        group_data['error'] = 'OBS upload failed'
                        
                except Exception as e:
                    print(f"Image swap post-processing error: {e}")
                    group_data['status'] = 'failed'
                    group_data['error'] = str(e)
                    
            else:
                # Video Swap Logic
                print(f"Group {group_id} all tasks done. Concatenating...")
                # Concatenate videos
                try:
                    # Sort by segment index
                    sorted_tasks = sorted(group_data['tasks'], key=lambda x: x['segment_index'])
                    clips = []
                    for t in sorted_tasks:
                        if t['result_path'] and os.path.exists(t['result_path']):
                            clips.append(VideoFileClip(t['result_path']))
                    
                    if clips:
                        final_clip = concatenate_videoclips(clips)
                        
                        # Merge audio back
                        audio_path = group_data.get('audio_path')
                        if audio_path and os.path.exists(audio_path):
                            try:
                                audio_clip = AudioFileClip(audio_path)
                                video_duration = final_clip.duration
                                audio_duration = audio_clip.duration
                                
                                if audio_duration < video_duration:
                                    # Loop audio
                                    audio_clip = afx.audio_loop(audio_clip, duration=video_duration)
                                else:
                                    # Cut audio
                                    audio_clip = audio_clip.subclip(0, video_duration)
                                    
                                final_clip = final_clip.set_audio(audio_clip)
                                print(f"Merged audio from {audio_path}")
                            except Exception as e:
                                print(f"Failed to merge audio: {e}")
                        
                        output_filename = datetime.now().strftime("%Y%m%d%H%M%Sall.mp4")
                        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                        # Write with audio if available
                        final_clip.write_videofile(
                            output_path, 
                            codec='libx264', 
                            audio_codec='aac' if final_clip.audio else None,
                            audio=(final_clip.audio is not None)
                        )
                        
                        # Close clips
                        final_clip.close()
                        for c in clips:
                            c.close()
                        
                        # Upload to OBS
                        print(f"Uploading {output_path} to OBS...")
                        obs_url = obs_utils.upload_file(output_path, output_filename, mime_type='video/mp4')
                        
                        if obs_url:
                            group_data['final_url'] = obs_url
                            group_data['status'] = 'completed'
                        else:
                            group_data['status'] = 'failed'
                            group_data['error'] = 'OBS upload failed'
                    else:
                        group_data['status'] = 'failed'
                        group_data['error'] = 'No clips to concatenate'
                        
                except Exception as e:
                    print(f"Concatenation error: {e}")
                    group_data['status'] = 'failed'
                    group_data['error'] = str(e)
            
            print(f"Group {group_id} finished with status {group_data['status']}")
            break
            
        # Wait 30 seconds
        time.sleep(30)

@app.route('/upload_image_swap', methods=['POST'])
def upload_image_swap():
    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    # Get workflow type
    workflow_type = request.form.get('workflow_type', 'real') # 'real' or 'anime'

    # Save uploaded image
    filename = file.filename
    # Add uuid to avoid conflict
    file_id = str(uuid.uuid4())
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'png'
    image_filename = f"image_swap_{file_id}.{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, image_filename)
    file.save(image_path)
    
    # NEW: Download character from OBS
    character_url = "http://obs.dimond.top/character.png"
    character_path = os.path.join(UPLOAD_FOLDER, f"character_for_{image_filename}.png")
    
    try:
        # Download character
        with requests.get(character_url, stream=True) as r:
            if r.status_code == 200:
                with open(character_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                return jsonify({'error': f"Failed to download character from {character_url}"}), 500
    except Exception as e:
        return jsonify({'error': f"Failed to download character: {e}"}), 500
    
    group_id = file_id # Reuse file_id as group_id
    
    TASKS_STORE[group_id] = {
        'status': 'processing',
        'tasks': [],
        'created_at': time.time(),
        'workflow_type': workflow_type,
        'task_type': 'image_swap', # Special flag
        'audio_path': None
    }
    
    try:
        # Create a 0.5s video from the image
        # Using MoviePy ImageClip
        # Duration 0.5s, FPS 30
        from moviepy.editor import ImageClip
        
        # Resize logic: maintain aspect ratio, set height to 848 (same as video swap)
        # Note: ImageClip resize
        clip = ImageClip(image_path).set_duration(0.5).set_fps(30)
        
        # Resize
        # If width/height are odd, ffmpeg might complain. Ensure even dimensions.
        # But resize(height=848) handles aspect ratio.
        clip_resized = clip.resize(height=848)
        
        # Write temp video
        segment_filename = f"segment_{group_id}_0.mp4"
        segment_path = os.path.join(UPLOAD_FOLDER, segment_filename)
        
        clip_resized.write_videofile(
            segment_path, 
            fps=30, 
            codec='libx264', 
            audio=False, 
            logger=None
        )
        
        clip.close()
        clip_resized.close()
        
        # Submit to ComfyUI (Reuse video swap logic basically)
        # Upload files to ComfyUI
        comfy_seg = comfy_utils.client.upload_file(segment_path)
        if not comfy_seg:
            raise Exception("Failed to upload video segment")
        
        comfy_char = comfy_utils.client.upload_file(character_path)
        if not comfy_char:
            raise Exception("Failed to upload character")
            
        # Submit job with workflow_type
        prompt_id, error = comfy_utils.queue_workflow_template(
            comfy_char['name'], 
            comfy_seg['name'], 
            workflow_type=workflow_type
        )
        
        if prompt_id:
            TASKS_STORE[group_id]['tasks'].append({
                'task_id': prompt_id,
                'status': 'pending',
                'segment_index': 0,
                'result_path': None
            })
        else:
            TASKS_STORE[group_id]['status'] = 'failed'
            TASKS_STORE[group_id]['error'] = f"Failed to submit job: {error}"
            return jsonify({'error': f"Failed to submit job: {error}"}), 500
        
        # Clean up segment file
        if os.path.exists(segment_path):
            os.remove(segment_path)
            
        # Clean up input image
        if os.path.exists(image_path):
            os.remove(image_path)
            
        # Clean up character file
        if os.path.exists(character_path):
            os.remove(character_path)
            
        # Start background monitor
        thread = threading.Thread(target=monitor_group_task, args=(group_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing', 
            'group_id': group_id, 
            'message': 'Started image swap processing'
        })
        
    except Exception as e:
        TASKS_STORE[group_id]['status'] = 'failed'
        TASKS_STORE[group_id]['error'] = str(e)
        return jsonify({'error': str(e)}), 500

@app.route('/latest_image', methods=['GET'])
def get_latest_image():
    """
    Returns the URL of the latest generated image from OBS based on naming convention.
    Naming convention: YYYYMMDDHHMMSSone.png
    """
    try:
        # 1. Try to fetch from OBS directly (Stateless)
        latest_file = get_latest_file_from_obs('one.png')
        
        if latest_file:
            obs_url = f"http://obs.dimond.top/{latest_file}"
            return jsonify({'url': obs_url, 'filename': latest_file})
            
        # 2. Fallback to local
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('one.png')]
        if not files:
            return jsonify({'url': None})
            
        files.sort(reverse=True)
        latest_file = files[0]
        obs_url = f"http://obs.dimond.top/{latest_file}"
        
        return jsonify({'url': obs_url, 'filename': latest_file})
    except Exception as e:
        print(f"Error fetching latest image: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload_and_cut', methods=['POST'])
def upload_and_cut():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Get workflow type
    workflow_type = request.form.get('workflow_type', 'real') # 'real' or 'anime'

    # Save uploaded file
    filename = file.filename
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)
    
    # NEW: Download character from OBS
    character_url = "http://obs.dimond.top/character.png"
    character_path = os.path.join(UPLOAD_FOLDER, f"character_for_{filename}.png")
    
    try:
        # Download character
        with requests.get(character_url, stream=True) as r:
            if r.status_code == 200:
                with open(character_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                # Fallback to local default if exists? Or fail?
                # Let's try to fail gracefully
                return jsonify({'error': f"Failed to download character from {character_url}"}), 500
    except Exception as e:
        return jsonify({'error': f"Failed to download character: {e}"}), 500
    
    group_id = str(uuid.uuid4())
    
    # Extract audio immediately
    audio_path = os.path.join(UPLOAD_FOLDER, f"original_audio_{group_id}.mp3")
    try:
        # We need to extract audio using moviepy before we do anything else
        # Or just use the original file if it has audio
        # Let's use VideoFileClip to extract
        temp_clip = VideoFileClip(file_path)
        if temp_clip.audio:
            temp_clip.audio.write_audiofile(audio_path, logger=None)
            has_audio = True
        else:
            has_audio = False
        temp_clip.close()
    except Exception as e:
        print(f"Failed to extract audio: {e}")
        has_audio = False

    TASKS_STORE[group_id] = {
        'status': 'processing',
        'tasks': [],
        'created_at': time.time(),
        'workflow_type': workflow_type,
        'audio_path': audio_path if has_audio else None
    }
    
    try:
        # Preprocessing: Resize and set FPS
        # Target: Height 848, FPS 30
        clip = VideoFileClip(file_path)
        
        # Resize height to 848
        clip_resized = clip.resize(height=848)
        
        duration = clip.duration
        fps = 30 # Target FPS
        
        # Calculate segments (4s duration as requested)
        segment_duration = 4
        num_segments = math.ceil(duration / segment_duration)
        
        print(f"Processing video: {filename}, duration: {duration}s, segments: {num_segments}, workflow: {workflow_type}")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, duration)
            
            # Create subclip
            subclip = clip_resized.subclip(start_time, end_time)
            
            # Generate segment filename
            segment_filename = f"segment_{group_id}_{i}.mp4"
            segment_path = os.path.join(UPLOAD_FOLDER, segment_filename)
            
            # Write segment
            subclip.write_videofile(
                segment_path, 
                fps=fps, 
                codec='libx264', 
                audio=False, 
                logger=None
            )
            
            # Upload files to ComfyUI
            comfy_seg = comfy_utils.client.upload_file(segment_path)
            if not comfy_seg:
                raise Exception("Failed to upload video segment")
            
            comfy_char = comfy_utils.client.upload_file(character_path)
            if not comfy_char:
                raise Exception("Failed to upload character")
                
            # Submit job with workflow_type
            prompt_id, error = comfy_utils.queue_workflow_template(
                comfy_char['name'], 
                comfy_seg['name'], 
                workflow_type=workflow_type
            )
            
            if prompt_id:
                TASKS_STORE[group_id]['tasks'].append({
                    'task_id': prompt_id,
                    'status': 'pending',
                    'segment_index': i,
                    'result_path': None
                })
            else:
                TASKS_STORE[group_id]['status'] = 'failed'
                TASKS_STORE[group_id]['error'] = f"Failed to submit segment {i}: {error}"
                clip.close()
                clip_resized.close()
                return jsonify({'error': f"Failed to submit segment {i}: {error}"}), 500
            
            # Clean up segment file
            if os.path.exists(segment_path):
                os.remove(segment_path)
                
        clip.close()
        clip_resized.close()
        
        # Clean up original file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Clean up downloaded character file
        if os.path.exists(character_path):
            os.remove(character_path)
            
        # Start background monitor
        thread = threading.Thread(target=monitor_group_task, args=(group_id,))
        thread.daemon = True
        thread.start()
            
        return jsonify({
            'status': 'processing', 
            'group_id': group_id, 
            'message': f'Started processing {num_segments} segments'
        })

    except Exception as e:
        # Clean up original file if error
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'character_path' in locals() and os.path.exists(character_path):
            os.remove(character_path)
            
        TASKS_STORE[group_id]['status'] = 'failed'
        TASKS_STORE[group_id]['error'] = str(e)
        return jsonify({'error': str(e)}), 500

@app.route('/check_group_status/<group_id>', methods=['GET'])
def check_group_status(group_id):
    group_data = TASKS_STORE.get(group_id)
    if not group_data:
        return jsonify({'error': 'Group not found'}), 404
    
    response = {
        'status': group_data.get('status'),
        'final_url': group_data.get('final_url'),
        'error': group_data.get('error'),
        'progress': f"{len([t for t in group_data['tasks'] if t['status'] == 'completed'])}/{len(group_data['tasks'])}"
    }
    return jsonify(response)

def get_latest_file_from_obs(suffix):
    """
    Fetches the file list from OBS and returns the latest file matching the suffix.
    """
    try:
        # Fetch OBS index page
        response = requests.get("http://obs.dimond.top/", timeout=5)
        if response.status_code != 200:
            print(f"Failed to fetch OBS index: {response.status_code}")
            return None
            
        # Parse filenames using regex
        # Look for href="http://obs.dimond.top/FILENAME" or just FILENAME in list
        # Based on curl output: <a href="http://obs.dimond.top/20260114002813all.mp4" target="_blank">
        import re
        content = response.text
        # Regex to capture filenames ending with suffix
        # Pattern matches: href="http://obs.dimond.top/(.*?suffix)" or href="(.*?suffix)"
        # Assuming simple filenames without path
        pattern = r'href=["\'](?:http://obs\.dimond\.top/)?([^"\']+' + re.escape(suffix) + r')["\']'
        matches = re.findall(pattern, content)
        
        if not matches:
            return None
            
        # Filter out duplicates and sort
        unique_files = list(set(matches))
        unique_files.sort(reverse=True)
        
        if unique_files:
            latest_file = unique_files[0]
            # Ensure it's just the filename, not full URL
            if "/" in latest_file:
                latest_file = latest_file.split("/")[-1]
            return latest_file
            
        return None
    except Exception as e:
        print(f"Error fetching from OBS: {e}")
        return None

@app.route('/latest_video', methods=['GET'])
def get_latest_video():
    """
    Returns the URL of the latest generated video from OBS based on naming convention.
    Naming convention: YYYYMMDDHHMMSSall.mp4
    """
    try:
        # 1. Try to fetch from OBS directly (Stateless)
        latest_file = get_latest_file_from_obs('all.mp4')
        
        if latest_file:
            obs_url = f"http://obs.dimond.top/{latest_file}"
            return jsonify({'url': obs_url})
            
        # 2. Fallback to local file system if OBS fetch fails or returns nothing
        # (This handles case where OBS index might be disabled but local has it)
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('all.mp4')]
        if not files:
            return jsonify({'url': None})
            
        files.sort(reverse=True)
        latest_file = files[0]
        obs_url = f"http://obs.dimond.top/{latest_file}"
        
        return jsonify({'url': obs_url})
    except Exception as e:
        print(f"Error fetching latest video: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)