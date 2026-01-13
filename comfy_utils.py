import os
import json
import time
import requests
import logging
import websocket # pip install websocket-client
import uuid
import urllib.parse
import urllib.request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComfyUIClient:
    def __init__(self, server_address=["192.168.50.210:7860", "192.168.0.210:7860"]):
        self.client_id = str(uuid.uuid4())
        self.ws = None
        
        # Handle server_address input
        if isinstance(server_address, str):
            # Check if it looks like a JSON list (e.g. from env var)
            if server_address.strip().startswith('[') and server_address.strip().endswith(']'):
                try:
                    self.servers = json.loads(server_address)
                except json.JSONDecodeError:
                    self.servers = [server_address]
            else:
                self.servers = [server_address]
        elif isinstance(server_address, list):
            self.servers = server_address
        else:
            self.servers = ["127.0.0.1:8188"]
            
        # Do not find active server on init to prevent blocking
        # Default to first one or a placeholder
        self.server_address = self.servers[0].replace("http://", "").replace("https://", "").rstrip("/") if self.servers else "127.0.0.1:8188"
        logger.info(f"ComfyUIClient initialized. Active server detection deferred. Default: {self.server_address}")

    def _find_active_server(self):
        """
        Iterate through servers and find the first one that is reachable.
        """
        for server in self.servers:
            try:
                # Handle http/https prefix
                clean_server = server.replace("http://", "").replace("https://", "").rstrip("/")
                
                url = f"http://{clean_server}/object_info"
                logger.info(f"Checking connectivity to ComfyUI server: {url}")
                # Short timeout for connectivity check
                response = requests.get(url, timeout=5) # Increased timeout
                
                if response.status_code == 200:
                    logger.info(f"Successfully connected to ComfyUI server: {clean_server}")
                    return clean_server
            except Exception as e:
                logger.warning(f"Failed to connect to {server}: {e}")
        
        # Fallback to the first one if none work
        if self.servers:
            fallback = self.servers[0].replace("http://", "").replace("https://", "").rstrip("/")
            logger.warning(f"No active server found. Falling back to default: {fallback}")
            return fallback
        return "127.0.0.1:8188"

    def ensure_connection(self):
        """
        Ensures we have a valid connection or tries to find one.
        Returns True if connected/found, False otherwise.
        """
        if self.check_connection(timeout=1):
             return True
        
        new_server = self._find_active_server()
        if new_server:
            self.server_address = new_server
            return True
        return False

    def check_connection(self, timeout=2):
        """
        Checks if the current server address is reachable.
        If not, tries to find an active server again.
        """
        try:
            url = f"http://{self.server_address}/object_info"
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def upload_file(self, file_path, subfolder="", overwrite=False):
        """
        Uploads an image or video to ComfyUI.
        """
        try:
            url = f"http://{self.server_address}/upload/image"
            file_name = os.path.basename(file_path)
            
            with open(file_path, 'rb') as file:
                files = {'image': file}
                data = {
                    'subfolder': subfolder,
                    'overwrite': 'true' if overwrite else 'false'
                }
                logger.info(f"POST {url} with file={file_path}, data={data}")
                response = requests.post(url, files=files, data=data)
                
            if response.status_code == 200:
                response_data = response.json()
                # ComfyUI returns the filename (sometimes renamed) and subfolder/type
                logger.info(f"Upload response: {response_data}")
                return response_data
            else:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Upload exception: {e}")
            return None

    def queue_prompt(self, workflow):
        """
        Submits a workflow to the ComfyUI queue.
        """
        try:
            url = f"http://{self.server_address}/prompt"
            data = {"prompt": workflow, "client_id": self.client_id}
            data_json = json.dumps(data).encode('utf-8')
            
            logger.info(f"POST {url} with workflow (truncated): {str(data)[:200]}...")
            
            req = urllib.request.Request(url, data=data_json)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read())
                logger.info(f"Queue prompt response: {result}")
                return result.get('prompt_id')
        except Exception as e:
            logger.error(f"Queue prompt failed: {e}")
            return None

    def cancel_task(self, prompt_id):
        """
        Cancels a task.
        If pending: delete from queue.
        If running: interrupt.
        """
        try:
            # 1. Try to delete from queue (if pending)
            url = f"http://{self.server_address}/queue"
            data = {"delete": [prompt_id]}
            data_json = json.dumps(data).encode('utf-8')
            
            logger.info(f"Attempting to delete pending task {prompt_id} from queue...")
            req = urllib.request.Request(url, data=data_json, method='POST')
            try:
                with urllib.request.urlopen(req) as response:
                    logger.info(f"Delete queue response: {response.read().decode('utf-8')}")
            except Exception as e:
                logger.warning(f"Failed to delete from queue (might be running): {e}")

            # 2. Check if running and interrupt
            status = self.is_task_running(prompt_id)
            if status == "RUNNING":
                url = f"http://{self.server_address}/interrupt"
                logger.info(f"Task {prompt_id} is running. Sending interrupt...")
                req = urllib.request.Request(url, data=b"", method='POST')
                with urllib.request.urlopen(req) as response:
                    logger.info(f"Interrupt response: {response.read().decode('utf-8')}")
            
            return True
        except Exception as e:
            logger.error(f"Cancel task failed: {e}")
            return False

    def get_history(self, prompt_id):
        """
        Gets the history of a specific prompt.
        """
        try:
            url = f"http://{self.server_address}/history/{prompt_id}"
            logger.info(f"Fetching ComfyUI history: {url}")
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                # Log data but truncate if too long
                data_str = json.dumps(data)
                if len(data_str) > 1000:
                    logger.info(f"ComfyUI history response (truncated): {data_str[:1000]}...")
                else:
                    logger.info(f"ComfyUI history response: {data_str}")
                return data
        except Exception as e:
            # If 404, it might mean it's still running or not found
            # ComfyUI returns {} or error if not found in history (meaning potentially still in queue/running)
            logger.warning(f"Failed to get history for {prompt_id}: {e}")
            return {}

    def get_queue(self):
        """
        Gets the current queue status.
        """
        try:
            url = f"http://{self.server_address}/queue"
            logger.info(f"Fetching ComfyUI queue: {url}")
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                # Queue data can be huge, just log summary
                logger.info(f"ComfyUI queue response: Pending={len(data.get('queue_pending', []))}, Running={len(data.get('queue_running', []))}")
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
        # Task format in pending: [task_id, prompt_id, ...]
        for task in queue_data.get('queue_pending', []):
            if len(task) > 1 and task[1] == prompt_id:
                return "PENDING"
                
        # Check running
        # Task format in running: [task_id, prompt_id, ...]
        for task in queue_data.get('queue_running', []):
            if len(task) > 1 and task[1] == prompt_id:
                return "RUNNING"
                
        return "NOT_FOUND" # Could be finished or invalid

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
            url = f"http://{self.server_address}/view?{query_string}"
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            local_path = os.path.join(output_dir, filename)
            logger.info(f"Downloading {url} to {local_path}...")
            
            urllib.request.urlretrieve(url, local_path)
            return local_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

# Helper functions to be used by app.py

# Initialize client (Global instance or create per request? Better per request or global if stateless)
# We'll assume the server address is fixed or passed via env.
SERVER_ADDRESS = os.environ.get("COMFYUI_SERVER")
if SERVER_ADDRESS:
    client = ComfyUIClient(SERVER_ADDRESS)
else:
    # Use default list from __init__
    client = ComfyUIClient()

# Note: We deferred connection check, so client is ready immediately.

import tempfile
import shutil

def submit_job_with_urls(character_url, video_url):
    """
    Submits a job using URLs for character and video.
    Downloads files from URLs to temp storage, uploads to ComfyUI, and queues workflow.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Download character
        char_filename = os.path.basename(character_url)
        # Handle cases where url doesn't have a clean filename
        if '?' in char_filename:
            char_filename = char_filename.split('?')[0]
        if not char_filename:
            char_filename = "character.png"
            
        char_path = os.path.join(temp_dir, char_filename)
        logger.info(f"Downloading character from {character_url} to {char_path}")
        
        with requests.get(character_url, stream=True) as r:
            r.raise_for_status()
            with open(char_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    
        # Download video
        video_filename = os.path.basename(video_url)
        if '?' in video_filename:
            video_filename = video_filename.split('?')[0]
        if not video_filename:
            video_filename = "video.mp4"
            
        video_path = os.path.join(temp_dir, video_filename)
        logger.info(f"Downloading video from {video_url} to {video_path}")
        
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
        
        # Now submit using the local files
        return submit_job(char_path, video_path)
        
    except Exception as e:
        logger.error(f"Submit job with URLs failed: {e}")
        return None, str(e)
    finally:
        # Clean up temp dir
        shutil.rmtree(temp_dir)

def submit_job(character_path, video_path):
    """
    Orchestrates the whole process:
    1. Upload character image
    2. Upload video
    3. Load workflow template
    4. Update inputs
    5. Queue prompt
    """
    try:
        # 1. Upload files
        char_res = client.upload_file(character_path)
        video_res = client.upload_file(video_path)
        
        if not char_res or not video_res:
            return None, "Failed to upload files"
            
        char_filename = char_res.get('name')
        video_filename = video_res.get('name')
        
        return queue_workflow_template(char_filename, video_filename)
            
    except Exception as e:
        logger.error(f"Submit job error: {e}")
        return None, str(e)

def cancel_job(prompt_id):
    """
    Cancels a job by prompt_id.
    """
    return client.cancel_task(prompt_id)

def queue_workflow_template(char_filename, video_filename, prompt_text=None):
    """
    Loads workflow template, updates inputs, and queues prompt.
    """
    try:
        # 2. Load workflow
        workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '视频换人video_wan2_2_14B_animate.json')
        if not os.path.exists(workflow_path):
            return None, "Workflow file not found"
            
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        # 3. Update inputs
        # Node 10: LoadImage (Character)
        if "10" in workflow:
            workflow["10"]["inputs"]["image"] = char_filename
            
        # Node 145: LoadVideo (Video)
        if "145" in workflow:
            workflow["145"]["inputs"]["file"] = video_filename
            
        # Node 21: CLIPTextEncode (Positive Prompt)
        # Only update if prompt_text is provided and not empty
        if prompt_text and "21" in workflow:
            logger.info(f"Updating positive prompt with: {prompt_text}")
            workflow["21"]["inputs"]["text"] = prompt_text
            
        # Randomize seed for KSamplers to ensure new results
        # Nodes: 232:63 and 242:91 (KSampler)
        import random
        seed = random.randint(1, 1000000000000000)
        
        if "232:63" in workflow:
            workflow["232:63"]["inputs"]["seed"] = seed
        
        if "242:91" in workflow:
            workflow["242:91"]["inputs"]["seed"] = seed
            
        # 4. Queue prompt
        prompt_id = client.queue_prompt(workflow)
        
        if prompt_id:
            return prompt_id, None
        else:
            return None, "Failed to queue prompt"
    except Exception as e:
        logger.error(f"Queue workflow template error: {e}")
        return None, str(e)

def check_status(prompt_id):
    """
    Checks the status of the job.
    Returns: status (str), result (str/None)
    Status: PENDING, RUNNING, SUCCEEDED, FAILED
    """
    try:
        # Check history first (if finished)
        history = client.get_history(prompt_id)
        
        if prompt_id in history:
            # Task finished
            outputs = history[prompt_id].get('outputs', {})
            
            # We look for the final SaveVideo node (Node 243)
            # Or any video output if 243 is missing
            target_node_id = "243"
            
            if target_node_id in outputs:
                # SaveVideo often returns 'gifs' key for video files in API, or 'videos'
                # Sometimes it puts mp4 under 'images' too
                video_files = outputs[target_node_id].get('gifs', []) 
                if not video_files:
                     video_files = outputs[target_node_id].get('videos', [])
                if not video_files:
                     video_files = outputs[target_node_id].get('images', [])
                
                if video_files:
                    # Found video
                    file_info = video_files[0]
                    filename = file_info.get('filename')
                    subfolder = file_info.get('subfolder', '')
                    file_type = file_info.get('type', 'output')
                    
                    # Download URL (or local path if we want to download it)
                    # We should download it to our static folder
                    # Return the download link
                    return "SUCCEEDED", {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": file_type
                    }
            
            # If we didn't find the specific node, look for any video output
            for node_id, node_output in outputs.items():
                video_files = node_output.get('videos', []) + node_output.get('gifs', []) + node_output.get('images', [])
                if video_files:
                    # Check if it looks like a video file
                    file_info = video_files[0]
                    fname = file_info.get('filename', '').lower()
                    if fname.endswith('.mp4') or fname.endswith('.mov') or fname.endswith('.webm') or fname.endswith('.gif'):
                        return "SUCCEEDED", {
                            "filename": file_info.get('filename'),
                            "subfolder": file_info.get('subfolder', ''),
                            "type": file_info.get('type', 'output')
                        }

            return "FAILED", "No output video found"
            
        # If not in history, check queue
        status = client.is_task_running(prompt_id)
        if status in ["PENDING", "RUNNING"]:
            return status, None
        
        # If not in queue and not in history, double check history just in case it finished while we were checking queue
        # Or maybe invalid ID
        history = client.get_history(prompt_id)
        if prompt_id in history:
            # Recursive call or just duplicate logic? Let's just return success for now to trigger next poll loop logic if called again
            # Or better, just copy the success logic. 
            # For simplicity, let's return a special status or just NOT_FOUND if truly gone.
            # But wait, if it finished between the first history check and the queue check, it would be in history now.
            # So let's return NOT_FOUND only if truly missing.
            pass

        return "FAILED", "Task not found in queue or history"
        
    except Exception as e:
        logger.error(f"Check status error: {e}")
        return "FAILED", str(e)

def download_result(file_info, output_dir):
    """
    Downloads the result file from ComfyUI to local directory.
    """
    return client.download_output_file(
        file_info['filename'], 
        file_info['subfolder'], 
        file_info['type'], 
        output_dir
    )
