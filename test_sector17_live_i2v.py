import requests
import time
import json
import sys

BASE_URL = "http://127.0.0.1:5015"

def test_sector17_i2v():
    print("Submitting Sector 17 task with I2V trigger check...")
    # Use a simple query
    payload = {'text': '一只小猫在草地上奔跑'}
    
    try:
        response = requests.post(f"{BASE_URL}/sector17_submit", data=payload)
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
    test_sector17_i2v()
