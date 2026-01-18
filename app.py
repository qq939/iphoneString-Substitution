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

import comfy_utils
import obs_utils
import ffmpeg_utils

# Add local bin directory to PATH for ffmpeg/ffprobe
local_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
if os.path.exists(local_bin):
    os.environ["PATH"] += os.pathsep + local_bin

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

app = Flask(__name__)

# Global config and shared state (used across multiple routes and helpers)
SUBSTITUTION_FILE = 'langchain/substitution.txt'  # Used in: index route text substitution logic
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')  # Used in: all upload, temp, ffmpeg operations

VIDEO_WIDTH = 640  # Used in: generate_1s_video (ffmpeg image_to_video width)
VIDEO_HEIGHT = 640  # Used in: generate_1s_video (ffmpeg image_to_video height)
VIDEO_FPS = 16  # Used in: generate_1s_video (ffmpeg image_to_video fps)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

COMFY_STATUS = {  # Used in: check_comfy_status, /comfy_status, ensure_comfy_connection, /retest_connection
    'status': 'unknown',
    'last_checked': 0,
    'ip': 'Unknown'
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
                    print(f"ComfyUI is ONLINE at {comfy_utils.client.base_url}")
                COMFY_STATUS['status'] = 'online'
                COMFY_STATUS['ip'] = comfy_utils.client.base_url
            else:
                if COMFY_STATUS['status'] != 'offline':
                    print(f"ComfyUI is OFFLINE at {comfy_utils.client.base_url}")
                COMFY_STATUS['status'] = 'offline'
                COMFY_STATUS['ip'] = comfy_utils.client.base_url if comfy_utils.client.base_url else "None"
        except Exception as e:
            print(f"Error checking ComfyUI status: {e}")
            COMFY_STATUS['status'] = 'offline'
            COMFY_STATUS['ip'] = "Error"
        COMFY_STATUS['last_checked'] = time.time()
        time.sleep(30)

# Start status checker
status_thread = threading.Thread(target=check_comfy_status, daemon=True)
status_thread.start()

TASKS_STORE = {}  # Used in: upload_and_cut, generate_i2v_group, monitor_group_task, _add_transition_video_to_group, check_group_status
AUDIO_TASKS = {}  # Used in: upload_audio, check_audio_status, process_audio_result
AUDIO_LOCK = threading.Lock()  # Used in: concurrent audio task state protection

BACKEND_TASK_TIMEOUT_SECONDS = 6 * 60 * 60  # Used in: monitor_group_task timeout control
BACKEND_POLL_INTERVAL_SECONDS = 15  # Used in: monitor_group_task polling interval

def modify_digital_human_workflow(workflow, image_filename, audio_filename, audio_duration=None):
    """
    Modifies the digital human video workflow JSON based on inputs.
    audio_duration: duration of the audio segment in seconds (optional, for frame calculation)
    """
    # 1. Update Image (Node 49)
    if "49" in workflow and "inputs" in workflow["49"]:
        workflow["49"]["inputs"]["image"] = image_filename

    # 2. Update Audio (Node 58)
    if "58" in workflow and "inputs" in workflow["58"]:
        workflow["58"]["inputs"]["audio"] = audio_filename
        
    # 3. Randomize Seed (Node 64) -> Set to 0 as requested
    if "64" in workflow and "inputs" in workflow["64"]:
        workflow["64"]["inputs"]["seed"] = 0
        
    # 4. Update Frame Length (Node 65) based on audio duration and FPS (Node 60)
    if audio_duration is not None and "65" in workflow and "inputs" in workflow["65"]:
        fps = 25 # Default FPS
        if "60" in workflow and "inputs" in workflow["60"] and "fps" in workflow["60"]["inputs"]:
            fps = workflow["60"]["inputs"]["fps"]
            
        # Calculate frames: duration * fps
        # Add a small buffer or ceil? Wan2.1 usually needs specific lengths?
        # The prompt implies we should calculate it.
        # length = int(audio_duration * fps) + some_buffer?
        # Let's match audio length exactly or slightly more.
        length = int(math.ceil(audio_duration * fps))
        
        # Ensure minimum length if needed? 
        # Node 65 input "length"
        workflow["65"]["inputs"]["length"] = length
        print(f"Updated workflow frame length to {length} (Duration: {audio_duration}s, FPS: {fps})")
        
    return workflow

def modify_extend_video_workflow(workflow, video_filename, audio_filename):
    """
    Modifies the extend video to audio length workflow.
    """
    # 1. Update Video (Node 14 - VHS_LoadVideo)
    if "14" in workflow and "inputs" in workflow["14"]:
        workflow["14"]["inputs"]["video"] = video_filename
        
    # 2. Update Audio (Node 66 - LoadAudio)
    if "66" in workflow and "inputs" in workflow["66"]:
        workflow["66"]["inputs"]["audio"] = audio_filename
    
    return workflow

def modify_i2v_workflow(workflow, image_filename, prompt_text):
    if "97" in workflow and "inputs" in workflow["97"]:
        workflow["97"]["inputs"]["image"] = image_filename
    if "93" in workflow and "inputs" in workflow["93"]:
        workflow["93"]["inputs"]["text"] = prompt_text
    return workflow

def generate_1s_video(image_path, output_path):
    """
    Generates a 1-second video from an image using ffmpeg, with FPS and
    resolution controlled by global VIDEO_WIDTH, VIDEO_HEIGHT and VIDEO_FPS.
    """
    try:
        ffmpeg_utils.image_to_video(
            image_path,
            output_path,
            duration=1,
            fps=VIDEO_FPS,
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
        )
    except Exception as e:
        print(f"Error generating 1s video: {e}")
        raise e

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

@app.route('/retest_connection', methods=['POST'])
def retest_connection():
    try:
        success = comfy_utils.client.find_fastest_server()
        status = 'online' if success else 'offline'
        ip = comfy_utils.client.base_url
        
        # Update global status immediately
        COMFY_STATUS['status'] = status
        COMFY_STATUS['ip'] = ip
        COMFY_STATUS['last_checked'] = time.time()
        
        return jsonify({'status': 'success', 'connected': success, 'ip': ip})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def ensure_comfy_connection():
    """
    Checks connection to ComfyUI and updates global status.
    Raises exception if no server is available.
    """
    if app.config.get('TESTING'):
        COMFY_STATUS['status'] = 'online'
        COMFY_STATUS['ip'] = comfy_utils.client.base_url if comfy_utils.client.base_url else "TESTING"
        COMFY_STATUS['last_checked'] = time.time()
        return

    # Force a check which will try to switch servers if current is down
    if not comfy_utils.client.check_connection():
        # If check_connection returns False, it means even after retries it failed
        COMFY_STATUS['status'] = 'offline'
        COMFY_STATUS['ip'] = "None"
        raise Exception("Could not connect to any ComfyUI server")
    
    # If we are here, we are connected
    COMFY_STATUS['status'] = 'online'
    COMFY_STATUS['ip'] = comfy_utils.client.base_url
    COMFY_STATUS['last_checked'] = time.time()

@app.route('/upload_character', methods=['POST'])
def upload_character():
    # 1. Connection Check (Optional for character upload)
    # User noted this is just OBS upload, so we shouldn't block if ComfyUI is down.
    # We'll just update status in background or log it.
    try:
        ensure_comfy_connection()
    except:
        pass

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
    # Ensure ComfyUI connection before starting
    try:
        ensure_comfy_connection()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

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
        input_video_path_for_stage2 = None
        
        # Check if file is provided and valid
        if file and file.filename != '':
            original_filename = file.filename
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
            
            if ext not in allowed_extensions:
                return jsonify({'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'}), 400
                
            temp_path = os.path.join(UPLOAD_FOLDER, f"temp_audio_{uuid.uuid4()}.{ext}")
            file.save(temp_path)
            
            # Save input video copy immediately if it's a video format
            # This ensures we have it for Stage 2 before any conversion/cleanup
            if ext in ['mp4', 'mov']:
                 try:
                    input_video_filename = f"input_video_{uuid.uuid4()}.{ext}"
                    input_video_path = os.path.join(UPLOAD_FOLDER, input_video_filename)
                    shutil.copy(temp_path, input_video_path)
                    
                    # Verify it has video stream using ffmpeg
                    is_valid_video = False
                    try:
                        info = ffmpeg_utils.get_video_info(input_video_path)
                        if info.get('duration', 0) > 0 and info.get('width', 0) > 0 and info.get('height', 0) > 0:
                            is_valid_video = True
                            print(f"Video verification passed for {input_video_filename}: {info.get('width')}x{info.get('height')}, {info.get('duration')}s")
                    except Exception as e:
                        print(f"Video verification failed for {input_video_filename}: {e}")
                        if ext == 'mov':
                            is_valid_video = True
                            print(f"Fallback: Treating {input_video_filename} as valid video because extension is .mov")
                        else:
                            is_valid_video = False
                        
                    if is_valid_video:
                        input_video_path_for_stage2 = input_video_path
                        print(f"Saved input video for Stage 2: {input_video_path}")
                    else:
                        print(f"File {ext} does not appear to be a valid video, ignoring for Stage 2.")
                        if os.path.exists(input_video_path):
                            os.remove(input_video_path)
                 except Exception as e:
                     print(f"Failed to save input video copy: {e}")
            
            # Convert to wav
            if AudioSegment:
                try:
                    audio = AudioSegment.from_file(temp_path)
                    # Enforce standard WAV format: 44.1kHz, 16-bit, Stereo
                    audio = audio.set_frame_rate(44100).set_sample_width(2).set_channels(2)
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
            
            # Step 1: Download
            try:
                wav_filename = f"tone_{uuid.uuid4()}.wav"
                wav_path = os.path.join(UPLOAD_FOLDER, wav_filename)
                
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(obs_tone_url, stream=True, timeout=30, headers=headers)
                
                if response.status_code == 200:
                    with open(wav_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Successfully downloaded tone.wav ({os.path.getsize(wav_path)} bytes)")
                else:
                    print(f"OBS Download failed with status: {response.status_code}")
                    return jsonify({'error': f'Failed to download tone.wav from OBS: {response.status_code}'}), 500
            except Exception as e:
                print(f"OBS Download Exception: {e}")
                return jsonify({'error': f'Exception downloading from OBS: {str(e)}'}), 500

            # Step 2: Upload to ComfyUI
            try:
                print(f"Uploading {wav_filename} to ComfyUI...")
                comfy_res = comfy_utils.client.upload_file(wav_path)
                if not comfy_res:
                    return jsonify({'error': 'Failed to upload downloaded tone.wav to ComfyUI (Response empty)'}), 500
                uploaded_filename = comfy_res.get('name')
                
                # Clean up local file
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                    
            except Exception as e:
                print(f"ComfyUI Upload Exception: {e}")
                # Clean up even on failure
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                return jsonify({'error': f'Failed to upload to ComfyUI: {str(e)}'}), 500

        # Load Workflow
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', 'audio_workflow.json')
        if not os.path.exists(workflow_path):
             return jsonify({"error": "Workflow file not found"}), 500
             
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        workflow = modify_audio_workflow(workflow, text, uploaded_filename, emotions)
        
        queue_result = comfy_utils.client.queue_prompt(workflow)
        if isinstance(queue_result, tuple):
            if len(queue_result) == 2:
                prompt_id, server_address = queue_result
            elif len(queue_result) >= 3:
                prompt_id, server_address = queue_result[0], queue_result[1]
            else:
                prompt_id, server_address = queue_result[0] if queue_result else None, None
        else:
            prompt_id, server_address = queue_result, None
        
        if prompt_id:
            task_info = {
                'status': 'pending',
                'url': None,
                'input_video_path': input_video_path_for_stage2,
                'server': server_address,
                'created_at': time.time(),
            }

            with AUDIO_LOCK:
                AUDIO_TASKS[prompt_id] = task_info
            
            # Start background monitor for this task
            monitor_thread = threading.Thread(target=monitor_audio_task, args=(prompt_id,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
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

def process_digital_human_video(audio_path, input_video_path=None):
    """
    Background task to generate digital human video.
    """
    try:
        print(f"Starting digital human video generation for audio: {audio_path}")
        
        # 1. Prepare Inputs
        # Audio is already at audio_path (local)
        
        uploaded_video_name = None
        character_path = None
        video_1s_path = None

        # DEBUG: Check if input_video_path is passed correctly
        print(f"DEBUG: process_digital_human_video called with input_video_path: {input_video_path}")
        if input_video_path:
             print(f"DEBUG: input_video_path exists: {os.path.exists(input_video_path)}")
        
        if input_video_path and os.path.exists(input_video_path):
            print(f"Using provided input video: {input_video_path}")
            stage2_video_path = input_video_path
            trimmed_video_path = None
            try:
                info = ffmpeg_utils.get_video_info(input_video_path)
                duration = info.get('duration', 0)
                end_time = min(3, duration) if duration > 0 else 3
                
                trimmed_video_filename = f"stage2_input_3s_{uuid.uuid4()}.mp4"
                trimmed_video_path = os.path.join(UPLOAD_FOLDER, trimmed_video_filename)
                
                ffmpeg_utils.cut_video(input_video_path, trimmed_video_path, 0, end_time)
                
                stage2_video_path = trimmed_video_path
                print(f"Trimmed input video to first {end_time}s: {trimmed_video_path}")
            except Exception as e:
                print(f"Failed to trim input video, uploading original: {e}")

            print("Uploading input video to ComfyUI...")
            try:
                comfy_video = comfy_utils.client.upload_file(stage2_video_path)
            finally:
                if trimmed_video_path:
                    try:
                        os.remove(trimmed_video_path)
                    except OSError:
                        pass
            if not comfy_video:
                print("Failed to upload input video to ComfyUI")
                return
            uploaded_video_name = comfy_video.get('name')
            print(f"Input video uploaded as: {uploaded_video_name}")
            
        else:
            latest_character_video = get_latest_file_from_obs('character.mp4')
            if latest_character_video:
                character_video_url = f"http://obs.dimond.top/{latest_character_video}"
                character_video_path = os.path.join(UPLOAD_FOLDER, f"character_video_{uuid.uuid4()}.mp4")
                print(f"Downloading character.mp4 from OBS: {character_video_url}")
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    with requests.get(character_video_url, stream=True, timeout=30, headers=headers) as response:
                        if response.status_code == 200:
                            with open(character_video_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            stage2_video_path = character_video_path
                        else:
                            print(f"Failed to download character.mp4: {response.status_code}")
                            stage2_video_path = None
                except Exception as e:
                    print(f"Error downloading character.mp4: {e}")
                    stage2_video_path = None
                
                if stage2_video_path:
                    print("Uploading character.mp4 to ComfyUI for extend-video workflow...")
                    comfy_video = comfy_utils.client.upload_file(stage2_video_path)
                    if not comfy_video:
                        print("Failed to upload character.mp4 to ComfyUI")
                        return
                    uploaded_video_name = comfy_video.get('name')
                else:
                    return
            else:
                character_url = "http://obs.dimond.top/character.png"
                character_filename = f"character_{uuid.uuid4()}.png"
                character_path = os.path.join(UPLOAD_FOLDER, character_filename)
                
                print(f"Downloading character from {character_url}...")
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    response = requests.get(character_url, stream=True, timeout=30, headers=headers)
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
                
                print("Generating 1s video from character...")
                video_1s_filename = f"character_1s_{uuid.uuid4()}.mp4"
                video_1s_path = os.path.join(UPLOAD_FOLDER, video_1s_filename)
                try:
                    generate_1s_video(character_path, video_1s_path)
                except Exception as e:
                    print(f"Error generating 1s video: {e}")
                    return
                
                print("Uploading 1s video to ComfyUI...")
                comfy_video = comfy_utils.client.upload_file(video_1s_path)
                if not comfy_video:
                    print("Failed to upload 1s video to ComfyUI")
                    return
                uploaded_video_name = comfy_video.get('name')
        
        # Upload Full Audio
        print("Uploading audio to ComfyUI...")
        comfy_audio = comfy_utils.client.upload_file(audio_path)
        if not comfy_audio:
            print("Failed to upload audio to ComfyUI")
            return
        uploaded_audio_name = comfy_audio.get('name')
        
        # 4. Submit Task
        print("Submitting digital human task...")
        
        # Load Workflow Template
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '扩展视频到音频长度.json')
        if not os.path.exists(workflow_path):
            print("Digital human workflow file not found")
            return
            
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_template = json.load(f)
            
        # Modify Workflow
        current_workflow = modify_extend_video_workflow(
            workflow_template, 
            uploaded_video_name, 
            uploaded_audio_name
        )
        
        prompt_id, server_address = comfy_utils.client.queue_prompt(current_workflow)
        
        if not prompt_id:
            print("Failed to queue prompt")
            return
            
        print(f"Task queued with ID: {prompt_id} on {server_address}")
        
        print("Monitoring digital human task...")
        start_time = time.time()
        
        while True:
            try:
                if time.time() - start_time > BACKEND_TASK_TIMEOUT_SECONDS:
                    print("Digital human task timed out after 6 hours")
                    break
                
                status, result = comfy_utils.check_status(prompt_id, server_address)
                
                if status == 'SUCCEEDED':
                    if isinstance(result, dict):
                        print("Task succeeded, downloading...")
                        local_path = comfy_utils.download_result(result, UPLOAD_FOLDER, server_address)
                        
                        if local_path:
                            output_filename = datetime.now().strftime("%Y%m%d%H%M%Sall.mp4")
                            output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                            
                            shutil.move(local_path, output_path)
                            
                            print(f"Uploading result to OBS as {output_filename}...")
                            obs_url = obs_utils.upload_file(output_path, output_filename, mime_type='video/mp4')
                            
                            if obs_url:
                                print(f"Digital human video successfully uploaded: {obs_url}")
                            else:
                                print("Failed to upload digital human video to OBS")
                        else:
                            print("Failed to download result")
                    else:
                        print("Invalid result format")
                    break
                    
                elif status == 'FAILED':
                    print(f"Task failed: {result}")
                    break
                    
            except Exception as e:
                print(f"Error checking task: {e}")
            
            time.sleep(BACKEND_POLL_INTERVAL_SECONDS)
            
        # Cleanup
        if os.path.exists(character_path):
            os.remove(character_path)
        if os.path.exists(video_1s_path):
            os.remove(video_1s_path)
        if os.path.exists(audio_path):
            # Audio path is passed in, might be needed? 
            # In previous logic we cleaned it up.
            pass
            
    except Exception as e:
        print(f"Process digital human video error: {e}")
        import traceback
        traceback.print_exc()

def process_audio_result(prompt_id, result):
    """
    Process the result of an audio task: download, convert, upload to OBS, and trigger Stage 2.
    Returns (success, url_or_error_message)
    """
    try:
        if isinstance(result, dict):
            local_path = comfy_utils.download_result(result, UPLOAD_FOLDER)
            if local_path:
                # Upload to OBS
                # Naming: YYYYMMDDHHMMSSaudio.wav
                output_filename = datetime.now().strftime("%Y%m%d%H%M%Saudio.wav")
                
                # Convert to WAV if needed (ComfyUI usually outputs FLAC or WAV)
                wav_path = os.path.join(UPLOAD_FOLDER, output_filename)
                
                try:
                    if AudioSegment:
                        audio = AudioSegment.from_file(local_path)
                        # Enforce standard WAV format: 44.1kHz, 16-bit, Stereo
                        audio = audio.set_frame_rate(44100).set_sample_width(2).set_channels(2)
                        audio.export(wav_path, format="wav")
                        print(f"Converted output to WAV: {wav_path}")
                    else:
                        # Fallback just rename if pydub missing (risky if not wav)
                        print("Warning: pydub not found, renaming file to wav without conversion")
                        shutil.copy(local_path, wav_path)
                except Exception as e:
                    print(f"Failed to convert output to WAV: {e}")
                    # Fallback to original file but renamed
                    shutil.copy(local_path, wav_path)

                obs_url = obs_utils.upload_file(wav_path, output_filename, mime_type='audio/wav')
                
                # Rename local file to match so latest_audio can find it
                # local_renamed_path is used for stage 2
                local_renamed_path = wav_path
                
                if obs_url:
                    # Update task state
                    with AUDIO_LOCK:
                        if prompt_id in AUDIO_TASKS:
                            AUDIO_TASKS[prompt_id]['status'] = 'completed'
                            AUDIO_TASKS[prompt_id]['url'] = obs_url
                    
                    # Trigger Digital Human Video Generation (Stage 2)
                    # We do this in a background thread to avoid blocking the response
                    print(f"Audio upload successful. Triggering digital human video generation with {local_renamed_path}")
                    
                    input_video_path = None
                    with AUDIO_LOCK:
                        if prompt_id in AUDIO_TASKS and 'input_video_path' in AUDIO_TASKS[prompt_id]:
                            input_video_path = AUDIO_TASKS[prompt_id]['input_video_path']
                        
                    thread = threading.Thread(target=process_digital_human_video, args=(local_renamed_path, input_video_path))
                    thread.daemon = True
                    thread.start()
                    
                    return True, obs_url
                else:
                    return False, 'Failed to upload to OBS'
            else:
                return False, 'Failed to download result'
        else:
            return False, 'Invalid result format'
    except Exception as e:
        print(f"Error processing audio result: {e}")
        return False, str(e)

def monitor_audio_task(prompt_id):
    """
    Background thread to monitor audio task status.
    """
    print(f"Started monitoring audio task {prompt_id}")
    while True:
        with AUDIO_LOCK:
            if prompt_id not in AUDIO_TASKS:
                break
            task_data = AUDIO_TASKS[prompt_id]
            status = task_data['status']
            created_at = task_data.get('created_at')
            if created_at is not None and time.time() - created_at > BACKEND_TASK_TIMEOUT_SECONDS:
                AUDIO_TASKS[prompt_id]['status'] = 'failed'
                AUDIO_TASKS[prompt_id]['error'] = 'Timeout: audio task exceeded 6 hours'
                print(f"Audio task {prompt_id} timed out after 6 hours")
                break
            if status in ['completed', 'failed']:
                break
        
        try:
            status, result = comfy_utils.check_status(prompt_id)
            
            if status == 'SUCCEEDED':
                should_process = False
                with AUDIO_LOCK:
                    current_status = AUDIO_TASKS.get(prompt_id, {}).get('status')
                    if current_status not in ['processing_result', 'completed', 'failed']:
                        AUDIO_TASKS[prompt_id]['status'] = 'processing_result'
                        should_process = True
                
                if should_process:
                    print(f"Monitor: Task {prompt_id} succeeded. Processing result...")
                    success, output = process_audio_result(prompt_id, result)
                    if not success:
                        with AUDIO_LOCK:
                            if prompt_id in AUDIO_TASKS:
                                AUDIO_TASKS[prompt_id]['status'] = 'failed'
                break
                
            elif status == 'FAILED':
                with AUDIO_LOCK:
                    if prompt_id in AUDIO_TASKS:
                        AUDIO_TASKS[prompt_id]['status'] = 'failed'
                break
                
        except Exception as e:
            print(f"Monitor error for {prompt_id}: {e}")
            
        time.sleep(BACKEND_POLL_INTERVAL_SECONDS)

@app.route('/check_audio_status/<prompt_id>', methods=['GET'])
def check_audio_status(prompt_id):
    # Check if we already processed this task
    with AUDIO_LOCK:
        task_data = AUDIO_TASKS.get(prompt_id)
        if task_data:
            if task_data['status'] == 'completed' and task_data['url']:
                return jsonify({'status': 'completed', 'url': task_data['url']})
            if task_data['status'] == 'processing_result':
                return jsonify({'status': 'processing'}) # Still working on result

    try:
        status, result = comfy_utils.check_status(prompt_id)
        
        if status == 'SUCCEEDED':
            # Mark as processing to prevent re-entry
            should_process = False
            with AUDIO_LOCK:
                # Double check inside lock
                if prompt_id in AUDIO_TASKS and AUDIO_TASKS[prompt_id]['status'] in ['processing_result', 'completed']:
                     return jsonify({'status': 'processing'})
                     
                if prompt_id in AUDIO_TASKS:
                    AUDIO_TASKS[prompt_id]['status'] = 'processing_result'
                    should_process = True
                else:
                    AUDIO_TASKS[prompt_id] = {'status': 'processing_result', 'url': None}
                    should_process = True

            if should_process:
                success, output = process_audio_result(prompt_id, result)
                if success:
                    return jsonify({'status': 'completed', 'url': output})
                else:
                    with AUDIO_LOCK:
                        AUDIO_TASKS[prompt_id]['status'] = 'failed'
                    return jsonify({'status': 'failed', 'error': output})
            else:
                 return jsonify({'status': 'processing'})

        elif status == 'FAILED':
             with AUDIO_LOCK:
                 if prompt_id in AUDIO_TASKS:
                     AUDIO_TASKS[prompt_id]['status'] = 'failed'
             return jsonify({'status': 'failed', 'error': str(result)})
        else:
             return jsonify({'status': status})
             
    except Exception as e:
        return jsonify({'status': 'failed', 'error': str(e)})

@app.route('/latest_audio', methods=['GET'])
def get_latest_audio():
    """
    Returns the URL of the latest generated audio from OBS based on naming convention.
    Naming convention: YYYYMMDDHHMMSSaudio.wav
    """
    try:
        # 1. Try to fetch from OBS directly (Stateless)
        latest_file = get_latest_file_from_obs('audio.wav')
        
        if latest_file:
            obs_url = f"http://obs.dimond.top/{latest_file}"
            return jsonify({'url': obs_url, 'filename': latest_file})
            
        # 2. Fallback to local
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('audio.wav')]
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
        now = time.time()
        created_at = group_data.get('created_at')
        if created_at is not None and now - created_at > BACKEND_TASK_TIMEOUT_SECONDS:
            group_data['status'] = 'failed'
            group_data['error'] = 'Timeout: group exceeded 6 hours'
            print(f"Group {group_id} timed out after 6 hours")
            break

        all_done = True
        
        # Check each task
        for task in group_data['tasks']:
            if task['status'] in ['completed', 'failed']:
                continue
                
            # Check status from ComfyUI
            try:
                status, result = comfy_utils.check_status(task['task_id'], task.get('server'))
                # print(f"Task {task['task_id']} status: {status}")
                
                if status == 'SUCCEEDED':
                    # Download result
                    if isinstance(result, dict):
                        local_path = comfy_utils.download_result(result, UPLOAD_FOLDER, task.get('server'))
                        if local_path:
                            task['result_path'] = local_path
                            task['status'] = 'completed'
                        else:
                            task['status'] = 'failed'
                            task['error'] = 'Download failed'
                    else:
                        task['status'] = 'failed'
                        task['error'] = 'Invalid result format'
                        
                elif status == 'FAILED':
                    task['status'] = 'failed'
                    task['error'] = str(result)
                else:
                    # PENDING or RUNNING
                    all_done = False
            except Exception as e:
                print(f"Error checking task {task['task_id']}: {e}")
                # Don't mark as failed immediately, maybe network glitch?
                # But for now let's not block forever
                all_done = False
            
        if all_done:
            # Video Swap Logic
            print(f"Group {group_id} all tasks done. Concatenating...")
            # Concatenate videos
            try:
                # Sort by segment index
                sorted_tasks = sorted(group_data['tasks'], key=lambda x: x['segment_index'])
                video_paths = []
                for t in sorted_tasks:
                    if t['result_path'] and os.path.exists(t['result_path']):
                        video_paths.append(t['result_path'])
                
                if video_paths:
                    output_filename = datetime.now().strftime("%Y%m%d%H%M%Sall.mp4")
                    output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                    
                    # Temp concatenated video (silent)
                    temp_concat_path = os.path.join(UPLOAD_FOLDER, f"temp_concat_{group_id}.mp4")
                    ffmpeg_utils.concatenate_videos(video_paths, temp_concat_path)
                    
                    # Merge audio back
                    audio_path = group_data.get('audio_path')
                    if audio_path and os.path.exists(audio_path):
                        try:
                            # Merge audio with loop enabled if needed
                            # Our merge_audio_video with loop_audio=True will loop it
                            ffmpeg_utils.merge_audio_video(temp_concat_path, audio_path, output_path, loop_audio=True)
                            print(f"Merged audio from {audio_path}")
                            
                            # Remove temp concat
                            if os.path.exists(temp_concat_path):
                                os.remove(temp_concat_path)
                        except Exception as e:
                            print(f"Failed to merge audio: {e}")
                            # If merge fails, just use the silent video? 
                            # Or maybe move temp to output
                            if os.path.exists(temp_concat_path):
                                shutil.move(temp_concat_path, output_path)
                    else:
                        # No audio, just move temp to output
                        if os.path.exists(temp_concat_path):
                            shutil.move(temp_concat_path, output_path)
                    
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
            
        time.sleep(BACKEND_POLL_INTERVAL_SECONDS)


def _add_transition_video_to_group(file_storage, group_id=None):
    try:
        ensure_comfy_connection()
    except Exception as e:
        raise Exception(str(e))

    if group_id is None:
        group_id = str(uuid.uuid4())

    group_data = TASKS_STORE.get(group_id)
    if not group_data:
        group_data = {
            "status": "processing",
            "tasks": [],
            "created_at": time.time(),
            "workflow_type": "transition",
            "audio_path": None,
            "transition_videos": [],
            "monitor_started": False,
        }
        TASKS_STORE[group_id] = group_data

    index = len(group_data.get("transition_videos", []))

    original_filename = file_storage.filename or f"transition_{group_id}_{index}.mp4"
    raw_path = os.path.join(UPLOAD_FOLDER, f"raw_transition_{group_id}_{index}.mp4")
    file_storage.save(raw_path)

    preprocessed_path = os.path.join(UPLOAD_FOLDER, f"transition_{group_id}_{index}.mp4")
    ffmpeg_utils.resize_video(raw_path, preprocessed_path, 640, 16)

    info = ffmpeg_utils.get_video_info(preprocessed_path)
    duration = info.get("duration", 0) if isinstance(info, dict) else 0
    if duration is None:
        duration = 0

    group_data.setdefault("transition_videos", []).append(
        {"index": index, "path": preprocessed_path, "duration": duration, "name": original_filename}
    )

    if os.path.exists(raw_path):
        try:
            os.remove(raw_path)
        except OSError:
            pass

    if index == 0:
        group_data["tasks"].append(
            {
                "task_id": None,
                "server": None,
                "status": "completed",
                "segment_index": 0,
                "result_path": preprocessed_path,
            }
        )
    else:
        prev_video = group_data["transition_videos"][index - 1]
        prev_duration = prev_video.get("duration") or 0
        offset = prev_duration - 1.0 / 16.0
        if offset < 0:
            offset = 0

        start_image_path = os.path.join(
            UPLOAD_FOLDER, f"transition_{group_id}_{index - 1}_end.png"
        )
        end_image_path = os.path.join(
            UPLOAD_FOLDER, f"transition_{group_id}_{index}_start.png"
        )

        ffmpeg_utils.extract_frame(prev_video["path"], start_image_path, offset)
        ffmpeg_utils.extract_frame(preprocessed_path, end_image_path, 0)

        start_upload = comfy_utils.client.upload_file(start_image_path)
        end_upload = comfy_utils.client.upload_file(end_image_path)

        if not start_upload or not end_upload:
            raise Exception("Failed to upload transition frames to ComfyUI")

        start_image_name = start_upload.get("name")
        end_image_name = end_upload.get("name")
        if not start_image_name or not end_image_name:
            raise Exception("Invalid frame upload response from ComfyUI")

        prompt_id, server_address, error = comfy_utils.queue_transition_workflow(
            start_image_name, end_image_name
        )
        if not prompt_id:
            raise Exception(error or "Failed to queue transition workflow")

        group_data["tasks"].append(
            {
                "task_id": prompt_id,
                "server": server_address,
                "status": "pending",
                "segment_index": 2 * index - 1,
                "result_path": None,
            }
        )
        group_data["tasks"].append(
            {
                "task_id": None,
                "server": None,
                "status": "completed",
                "segment_index": 2 * index,
                "result_path": preprocessed_path,
            }
        )

    if not group_data.get("monitor_started"):
        thread = threading.Thread(target=monitor_group_task, args=(group_id,))
        thread.daemon = True
        thread.start()
        group_data["monitor_started"] = True

    return group_id

def monitor_i2v_group(group_id):
    group_data = TASKS_STORE.get(group_id)
    if not group_data:
        return
    while True:
        now = time.time()
        created_at = group_data.get('created_at')
        if created_at is not None and now - created_at > BACKEND_TASK_TIMEOUT_SECONDS:
            group_data['status'] = 'failed'
            break
        tasks = group_data.get('tasks', [])
        all_done = True
        for task in tasks:
            if task['status'] in ['completed', 'failed']:
                continue
            all_done = False
            try:
                status, result = comfy_utils.check_status(task['task_id'], task.get('server'))
                if status == 'SUCCEEDED':
                    if isinstance(result, dict):
                        local_path = comfy_utils.download_result(result, UPLOAD_FOLDER, task.get('server'))
                        if local_path:
                            task['result_path'] = local_path
                            task['status'] = 'completed'
                        else:
                            task['status'] = 'failed'
                    else:
                        task['status'] = 'failed'
                elif status == 'FAILED':
                    task['status'] = 'failed'
            except Exception:
                pass
        if all_done:
            video_paths = []
            for t in sorted(tasks, key=lambda x: x['segment_index']):
                if t.get('result_path') and os.path.exists(t['result_path']):
                    video_paths.append(t['result_path'])
            if video_paths:
                output_filename = datetime.now().strftime("%Y%m%d%H%M%Sall.mp4")
                output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                temp_concat_path = os.path.join(UPLOAD_FOLDER, f"temp_i2v_{group_id}.mp4")
                try:
                    ffmpeg_utils.concatenate_videos(video_paths, temp_concat_path)
                    if os.path.exists(temp_concat_path):
                        shutil.move(temp_concat_path, output_path)
                    obs_url = obs_utils.upload_file(output_path, output_filename, mime_type='video/mp4')
                    if obs_url:
                        group_data['final_url'] = obs_url
                        group_data['status'] = 'completed'
                    else:
                        group_data['status'] = 'failed'
                        group_data['error'] = 'OBS upload failed'
                except Exception as e:
                    group_data['status'] = 'failed'
                    group_data['error'] = str(e)
            else:
                group_data['status'] = 'failed'
                group_data['error'] = 'No clips to concatenate'
            break
        time.sleep(BACKEND_POLL_INTERVAL_SECONDS)

@app.route('/upload_and_cut', methods=['POST'])
def upload_and_cut():
    # Ensure ComfyUI connection before starting
    try:
        ensure_comfy_connection()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

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
        # We need to extract audio using ffmpeg before we do anything else
        # Or just use the original file if it has audio
        info = ffmpeg_utils.get_video_info(file_path)
        if info.get('has_audio'):
            ffmpeg_utils.extract_audio(file_path, audio_path)
            has_audio = True
        else:
            has_audio = False
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
        resized_video_path = None
        segment_source_path = file_path
        if workflow_type == 'anime':
            resized_video_path = os.path.join(UPLOAD_FOLDER, f"resized_{group_id}.mp4")
            try:
                ffmpeg_utils.resize_video(file_path, resized_video_path)
            except Exception as e:
                print(f"FFmpeg resize failed: {e}. Falling back to original size.")
                shutil.copy(file_path, resized_video_path)
            segment_source_path = resized_video_path
        
        info = ffmpeg_utils.get_video_info(segment_source_path)
        duration = info.get('duration', 0)
        fps = 20 # Target FPS (ffmpeg command handles this if we add -r)
        
        # Calculate segments (4s duration as requested)
        segment_duration = 4
        num_segments = math.ceil(duration / segment_duration)
        
        print(f"Processing video: {filename}, duration: {duration}s, segments: {num_segments}, workflow: {workflow_type}")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, duration)
            current_seg_len = end_time - start_time
            
            # Generate segment filename
            segment_filename = f"segment_{group_id}_{i}.mp4"
            segment_path = os.path.join(UPLOAD_FOLDER, segment_filename)
            
            ffmpeg_utils.cut_video(segment_source_path, segment_path, start_time, end_time)
            
            # Upload files to ComfyUI
            comfy_seg = comfy_utils.client.upload_file(segment_path)
            if not comfy_seg:
                raise Exception("Failed to upload video segment")
            
            comfy_char = comfy_utils.client.upload_file(character_path)
            if not comfy_char:
                raise Exception("Failed to upload character")
                
            # Submit job with workflow_type
            prompt_id, server_address, error = comfy_utils.queue_workflow_template(
                comfy_char['name'], 
                comfy_seg['name'], 
                workflow_type=workflow_type,
                segment_duration=current_seg_len
            )
            
            if prompt_id:
                TASKS_STORE[group_id]['tasks'].append({
                    'task_id': prompt_id,
                    'server': server_address,
                    'status': 'pending',
                    'segment_index': i,
                    'result_path': None
                })
            else:
                TASKS_STORE[group_id]['status'] = 'failed'
                TASKS_STORE[group_id]['error'] = f"Failed to submit segment {i}: {error}"
                if resized_video_path and os.path.exists(resized_video_path):
                    os.remove(resized_video_path)
                return jsonify({'error': f"Failed to submit segment {i}: {error}"}), 500
            
            # Clean up segment file
            if os.path.exists(segment_path):
                os.remove(segment_path)
                
        if resized_video_path and os.path.exists(resized_video_path):
            os.remove(resized_video_path)
            
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
        if 'resized_video_path' in locals() and resized_video_path and os.path.exists(resized_video_path):
            os.remove(resized_video_path)
            
        TASKS_STORE[group_id]['status'] = 'failed'
        TASKS_STORE[group_id]['error'] = str(e)
        return jsonify({'error': str(e)}), 500


@app.route('/upload_transition_video', methods=['POST'])
def upload_transition_video():
    try:
        ensure_comfy_connection()
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    group_id = request.form.get('group_id') or None

    try:
        group_id = _add_transition_video_to_group(file, group_id)
        return jsonify({'status': 'processing', 'group_id': group_id})
    except Exception as e:
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

@app.route('/generate_i2v_group', methods=['POST'])
def generate_i2v_group():
    try:
        ensure_comfy_connection()
    except Exception as e:
        return jsonify({'error': str(e)}), 503
    data = request.get_json(silent=True) or {}
    texts = data.get('texts') or []
    if not isinstance(texts, list) or len(texts) < 4:
        return jsonify({'error': 'texts must be a list of length 4'}), 400
    character_url = "http://obs.dimond.top/character.png"
    character_path = os.path.join(UPLOAD_FOLDER, f"i2v_character_{uuid.uuid4()}.png")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(character_url, stream=True, timeout=30, headers=headers) as r:
            if r.status_code != 200:
                return jsonify({'error': f'Failed to download character: {r.status_code}'}), 500
            with open(character_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    try:
        upload_res = comfy_utils.client.upload_file(character_path)
        if not upload_res or 'name' not in upload_res:
            return jsonify({'error': 'Failed to upload character to ComfyUI'}), 500
        image_name = upload_res['name']
    finally:
        if os.path.exists(character_path):
            os.remove(character_path)
    workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '图生视频video_wan2_2_14B_i2v.json')
    if not os.path.exists(workflow_path):
        return jsonify({'error': 'Workflow file not found'}), 500
    group_id = str(uuid.uuid4())
    TASKS_STORE[group_id] = {
        'status': 'processing',
        'tasks': [],
        'created_at': time.time(),
        'workflow_type': 'i2v',
        'audio_path': None,
    }
    for idx, text in enumerate(texts):
        if not isinstance(text, str):
            continue
        prompt_text = text.strip()
        if not prompt_text:
            continue
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        workflow = modify_i2v_workflow(workflow, image_name, prompt_text)
        try:
            prompt_id, server_address = comfy_utils.client.queue_prompt(workflow)
        except Exception as e:
            continue
        if prompt_id:
            TASKS_STORE[group_id]['tasks'].append({
                'task_id': prompt_id,
                'server': server_address,
                'status': 'pending',
                'segment_index': idx,
                'result_path': None,
            })
    thread = threading.Thread(target=monitor_i2v_group, args=(group_id,))
    thread.daemon = True
    thread.start()
    return jsonify({'status': 'processing', 'group_id': group_id})

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

@app.route('/save_character_from_current', methods=['POST'])
def save_character_from_current():
    try:
        latest_file = get_latest_file_from_obs('all.mp4')
        if not latest_file:
            return jsonify({'error': 'No latest video found on OBS'}), 404
        source_url = f"http://obs.dimond.top/{latest_file}"
        print(f"Downloading latest video for character.mp4 from {source_url}")
        character_temp = os.path.join(UPLOAD_FOLDER, f"character_src_{uuid.uuid4()}.mp4")
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(source_url, stream=True, timeout=30, headers=headers) as r:
            if r.status_code != 200:
                return jsonify({'error': f'Failed to download latest video: {r.status_code}'}), 500
            with open(character_temp, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        info = ffmpeg_utils.get_video_info(character_temp)
        duration = info.get('duration', 0)
        end_time = min(10, duration) if duration and duration > 0 else 10
        character_clip = os.path.join(UPLOAD_FOLDER, 'character.mp4')
        ffmpeg_utils.cut_video(character_temp, character_clip, 0, end_time)
        obs_url = obs_utils.upload_file(character_clip, 'character.mp4', mime_type='video/mp4')
        try:
            if os.path.exists(character_temp):
                os.remove(character_temp)
        except OSError:
            pass
        return jsonify({'status': 'success', 'url': obs_url})
    except Exception as e:
        print(f"Error saving character from current video: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)
