from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
import os
import re
import urllib
import requests
import math
from moviepy import VideoFileClip

app = Flask(__name__)
SUBSTITUTION_FILE = 'langchain/substitution.txt'

# Video Cut Config
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')
TARGET_URL = "http://videocut.dimond.top/overall"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
    
    results = []
    
    try:
        # Load video
        clip = VideoFileClip(file_path)
        duration = clip.duration
        
        # Cut into 3s segments
        segment_duration = 3
        num_segments = math.ceil(duration / segment_duration)
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, duration)
            
            # Create subclip
            subclip = clip.subclipped(start_time, end_time)
            
            # Generate segment filename
            segment_filename = f"segment_{i}_{filename}"
            segment_path = os.path.join(UPLOAD_FOLDER, segment_filename)
            
            # Write segment to file
            # Use ultrafast preset for speed, libx264 for compatibility
            subclip.write_videofile(
                segment_path, 
                codec='libx264', 
                audio_codec='aac', 
                temp_audiofile=os.path.join(UPLOAD_FOLDER, f"temp-audio-{i}.m4a"), 
                remove_temp=True,
                preset='ultrafast',
                logger=None # Silence output
            )
            
            # Post to target URL
            try:
                with open(segment_path, 'rb') as f:
                    files = {'video': (segment_filename, f, 'video/mp4')}
                    response = requests.post(TARGET_URL, files=files)
                    results.append({
                        'segment': i,
                        'status_code': response.status_code,
                        'response': response.json() if response.content else None
                    })
            except Exception as req_e:
                results.append({
                    'segment': i,
                    'error': str(req_e)
                })
            
            # Clean up segment file
            if os.path.exists(segment_path):
                os.remove(segment_path)
                
        clip.close()
        
        # Clean up original file
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return jsonify({'status': 'processed', 'results': results})

    except Exception as e:
        # Clean up original file if error
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)
