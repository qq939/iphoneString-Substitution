import requests
import json
import time

BASE_URL = "http://127.0.0.1:5015"

GROUP_IDS = [
    "61f00435-9cee-4c6c-ab27-cf94ba8e5b43", # Sector 17
    "37a513af-af50-4790-832d-54d7dab60296", # Sector 19
    "cd1dac2e-6db3-49a4-a83d-9970bebf3168"  # Sector 9-12 Batch
]

def check_groups():
    for group_id in GROUP_IDS:
        print(f"\nChecking Group ID: {group_id}")
        try:
            response = requests.get(f"{BASE_URL}/check_group_status/{group_id}")
            if response.status_code != 200:
                print(f"Error: {response.status_code} - {response.text}")
                continue
            
            data = response.json()
            print(f"Status: {data.get('status')}")
            tasks = data.get('tasks', [])
            for i, task in enumerate(tasks):
                print(f"  Task {i}: ID={task.get('task_id')}, Status={task.get('status')}, Server={task.get('server')}, Idx={task.get('segment_index')}")
                if task.get('status') == 'completed':
                     print(f"    Result: {task.get('result_path')}")
        except Exception as e:
            print(f"Exception checking group {group_id}: {e}")

if __name__ == "__main__":
    check_groups()
