import requests
import time
import json
import os

BASE_URL = "http://127.0.0.1:5015"

def find_video_file():
    # Look for a video file in tmp or current directory to use for testing
    search_dirs = [
        os.path.join(os.path.dirname(__file__), 'tmp'),
        os.path.dirname(__file__)
    ]
    
    for d in search_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.lower().endswith(('.mp4', '.mov', '.avi')):
                    return os.path.join(d, f)
    return None

def test_video_analyzing():
    video_path = find_video_file()
    if not video_path:
        print("No video file found for testing /video_analyzing")
        return

    print(f"Submitting to /video_analyzing with video: {video_path}")
    
    try:
        with open(video_path, 'rb') as f:
            # Note: The field name must be 'file' as per the new endpoint
            files = {'file': f}
            response = requests.post(f"{BASE_URL}/video_analyzing", files=files)
            
            if response.status_code != 200:
                 print(f"Error submitting task: {response.status_code} - {response.text}")
                 return
                 
            data = response.json()
            
            if data['status'] != 'processing':
                print(f"Error submitting task: {data}")
                return
                
            task_id = data['task_id']
            print(f"Task ID: {task_id}")
            
            print("Polling for logs...")
            last_log_count = 0
            
            while True:
                status_res = requests.get(f"{BASE_URL}/check_sector_task/{task_id}")
                status_data = status_res.json()
                
                logs = status_data.get('logs', [])
                if len(logs) > last_log_count:
                    for log in logs[last_log_count:]:
                        print(f"LOG: {log}")
                    last_log_count = len(logs)
                
                status = status_data['status']
                if status in ['completed', 'failed']:
                    print(f"Task finished with status: {status}")
                    if status == 'failed':
                        print(f"Error: {status_data.get('error')}")
                    else:
                        print("Result:", status_data.get('result'))
                    break
                
                time.sleep(2)
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_video_analyzing()
