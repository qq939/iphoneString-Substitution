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

def test_sector19_i2v():
    video_path = find_video_file()
    if not video_path:
        print("No video file found for testing Sector 19")
        return

    print(f"Submitting Sector 19 task with video: {video_path} and checking I2V trigger...")
    
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
            completed = False
            i2v_triggered = False
            
            # Poll for a bit longer even after completion to catch I2V logs
            max_retries_after_complete = 10
            retries_after_complete = 0
            
            while True:
                status_res = requests.get(f"{BASE_URL}/check_sector_task/{task_id}")
                status_data = status_res.json()
                
                logs = status_data.get('logs', [])
                if len(logs) > last_log_count:
                    for log in logs[last_log_count:]:
                        print(f"LOG: {log}")
                        if "I2V Task started successfully" in log:
                            i2v_triggered = True
                    last_log_count = len(logs)
                
                status = status_data['status']
                if status in ['completed', 'failed']:
                    if not completed:
                        print(f"Task finished with status: {status}")
                        if status == 'failed':
                            print(f"Error: {status_data.get('error')}")
                            break
                        else:
                            print("Result:", status_data.get('result'))
                        completed = True
                    
                    # If completed, wait for I2V trigger log
                    if completed and not i2v_triggered:
                        retries_after_complete += 1
                        if retries_after_complete > max_retries_after_complete:
                            print("Timeout waiting for I2V trigger logs.")
                            break
                        time.sleep(1)
                        continue
                    
                    if i2v_triggered:
                        print("SUCCESS: I2V Task triggered successfully.")
                        break
                
                time.sleep(2)
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_sector19_i2v()
