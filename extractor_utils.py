import os
import requests
import json
import time
import shutil
import math
import base64
import cv2
import yt_dlp
import numpy as np
import logging
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import dotenv

# Load environment variables
dotenv.load_dotenv()
dotenv.load_dotenv("asset/.env")

# ========== GLOBAL PARAMETERS ==========

# Bilibili Search API
# Used in: search_bilibili (Line 130)
SEARCH_API_URL = "https://api.bilibili.com/x/web-interface/search/type"

# Bilibili Video Detail API (for likes)
# Used in: get_video_likes (Line 104)
VIDEO_DETAIL_URL = "https://api.bilibili.com/x/web-interface/view"

# Max video duration in seconds for search filter
# Used in: search_bilibili (Line 156)
MAX_DURATION_SECONDS = 120

# Search result limit
# Used in: search_bilibili (Line 137)
SEARCH_RESULT_LIMIT = 20

# LLM Model Name
# Used in: call_llm_vlm (Line 289)
LLM_MODEL = "glm-4.6v" # defaulting to 4.6v as requested, mapped to glm-4v if needed by provider

# LLM Base URL
# Used in: call_llm_vlm (Line 290)
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# Screenshot Max Side Length
# Used in: analyze_video (Line 345 -> resize_image)
MAX_SIDE = 640

# Grid Size for image stitching
# Used in: analyze_video (Line 368 -> create_grid_image)
GRID_SIZE = 3

# Directory for additional context resources
# Used in: analyze_video (Line 377)
RESOURCE_DIR = ".resources"

# Headers for Bilibili requests
# Used in: search_bilibili, get_video_likes
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Cookie": "buvid3=infoc;"
}

# Logger setup
logger = logging.getLogger(__name__)

# ========== SEARCH MODULE ==========

def parse_duration(duration_str: str) -> int:
    """
    Convert duration string "MM:SS" or "HH:MM:SS" to seconds.
    """
    if not duration_str:
        return 0
    
    parts = duration_str.split(':')
    seconds = 0
    try:
        if len(parts) == 2:
            seconds = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return seconds

def get_video_likes(bvid: str) -> int:
    """
    Get video like count.
    """
    try:
        params = {"bvid": bvid}
        response = requests.get(VIDEO_DETAIL_URL, params=params, headers=HEADERS, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("stat", {}).get("like", 0)
    except Exception:
        pass
    return 0

def search_bilibili(keyword: str) -> str | None:
    """
    Search Bilibili for video with highest likes and duration <= MAX_DURATION_SECONDS.
    """
    if not keyword:
        return None
        
    try:
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page_size": SEARCH_RESULT_LIMIT
        }
        
        response = requests.get(SEARCH_API_URL, params=params, headers=HEADERS, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") != 0:
            print(f"Bilibili API Error: {data.get('message')}")
            return None
            
        data_data = data.get("data", {})
        if data_data.get("numResults") == 0:
            return None
            
        result_data = data_data.get("result", [])
        
        if not result_data or not isinstance(result_data, list):
            return None
            
        # Filter candidates
        candidates = []
        for video in result_data:
            duration_str = video.get("duration", "")
            duration_seconds = parse_duration(duration_str)
            
            if duration_seconds <= MAX_DURATION_SECONDS:
                bvid = video.get("bvid")
                arcurl = video.get("arcurl")
                if bvid:
                    candidates.append({
                        "bvid": bvid,
                        "arcurl": arcurl or f"https://www.bilibili.com/video/{bvid}",
                        "likes": 0 
                    })
        
        if not candidates:
            return None
            
        # Get likes concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_video = {executor.submit(get_video_likes, video["bvid"]): video for video in candidates}
            for future in as_completed(future_to_video):
                video = future_to_video[future]
                try:
                    likes = future.result()
                    video["likes"] = likes
                except Exception:
                    video["likes"] = 0
        
        # Sort by likes descending
        candidates.sort(key=lambda x: x["likes"], reverse=True)
        
        if candidates:
            best_video = candidates[0]
            print(f"Selected video: {best_video['arcurl']} with {best_video['likes']} likes")
            return best_video['arcurl']
            
        return None
        
    except Exception as e:
        print(f"Search error: {e}")
        return None

# ========== DOWNLOAD MODULE ==========

def download_video(url: str, output_dir: str) -> str | None:
    """
    Download video using yt-dlp.
    """
    if not url or not output_dir:
        return None
        
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        else:
            # Clean directory for fresh download
            shutil.rmtree(output_dir)
            os.makedirs(output_dir)
            
        # Rely on system ffmpeg
        ffmpeg_path = "ffmpeg"
        print(f"Using ffmpeg from system path")

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'ffmpeg_location': ffmpeg_path,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                return ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as e:
            print(f"Preferred format download failed: {e}")
            print("Retrying with video-only fallback...")
            
            try:
                 ydl_opts['format'] = 'bestvideo'
                 if 'merge_output_format' in ydl_opts:
                     del ydl_opts['merge_output_format']
                     
                 with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        return None
                    return ydl.prepare_filename(info)
            except yt_dlp.utils.DownloadError as e2:
                 print(f"Fallback download failed: {e2}")
                 return None

    except Exception as e:
        print(f"Download error: {e}")
        return None

# ========== ANALYZE MODULE ==========

def resize_image(image: Image.Image, max_side: int) -> Image.Image:
    """Resize image so that the longest side is at most max_side."""
    width, height = image.size
    if max(width, height) <= max_side:
        return image
    
    if width > height:
        new_width = max_side
        new_height = int(height * (max_side / width))
    else:
        new_height = max_side
        new_width = int(width * (max_side / height))
        
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

def draw_time_on_image(image: Image.Image, time_str: str) -> Image.Image:
    """Draw time string on image."""
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()
        
    text = time_str
    x, y = 10, 10
    # Outline
    draw.text((x-1, y), text, font=font, fill="black")
    draw.text((x+1, y), text, font=font, fill="black")
    draw.text((x, y-1), text, font=font, fill="black")
    draw.text((x, y+1), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="red")
    return image

def create_grid_image(images: List[Image.Image], grid_size: int = 3) -> Image.Image:
    """Create a grid image from a list of images."""
    if not images:
        return None
        
    cell_width = 0
    cell_height = 0
    for img in images:
        cell_width = max(cell_width, img.width)
        cell_height = max(cell_height, img.height)
        
    grid_w = cell_width * grid_size
    grid_h = cell_height * grid_size
    
    grid_img = Image.new('RGB', (grid_w, grid_h), color='black')
    
    for i, img in enumerate(images):
        row = i // grid_size
        col = i % grid_size
        x = col * cell_width
        y = row * cell_height
        
        x_offset = (cell_width - img.width) // 2
        y_offset = (cell_height - img.height) // 2
        
        grid_img.paste(img, (x + x_offset, y + y_offset))
        
    return grid_img

def encode_image_base64(image: Image.Image) -> str:
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def call_llm_vlm(prompt_text: str, images: List[Image.Image], log_callback=None) -> str:
    """
    Call VLM using LangChain and ChatOpenAI compatible API
    """
    print(f"Calling LLM with {len(images)} images and prompt length: {len(prompt_text)}")
    
    if log_callback:
        log_callback(f"Constructing LLM request...")
        log_callback(f"Human Prompt:\n{prompt_text}")
        log_callback(f"System Prompt: (Using default for {LLM_MODEL})")
        log_callback(f"Image Count: {len(images)}")
        log_callback(f"LLM Model: {LLM_MODEL}")
        log_callback(f"LLM Base URL: {LLM_BASE_URL}")

    
    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        return "Error: ZAI_API_KEY environment variable not set."

    # Map model name if necessary (glm-4.6v -> glm-4v if provider requires)
    # Zhipu usually uses glm-4v
    model_name = "glm-4v" if LLM_MODEL == "glm-4.6v" else LLM_MODEL

    try:
        llm = ChatOpenAI(
            model=model_name,
            base_url=LLM_BASE_URL,
            api_key=api_key,
            temperature=0.7
        )
        
        content = [{"type": "text", "text": prompt_text}]
        
        for img in images:
            base64_image = encode_image_base64(img)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
            
        messages = [
            HumanMessage(content=content)
        ]
        
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        print(f"LLM Call Error: {e}")
        return f"Error calling LLM: {e}"

def analyze_video(video_path: str, resource_dir: str, log_callback=None) -> str:
    """
    Analyze video and generate prompt.
    """
    if log_callback: log_callback(f"Analyzing video: {video_path}")
    
    if not video_path:
        return "Error: No video path provided"
        
    resource_output_dir = os.path.dirname(video_path)
    if resource_output_dir and not os.path.exists(resource_output_dir):
        os.makedirs(resource_output_dir)

    # 1. Open Video
    if log_callback: log_callback("Opening video file...")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return "Error: Could not open video"
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 30 # Default
        
    # Sample 1 frame per second
    frame_interval = int(fps) 
    frame_count = 0
    seconds = 0
    
    captured_images = []
    
    if log_callback: log_callback("Extracting frames (1 fps)...")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % frame_interval == 0:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            pil_img = resize_image(pil_img, MAX_SIDE)
            time_str = f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"
            pil_img = draw_time_on_image(pil_img, time_str)
            captured_images.append(pil_img)
            seconds += 1
                
        frame_count += 1
        
    cap.release()
    
    if not captured_images:
        return "Error: No frames captured from video"
    
    if log_callback: log_callback(f"Extracted {len(captured_images)} frames.")

    # 2. Create Grid Images
    if log_callback: log_callback("Creating grid images...")
    grid_images = []
    chunk_size = GRID_SIZE * GRID_SIZE
    
    for i in range(0, len(captured_images), chunk_size):
        chunk = captured_images[i:i + chunk_size]
        grid_img = create_grid_image(chunk, GRID_SIZE)
        if grid_img:
            grid_images.append(grid_img)
            
    for i, img in enumerate(grid_images):
        grid_filename = f"grid_{i}.jpg"
        grid_path = os.path.join(resource_output_dir, grid_filename)
        img.save(grid_path)
        if log_callback: log_callback(f"Saved grid image to: {grid_path}")

    # Limit number of grid images to avoid LLM API limits (e.g. Zhipu limit)
    # If we have too many, sample them uniformly
    MAX_GRID_IMAGES = 4
    if len(grid_images) > MAX_GRID_IMAGES:
        if log_callback: log_callback(f"Sampling {MAX_GRID_IMAGES} grid images from {len(grid_images)}...")
        indices = np.linspace(0, len(grid_images) - 1, MAX_GRID_IMAGES, dtype=int)
        grid_images = [grid_images[i] for i in indices]
    
    if log_callback: log_callback(f"Prepared {len(grid_images)} grid images for analysis.")

    # 3. Construct Prompt
    context = ""
    if os.path.exists(resource_dir):
        try:
            for filename in os.listdir(resource_dir):
                if filename.endswith(".txt"):
                    file_path = os.path.join(resource_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context += f"\n[{filename}]: {f.read()}"
        except Exception as e:
            print(f"Error reading resources: {e}")
            if log_callback: log_callback(f"Warning: Error reading resources: {e}")
            
    prompt = f"""
    用400字描述视频截图内容，突出人物动作和场景描述。
    
    Additional Context (if any):
    {context}
    """
    
    # 4. Call LLM
    if log_callback: log_callback("Calling LLM for analysis...")
    
    # Get the first captured image as reference for I2V
    reference_image_path = None
    if captured_images:
        # Save the first frame (without time overlay if possible? captured_images has time overlay)
        # We want the clean frame ideally, but we only have overlayed ones in captured_images.
        # Wait, captured_images has time overlay drawn on it.
        # "draw_time_on_image" modifies it in place or returns new? It returns new PIL image.
        # But we overwrite captured_images list with them.
        # It's fine, let's use the one with time or just use the first grid image?
        # Actually, let's use the first extracted frame.
        ref_img = captured_images[0]
        reference_image_path = os.path.join(resource_output_dir, "reference_frame.jpg")
        ref_img.save(reference_image_path)
        if log_callback: log_callback(f"Saved reference frame to: {reference_image_path}")

    prompt_content = call_llm_vlm(prompt, grid_images, log_callback=log_callback)
    return prompt_content, reference_image_path

# ========== MAIN WORKFLOW ==========

def process_query_to_prompt(query: str, output_dir: str, log_callback=None) -> tuple[str, str | None]:
    """
    Full workflow: Search -> Download -> Analyze -> Return (Prompt, ImagePath)
    """
    if log_callback: log_callback(f"Processing query: {query}")
    print(f"Processing query: {query}")
    
    # 1. Search
    if log_callback: log_callback("Searching Bilibili...")
    video_url = search_bilibili(query)
    if not video_url:
        return "Error: Video not found for query.", None
        
    print(f"Found video: {video_url}")
    if log_callback: log_callback(f"Found video URL: {video_url}")
    
    # 2. Download
    if log_callback: log_callback("Downloading video...")
    video_path = download_video(video_url, output_dir)
    if not video_path:
        return "Error: Video download failed.", None
        
    print(f"Video downloaded to: {video_path}")
    if log_callback: log_callback(f"Video downloaded to: {video_path}")
    
    # 3. Analyze
    prompt, image_path = analyze_video(video_path, RESOURCE_DIR, log_callback=log_callback)
    
    # Cleanup downloaded video (optional, maybe keep it?)
    # For now, let's keep it as per original logic which saved it to output_dir
    
    return prompt, image_path
