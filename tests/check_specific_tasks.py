
import sys
import os
import time
import requests

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import comfy_utils

def check_tasks():
    server_addr = "192.168.0.210:7860"
    task_ids = [
        "b97848c3-6b61-42df-a231-04cc61354f69", # Sector 9
        "5957c3fa-aeed-4467-a982-a53048fd1602"  # Sector 10
    ]
    
    # Initialize client manually if needed
    comfy_utils.client._set_server_address(server_addr)
    
    for tid in task_ids:
        try:
            status, result = comfy_utils.check_status(tid, server_addr)
            print(f"Task {tid}: {status}")
            if status == 'FAILED':
                 print(f"Error: {result}")
            elif status == 'SUCCEEDED':
                 print(f"Result: {result}")
        except Exception as e:
            print(f"Error checking {tid}: {e}")

if __name__ == "__main__":
    check_tasks()
