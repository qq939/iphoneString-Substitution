import requests
import json
import time

BASE_URL = "http://127.0.0.1:5015"

def trigger_batch():
    print("Triggering batch I2V (Sector 9-12 simulation)...")
    payload = {
        'texts': [
            "A cute cat running on grass",  # Sector 9 -> 13
            "A dog jumping in the park",    # Sector 10 -> 14
            "A bird flying in the sky",     # Sector 11 -> 15
            "A fish swimming in the ocean"  # Sector 12 -> 16
        ]
    }
    
    try:
        response = requests.post(f"{BASE_URL}/generate_i2v_group", json=payload)
        response.raise_for_status()
        data = response.json()
        
        group_id = data.get('group_id')
        print(f"Batch I2V triggered. Group ID: {group_id}")
        return group_id
    except Exception as e:
        print(f"Error triggering batch: {e}")
        return None

def monitor_group(group_id):
    if not group_id: return
    
    print(f"Monitoring Group {group_id}...")
    while True:
        try:
            res = requests.get(f"{BASE_URL}/check_group_status/{group_id}")
            data = res.json()
            status = data.get('status')
            print(f"Group Status: {status}")
            
            tasks = data.get('tasks', [])
            completed_count = 0
            for task in tasks:
                t_status = task.get('status')
                idx = task.get('segment_index')
                print(f"  Task {idx}: {t_status}")
                if t_status == 'completed':
                    completed_count += 1
            
            if status in ['completed', 'failed']:
                print("Group finished.")
                break
                
            # If all tasks are completed, the group should be completed soon
            if completed_count == len(tasks) and len(tasks) > 0:
                print("All tasks completed. Waiting for group update...")
            
            time.sleep(5)
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    gid = trigger_batch()
    # monitor_group(gid) # Optional: don't block indefinitely in this script
