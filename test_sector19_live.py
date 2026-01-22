import requests
import time
import os

BASE_URL = "http://127.0.0.1:5015"
# Use the file downloaded by Sector 17 test if available, or any small video
# I'll search for a mp4 file in tmp
TMP_DIR = "/Users/jiang/Downloads/Substitution/tmp"

def find_video_file():
    for root, dirs, files in os.walk(TMP_DIR):
        for file in files:
            if file.endswith(".mp4"):
                return os.path.join(root, file)
    return None

def test_sector19():
    video_path = find_video_file()
    if not video_path:
        print("No video file found for testing Sector 19")
        return

    print(f"Submitting Sector 19 task with video: {video_path}")
    
    try:
        with open(video_path, 'rb') as f:
            files = {'video': f}
            response = requests.post(f"{BASE_URL}/sector19_submit", files=files)
            response.raise_for_status()
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
                
                if status_data['status'] in ['completed', 'failed']:
                    print(f"Task finished with status: {status_data['status']}")
                    if status_data['status'] == 'failed':
                        print(f"Error: {status_data.get('error')}")
                    else:
                        print("Result:", status_data.get('result'))
                    break
                
                time.sleep(2)
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_sector19()
