
import os
import subprocess
import json
import math

def run_command(cmd):
    """Run a shell command and return the output."""
    print(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.stderr}")
        raise e

def get_video_info(file_path):
    """
    Get video metadata using ffprobe.
    Returns a dict with 'duration', 'width', 'height', 'has_audio'.
    """
    cmd = [
        'ffprobe', 
        '-v', 'quiet', 
        '-print_format', 'json', 
        '-show_format', 
        '-show_streams', 
        file_path
    ]
    output = run_command(cmd)
    data = json.loads(output)
    
    info = {
        'duration': 0.0,
        'width': 0,
        'height': 0,
        'has_audio': False
    }
    
    if 'format' in data and 'duration' in data['format']:
        info['duration'] = float(data['format']['duration'])
        
    for stream in data.get('streams', []):
        if stream['codec_type'] == 'video':
            info['width'] = int(stream.get('width', 0))
            info['height'] = int(stream.get('height', 0))
        elif stream['codec_type'] == 'audio':
            info['has_audio'] = True
            
    return info

def extract_audio(video_path, output_path):
    """Extract audio from video."""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn', # No video
        '-acodec', 'libmp3lame', # Convert to mp3
        '-q:a', '2',
        output_path
    ]
    run_command(cmd)

def resize_video(input_path, output_path, max_size=800, fps=20):
    """Resize video with aspect ratio preserved and max side limited."""
    scale_filter = f"scale='if(gt(iw,ih),{max_size},-2)':'if(gt(iw,ih),-2,{max_size})'"
 
    cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-vf', scale_filter, 
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-r', str(fps),
        '-c:a', 'copy', # Copy audio
        output_path
    ]
    run_command(cmd)

def cut_video(input_path, output_path, start_time, end_time):
    """Cut a segment from the video."""
    duration = end_time - start_time
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', input_path,
        '-t', str(duration),
        '-c', 'copy', # Try stream copy first for speed
        output_path
    ]
    try:
        run_command(cmd)
    except subprocess.CalledProcessError:
        # If copy fails (e.g. keyframe issues), re-encode
        print("Stream copy failed, re-encoding...")
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', input_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-c:a', 'aac',
            output_path
        ]
        run_command(cmd)

def image_to_video(image_path, output_path, duration, fps=20, width=None, height=None):
    """Create a video from a single image."""
    if width is not None and height is not None:
        scale_filter = f"scale={width}:{height}"
    elif width is not None:
        scale_filter = f"scale={width}:-2"
    elif height is not None:
        scale_filter = f"scale=-2:{height}"
    else:
        scale_filter = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

    cmd = [
        'ffmpeg', '-y',
        '-loop', '1',
        '-i', image_path,
        '-c:v', 'libx264',
        '-t', str(duration),
        '-pix_fmt', 'yuv420p',
        '-vf', scale_filter,
        '-r', str(fps),
        output_path
    ]
    run_command(cmd)

def extract_frame(video_path, output_path, time_offset):
    """Extract a single frame as image."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(time_offset),
        '-i', video_path,
        '-vframes', '1',
        output_path
    ]
    run_command(cmd)

def concatenate_videos(video_paths, output_path):
    """Concatenate multiple videos."""
    if not video_paths:
        raise ValueError("No video paths provided")
        
    # Create a temporary file list
    list_file = f"concat_list_{os.getpid()}.txt"
    try:
        with open(list_file, 'w') as f:
            for path in video_paths:
                # Absolute path is safer
                abs_path = os.path.abspath(path)
                f.write(f"file '{abs_path}'\n")
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            output_path
        ]
        run_command(cmd)
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

def merge_audio_video(video_path, audio_path, output_path, loop_audio=False):
    """Merge audio and video."""
    # If loop_audio is True, we need to loop the audio stream
    
    cmd = ['ffmpeg', '-y', '-i', video_path]
    
    if loop_audio:
        # -stream_loop -1 before input audio
        cmd.extend(['-stream_loop', '-1'])
    
    cmd.extend(['-i', audio_path])
    
    # Map video from 0, audio from 1
    # -shortest to stop when video ends (if audio is looped or longer)
    # But if audio is shorter and NOT looped, we still want video length? 
    # Usually we want video length.
    
    cmd.extend([
        '-map', '0:v',
        '-map', '1:a',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        output_path
    ])
    
    run_command(cmd)

def resize_image_to_video(image_path, output_path, target_height, duration=0.5, fps=20):
    """Resize image and convert to video in one go."""
    # Scale filter
    scale_filter = f"scale=-2:{target_height}"
    
    cmd = [
        'ffmpeg', '-y',
        '-loop', '1',
        '-i', image_path,
        '-c:v', 'libx264',
        '-t', str(duration),
        '-pix_fmt', 'yuv420p',
        '-vf', f"{scale_filter}:trunc(ow/2)*2:trunc(oh/2)*2", # Ensure even dimensions after scale
        '-r', str(fps),
        output_path
    ]
    run_command(cmd)
