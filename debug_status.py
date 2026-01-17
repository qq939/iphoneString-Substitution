import sys
import os
import logging
import json

# Ensure we can import comfy_utils
sys.path.append(os.getcwd())
import comfy_utils

# Configure logging to file
log_dir = '.log'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
    
log_file = os.path.join(log_dir, 'test_connection')

# Setup logger
logger = logging.getLogger('debug_status')
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream handler (console)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

def check_task(prompt_id):
    logger.info(f"=== Checking status for task: {prompt_id} ===")
    
    # We use the updated check_status which checks all servers if no server specified
    # Or we can explicitly iterate here to show details in the log
    
    servers = comfy_utils.SERVER_LIST
    logger.info(f"Servers to check: {servers}")
    
    found = False
    for server in servers:
        logger.info(f"Querying server: {server}")
        try:
            # Check history
            history = comfy_utils.client.get_history(prompt_id, server)
            if history is None:
                logger.warning(f"  Network error querying history on {server}")
            elif prompt_id in history:
                logger.info(f"  Found in history on {server}!")
                logger.info(f"  Response: {json.dumps(history[prompt_id], indent=2, ensure_ascii=False)}")
                found = True
                break
            else:
                logger.info(f"  Not found in history on {server}")
                
            # Check queue
            status = comfy_utils.client.is_task_running(prompt_id, server)
            if status == "UNKNOWN":
                 logger.warning(f"  Network error querying queue on {server}")
            else:
                 logger.info(f"  Queue status on {server}: {status}")
                 if status in ["PENDING", "RUNNING"]:
                     found = True
                     break
                     
        except Exception as e:
            logger.error(f"  Error querying {server}: {e}")
            
    if not found:
        logger.info("Task not found on any server.")
        
    # Also call the main check_status function to verify its return value
    logger.info("Calling comfy_utils.check_status()...")
    final_status, final_result = comfy_utils.check_status(prompt_id)
    logger.info(f"Final Status: {final_status}")
    logger.info(f"Final Result: {final_result}")
    logger.info("===========================================")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_status.py <prompt_id1> [prompt_id2 ...]")
        sys.exit(1)
        
    for pid in sys.argv[1:]:
        check_task(pid)
