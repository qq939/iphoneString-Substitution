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

def modify_audio_workflow(workflow, text, filename):
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
        workflow["27"]["inputs"]["seed"] = random.randint(1, 1000000000000000)
        
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
            # No file provided, fallback to existing tone.wav
            # We assume tone.wav exists in ComfyUI or we have a default one locally?
            # Requirement: "沿用旧的tone.wav发给comfyUI"
            # This implies we tell ComfyUI to use "tone.wav" (which might be the last uploaded one?)
            # OR we find a local default tone.wav and upload it.
            # Let's assume we send "tone.wav" string to the node, assuming it exists on server.
            # OR better, if we have a default one in UPLOAD_FOLDER?
            # Let's try to use "tone.wav" as the filename.
            print("No file uploaded, using default tone.wav")
            uploaded_filename = "tone.wav" 
            # Note: If tone.wav doesn't exist on ComfyUI server input folder, this will fail.
            # But the user request implies it should work (maybe persistence).

        # Load Workflow
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', 'audio_workflow.json')
        if not os.path.exists(workflow_path):
             return jsonify({"error": "Workflow file not found"}), 500
             
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        workflow = modify_audio_workflow(workflow, text, uploaded_filename)
        
        # Queue Prompt
        prompt_id = comfy_utils.client.queue_prompt(workflow)
        
        if prompt_id:
            # Clean up generated wav path if we created it
            if file and os.path.exists(wav_path):
                os.remove(wav_path)
                
            return jsonify({"status": "success", "prompt_id": prompt_id})
        else:
            return jsonify({"error": "Failed to queue prompt"}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
                    # Naming: YYYYMMDDHHMMSSsound.flac
                    output_filename = datetime.now().strftime("%Y%m%d%H%M%Ssound.flac")
                    obs_url = obs_utils.upload_file(local_path, output_filename, mime_type='audio/flac')
                    
                    # Rename local file to match so latest_audio can find it
                    local_renamed_path = os.path.join(UPLOAD_FOLDER, output_filename)
                    if os.path.exists(local_path):
                        os.rename(local_path, local_renamed_path)
                    
                    if obs_url:
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
    Naming convention: YYYYMMDDHHMMSSsound.flac
    """
    try:
        # We need to list files from OBS or local?
        # Since we upload to OBS and don't keep a local DB, we can check local UPLOAD_FOLDER for files we downloaded/processed
        # But wait, download_result saves to UPLOAD_FOLDER with ComfyUI's filename (e.g. ComfyUI_0001.flac or similar)
        # It doesn't rename to YYYYMMDDHHMMSSsound.flac locally unless we do it.
        # In check_audio_status, we upload to OBS with that name, but local file is whatever download_result returned.
        # We should probably check OBS listing? But obs_utils might not support listing.
        # Let's rely on the fact that we process it on this server.
        # We can rename the local file to match the OBS name after uploading, or keep a record.
        # Let's verify what check_audio_status does.
        # It uploads `local_path` to OBS as `output_filename`.
        # We should rename `local_path` to `output_filename` locally too so we can find it.
        
        # Refactor check_audio_status slightly to rename local file?
        # Or just search for *sound.flac in UPLOAD_FOLDER if we save it there.
        # Wait, check_audio_status doesn't save with new name locally.
        # I'll update check_audio_status to rename local file.
        
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('sound.flac')]
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

@app.route('/upload_and_cut', methods=['POST'])
def upload_and_cut():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

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
        'audio_path': audio_path if has_audio else None
    }
    
    try:
        # Load video
        clip = VideoFileClip(file_path)
        
        # Resize and set FPS (Preprocessing)
        # Height 848, width auto-scaled (maintaining aspect ratio), FPS 30
        print(f"Preprocessing video: resizing to height=848 and setting fps=30")
        clip = clip.resize(height=848)
        clip = clip.set_fps(30)
        
        duration = clip.duration
        
        # Cut into 3s segments
        segment_duration = 3
        num_segments = math.ceil(duration / segment_duration)
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, duration)
            
            # Create subclip
            subclip = clip.subclip(start_time, end_time)
            
            # Generate segment filename
            segment_filename = f"segment_{i}_{group_id}.mp4"
            segment_path = os.path.join(UPLOAD_FOLDER, segment_filename)
            
            # Write segment to file
            subclip.write_videofile(
                segment_path, 
                codec='libx264', 
                audio=False, # Disable audio to avoid MoviePy errors and sync issues
                remove_temp=True,
                preset='ultrafast',
                logger=None # Silence output
            )
            
            # Submit to ComfyUI
            # We use comfy_utils.submit_job which handles uploading files and queuing workflow
            prompt_id, error = comfy_utils.submit_job(character_path, segment_path)
            
            if prompt_id:
                TASKS_STORE[group_id]['tasks'].append({
                    'task_id': prompt_id,
                    'status': 'pending',
                    'segment_index': i,
                    'result_path': None
                })
            else:
                # If one fails, fail the whole group? Or continue?
                # For now fail immediately
                TASKS_STORE[group_id]['status'] = 'failed'
                TASKS_STORE[group_id]['error'] = f"Failed to submit segment {i}: {error}"
                clip.close()
                return jsonify({'error': f"Failed to submit segment {i}: {error}"}), 500
            
            # Clean up segment file (optional, but submit_job uploads it so we can delete local)
            # comfy_utils.submit_job reads the file. After return it's done.
            if os.path.exists(segment_path):
                os.remove(segment_path)
                
        clip.close()
        
        # Clean up original file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Clean up downloaded character file? 
        # We can keep it or delete it. Since it's unique per request (character_for_...), we should delete it.
        # But tasks are async... wait, submit_job uploads it to ComfyUI. 
        # Once submit_job returns, the file has been read and uploaded.
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

@app.route('/latest_video', methods=['GET'])
def get_latest_video():
    """
    Returns the URL of the latest generated video from OBS based on naming convention.
    Naming convention: YYYYMMDDHHMMSSall.mp4
    """
    try:
        # Since we don't have a database of OBS files, we can either:
        # 1. List files in local UPLOAD_FOLDER and find the latest 'all.mp4'
        # 2. Assume the filename format allows sorting
        
        files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('all.mp4')]
        if not files:
            return jsonify({'url': None})
            
        # Sort by filename (which starts with timestamp) descending
        files.sort(reverse=True)
        latest_file = files[0]
        
        # Construct OBS URL
        # Assuming obs_utils.upload_file returns a consistent URL format: http://obs.dimond.top/{filename}
        obs_url = f"http://obs.dimond.top/{latest_file}"
        
        return jsonify({'url': obs_url})
    except Exception as e:
        print(f"Error fetching latest video: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)