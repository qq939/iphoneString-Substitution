import requests
import time
import json

BASE_URL = "http://127.0.0.1:5015"

def test_sector17():
    print("Submitting Sector 17 task...")
    # Use a simple query that is likely to find results
    payload = {'text': '你好'}
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
    test_sector17()
