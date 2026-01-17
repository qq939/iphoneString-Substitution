import os
import sys
import time
import json
from datetime import datetime

import comfy_utils


def log_task_status(prompt_id, output_path=".log/test_connection", interval=2, max_rounds=60):
    directory = os.path.dirname(output_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i in range(max_rounds):
            timestamp = datetime.now().isoformat()
            try:
                history = comfy_utils.client.get_history(prompt_id)
            except Exception as e:
                history = {"error": str(e)}
            try:
                queue = comfy_utils.client.get_queue()
            except Exception as e:
                queue = {"error": str(e)}
            try:
                status = comfy_utils.client.is_task_running(prompt_id)
            except Exception as e:
                status = f"error: {e}"
            record = {
                "time": timestamp,
                "round": i,
                "prompt_id": prompt_id,
                "status": status,
                "history_keys": list(history.keys()) if isinstance(history, dict) else None,
                "raw_history": history,
                "queue": queue,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            time.sleep(interval)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python status_debug.py <prompt_id>")
        sys.exit(1)
    pid = sys.argv[1]
    log_task_status(pid)

