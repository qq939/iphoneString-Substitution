import os
import json
import requests
import logging
import uuid
import urllib.parse
import urllib.request
import shutil
import tempfile
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Server list for dual-try mechanism
SERVER_LIST = [
    "192.168.0.209:7860",
    "192.168.0.210:7860",
    "192.168.50.210:7860"
]

class ComfyUIClient:
    def __init__(self, server_address=None):
        self.client_id = str(uuid.uuid4())
        self.server_address = None
        self.base_url = None
        
        # If server_address is provided, try to use it
        if server_address:
            self._set_server_address(server_address)
        else:
            # Try to find the fastest server
            self.find_fastest_server()

    def _set_server_address(self, address):
        # Force HTTP as requested, removing HTTPS if present
        if address.startswith("https://"):
            address = address.replace("https://", "http://")
        elif not address.startswith("http://"):
            address = f"http://{address}"
            
        self.base_url = address.rstrip("/")
        self.server_address = self.base_url.replace("http://", "").replace("https://", "")
        logger.info(f"ComfyUIClient initialized with server: {self.base_url}")

    def find_fastest_server(self):
        """
        Pings all servers in SERVER_LIST concurrently and sets the base_url to the first one that responds.
        """
        logger.info("Attempting to find fastest server...")
        
        def check_server(server):
            try:
                # Force HTTP
                if server.startswith("https://"):
                    server = server.replace("https://", "http://")
                elif not server.startswith("http://"):
                    server = f"http://{server}"
                
                url = f"{server.rstrip('/')}/object_info"
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, timeout=5, headers=headers)
                if response.status_code == 200:
                    return server
            except:
                pass
            return None

        with ThreadPoolExecutor(max_workers=len(SERVER_LIST)) as executor:
            future_to_server = {executor.submit(check_server, server): server for server in SERVER_LIST}
            for future in as_completed(future_to_server):
                result = future.result()
                if result:
                    logger.info(f"Fastest server found: {result}")
                    self._set_server_address(result)
                    return True
        
        logger.warning("No available server found. Defaulting to first in list.")
        self._set_server_address(SERVER_LIST[0])
        return False

    def check_connection(self, timeout=5):
        """
        Checks if the server is reachable. If not, tries to switch to another server.
        """
        if not self.base_url:
            self.find_fastest_server()
            
        try:
            url = f"{self.base_url}/object_info"
            # Add headers to mimic browser/standard client
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, timeout=timeout, headers=headers)
            return response.status_code == 200
        except Exception as e:
            # logger.debug(f"Connection check failed: {e}") # Reduce noise
            # If connection fails, try to re-find server
            logger.info("Connection failed, attempting to switch server...")
            if self.find_fastest_server():
                return True
            return False

    def ensure_connection(self):
        """
        Ensures we have a valid connection.
        """
        return self.check_connection(timeout=5)

    def queue_prompt(self, prompt):
        """
        Sends the workflow to the server.
        """
        try:
            p = {"prompt": prompt, "client_id": self.client_id}
            data = json.dumps(p).encode('utf-8')
            
            url = f"{self.base_url}/prompt"
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as response:
                response_data = json.loads(response.read())
                if 'prompt_id' in response_data:
                    return response_data['prompt_id']
        except Exception as e:
            logger.warning(f"Failed to queue prompt: {e}")
            raise # Propagate exception to caller
            
        return None

    def get_history(self, prompt_id):
        """
        Queries history for the given prompt_id.
        """
        try:
            url = f"{self.base_url}/history/{prompt_id}"
            logger.info(f"Fetching ComfyUI history: {url}")
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                return data
        except Exception as e:
            logger.warning(f"Failed to get history for {prompt_id}: {e}")
            pass
        return {}

    def upload_file(self, file_path, subfolder="", overwrite=False):
        """
        Uploads file to the server.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            url = f"{self.base_url}/upload/image"
            
            with open(file_path, 'rb') as f:
                files = {'image': (os.path.basename(file_path), f)}
                data = {'overwrite': str(overwrite).lower(), 'subfolder': subfolder}
                response = requests.post(url, files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Upload failed with status {response.status_code}: {response.text}")
                    raise Exception(f"Upload failed: {response.status_code} - {response.text}")
        except Exception as e:
            logger.warning(f"Failed to upload file: {e}")
            raise # Propagate exception to caller
            
        return None
    
    def download_output_file(self, filename, subfolder="", file_type="output", output_dir="."):
        """
        Downloads a file from ComfyUI output.
        """
        try:
            params = {
                "filename": filename,
                "subfolder": subfolder,
                "type": file_type
            }
            query_string = urllib.parse.urlencode(params)
            url = f"{self.base_url}/view?{query_string}"
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            local_path = os.path.join(output_dir, filename)
            logger.info(f"Downloading {url} to {local_path}...")
            
            urllib.request.urlretrieve(url, local_path)
            return local_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise # Propagate exception
        
    def get_queue(self):
        """
        Gets the current queue status.
        """
        try:
            url = f"{self.base_url}/queue"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                return data
        except Exception as e:
            logger.error(f"Get queue failed: {e}")
            return {}
            
    def is_task_running(self, prompt_id):
        """
        Checks if a task is currently running or pending.
        """
        queue_data = self.get_queue()
        
        # Check pending
        for task in queue_data.get('queue_pending', []):
            if len(task) > 1 and task[1] == prompt_id:
                return "PENDING"
                
        # Check running
        for task in queue_data.get('queue_running', []):
            if len(task) > 1 and task[1] == prompt_id:
                return "RUNNING"
                
        return "NOT_FOUND"

    def cancel_task(self, prompt_id):
        """
        Cancels a task.
        """
        try:
            # 1. Try to delete from queue (if pending)
            url = f"{self.base_url}/queue"
            data = {"delete": [prompt_id]}
            data_json = json.dumps(data).encode('utf-8')
            
            req = urllib.request.Request(url, data=data_json, method='POST')
            try:
                urllib.request.urlopen(req)
            except:
                pass

            # 2. Check if running and interrupt
            status = self.is_task_running(prompt_id)
            if status == "RUNNING":
                url = f"{self.base_url}/interrupt"
                req = urllib.request.Request(url, data=b"", method='POST')
                urllib.request.urlopen(req)
            
            return True
        except Exception as e:
            logger.error(f"Cancel task failed: {e}")
            return False

# Initialize client
SERVER_ADDRESS = os.environ.get("COMFYUI_SERVER")
if SERVER_ADDRESS:
    client = ComfyUIClient(SERVER_ADDRESS)
else:
    client = ComfyUIClient()

# Helper functions for app.py
# These act as wrappers around the client instance

def submit_job_with_urls(character_url, video_url):
    temp_dir = tempfile.mkdtemp()
    try:
        # Download character
        char_filename = os.path.basename(character_url).split('?')[0] or "character.png"
        char_path = os.path.join(temp_dir, char_filename)
        with requests.get(character_url, stream=True) as r:
            r.raise_for_status()
            with open(char_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                    
        # Download video
        video_filename = os.path.basename(video_url).split('?')[0] or "video.mp4"
        video_path = os.path.join(temp_dir, video_filename)
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        
        return submit_job(char_path, video_path)
    except Exception as e:
        logger.error(f"Submit job with URLs failed: {e}")
        return None, str(e)
    finally:
        shutil.rmtree(temp_dir)

def submit_job(character_path, video_path):
    try:
        char_res = client.upload_file(character_path)
        video_res = client.upload_file(video_path)
        
        if not char_res or not video_res:
            return None, "Failed to upload files"
            
        return queue_workflow_template(char_res.get('name'), video_res.get('name'))
    except Exception as e:
        logger.error(f"Submit job error: {e}")
        return None, str(e)

def cancel_job(prompt_id):
    return client.cancel_task(prompt_id)

def queue_workflow_template(char_filename, video_filename, prompt_text=None, workflow_type='real'):
    try:
        if workflow_type == 'anime':
            workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '真人换动漫.json')
        else:
            workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '视频换人video_wan2_2_14B_animate.json')
            
        if not os.path.exists(workflow_path):
            return None, f"Workflow file not found: {workflow_path}"
            
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        # Update inputs
        if "10" in workflow: workflow["10"]["inputs"]["image"] = char_filename
        if "145" in workflow: workflow["145"]["inputs"]["file"] = video_filename
        if prompt_text and "21" in workflow: workflow["21"]["inputs"]["text"] = prompt_text
            
        # Randomize seed
        seed = random.randint(1, 1000000000000000)
        for node_id in ["232:63", "242:91", "64"]:
            if node_id in workflow and "inputs" in workflow[node_id] and "seed" in workflow[node_id]["inputs"]:
                workflow[node_id]["inputs"]["seed"] = seed
            
        prompt_id = client.queue_prompt(workflow)
        return (prompt_id, None) if prompt_id else (None, "Failed to queue prompt")
    except Exception as e:
        logger.error(f"Queue workflow template error: {e}")
        return None, str(e)

def check_status(prompt_id):
    try:
        history = client.get_history(prompt_id)
        if prompt_id in history:
            outputs = history[prompt_id].get('outputs', {})
            
            # Try to find output in preferred nodes or any node
            for node_id in ["243"] + list(outputs.keys()):
                if node_id in outputs:
                    node_output = outputs[node_id]
                    for type_key in ['gifs', 'videos', 'images', 'audio']:
                        files = node_output.get(type_key, [])
                        if files:
                            file_info = files[0]
                            return "SUCCEEDED", {
                                "filename": file_info.get('filename'),
                                "subfolder": file_info.get('subfolder', ''),
                                "type": file_info.get('type', 'output')
                            }
            return "FAILED", "No output found"
            
        status = client.is_task_running(prompt_id)
        if status in ["PENDING", "RUNNING"]:
            return status, None
        
        # Double check history to avoid race condition
        if prompt_id in client.get_history(prompt_id):
             return check_status(prompt_id) # Recursion safe as it will hit first block

        return "FAILED", "Task not found"
    except Exception as e:
        logger.error(f"Check status error: {e}")
        return "FAILED", str(e)

def download_result(file_info, output_dir):
    return client.download_output_file(
        file_info['filename'], 
        file_info['subfolder'], 
        file_info['type'], 
        output_dir
    )
