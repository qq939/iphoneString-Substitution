import time
import sys
import os
import logging
import threading

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_test():
    # 1. Initialize Flask test client
    client = app.app.test_client()
    
    # 2. Check ComfyUI connection
    logger.info("Checking ComfyUI connection...")
    try:
        app.ensure_comfy_connection()
        logger.info(f"ComfyUI Connected: {app.COMFY_STATUS['ip']}")
    except Exception as e:
        logger.error(f"ComfyUI Connection Failed: {e}")
        return

    # 3. Trigger Sector 9 Task
    logger.info("Triggering Sector 9 I2V Task...")
    try:
        resp = client.post('/generate_i2v_group', json={"texts": ["Test Sector 9 Auto Trigger", "", "", ""]})
        if resp.status_code != 200:
            logger.error(f"Failed to trigger Sector 9: {resp.data}")
            return
        g9_data = resp.get_json()
        g9_id = g9_data['group_id']
        logger.info(f"Sector 9 Task Started. Group ID: {g9_id}")
    except Exception as e:
        logger.error(f"Exception triggering Sector 9: {e}")
        return

    # 4. Trigger Sector 10 Task
    logger.info("Triggering Sector 10 I2V Task...")
    try:
        resp = client.post('/generate_i2v_group', json={"texts": ["", "Test Sector 10 Auto Trigger", "", ""]})
        if resp.status_code != 200:
            logger.error(f"Failed to trigger Sector 10: {resp.data}")
            return
        g10_data = resp.get_json()
        g10_id = g10_data['group_id']
        logger.info(f"Sector 10 Task Started. Group ID: {g10_id}")
    except Exception as e:
        logger.error(f"Exception triggering Sector 10: {e}")
        return

    # 5. Monitor Loop
    logger.info("Monitoring tasks... (This may take several minutes)")
    
    monitored_groups = {g9_id: "Sector 9", g10_id: "Sector 10"}
    completed_groups = set()
    
    # We also need to monitor triggered transition groups (Sector 13, 14)
    # Since we don't know their IDs yet (they are created dynamically), we check the global dict
    triggered_sectors = {} # '13': group_id, '14': group_id
    
    start_time = time.time()
    
    while True:
        if time.time() - start_time > 1200: # 20 minutes timeout (real generation is slow)
            logger.error("Test Timed Out")
            break
            
        # Check I2V Groups
        for gid, name in monitored_groups.items():
            if gid in completed_groups:
                continue
                
            status_resp = client.get(f'/check_group_status/{gid}')
            status = status_resp.get_json()
            
            if status['status'] == 'completed':
                logger.info(f"✅ {name} Completed! Final Video: {status['final_url']}")
                completed_groups.add(gid)
            elif status['status'] == 'failed':
                logger.error(f"❌ {name} Failed: {status['error']}")
                completed_groups.add(gid)
            else:
                # Log progress periodically? Too verbose.
                pass
        
        # Check for triggered transition groups
        # We access the global variable in app directly to see if new groups are assigned
        for sector, gid in app.CHANNEL_TRANSITION_GROUPS.items():
            if gid and sector in ['13', '14'] and sector not in triggered_sectors:
                logger.info(f"🚀 Auto-Trigger Detected! Sector {sector} Transition Group ID: {gid}")
                triggered_sectors[sector] = gid
        
        # Monitor Triggered Groups
        all_triggered_done = True
        for sector, gid in triggered_sectors.items():
            status_resp = client.get(f'/check_group_status/{gid}')
            status = status_resp.get_json()
            
            if status['status'] == 'processing':
                all_triggered_done = False
                # logger.info(f"Sector {sector} Transition Processing...")
            elif status['status'] == 'completed':
                if f"sec{sector}_done" not in completed_groups:
                    logger.info(f"✅ Sector {sector} Transition Workflow Completed! Final Video: {status['final_url']}")
                    completed_groups.add(f"sec{sector}_done")
            elif status['status'] == 'failed':
                if f"sec{sector}_done" not in completed_groups:
                    logger.error(f"❌ Sector {sector} Transition Failed: {status['error']}")
                    completed_groups.add(f"sec{sector}_done")

        # Exit condition
        if len(completed_groups) >= 2 + len(triggered_sectors) and len(triggered_sectors) >= 2:
             logger.info("🎉 All tasks and triggered workflows completed!")
             break
             
        # If I2V completed but no trigger detected after some time
        if len(completed_groups) >= 2 and len(triggered_sectors) == 0:
             # Wait a bit more for trigger logic to run
             if time.time() - start_time > 600: # If 10 mins passed and no trigger
                 pass

        time.sleep(5)

if __name__ == "__main__":
    run_test()
