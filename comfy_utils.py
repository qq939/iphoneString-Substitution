import os
import json
import time
import requests
import logging
import websocket # pip install websocket-client
import uuid
import urllib.parse
import urllib.request
import shutil
import tempfile
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComfyUIClient:
    def __init__(self, server_address="dimond.top:7860"):
        self.client_id = str(uuid.uuid4())
        self.ws = None
        self.server_address = server_address.replace("http://", "").replace("https://", "").rstrip("/")
        logger.info(f"ComfyUIClient initialized with server: {self.server_address}")

    def check_connection(self, timeout=5):
        """
        Checks if the server is reachable.
        """
        try:
            url = f"http://{self.server_address}/object_info"
            response = requests.get(url, timeout=timeout)
            return response.status_code == 200
        except:
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
            
            url = f"http://{self.server_address}/prompt"
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as response:
                response_data = json.loads(response.read())
                if 'prompt_id' in response_data:
                    return response_data['prompt_id']
        except Exception as e:
            logger.warning(f"Failed to queue prompt: {e}")
            
        return None

    def get_history(self, prompt_id):
        """
        Queries history for the given prompt_id.
        """
        try:
            url = f"http://{self.server_address}/history/{prompt_id}"
            logger.info(f"Fetching ComfyUI history: {url}")
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                # Log data but truncate if too long
                data_str = json.dumps(data)
                if len(data_str) > 1000:
                    logger.info(f"ComfyUI history response (truncated): {data_str[:1000]}...")
                else:
                    logger.info(f"ComfyUI history response: {data_str}")
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
            return None

        try:
            url = f"http://{self.server_address}/upload/image"
            
            with open(file_path, 'rb') as f:
                files = {'image': (os.path.basename(file_path), f)}
                data = {'overwrite': str(overwrite).lower(), 'subfolder': subfolder}
                response = requests.post(url, files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.warning(f"Failed to upload file: {e}")
            
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
        
    def get_queue(self):
        """
        Gets the current queue status.
        """
        try:
            url = f"http://{self.server_address}/queue"
            logger.info(f"Fetching ComfyUI queue: {url}")
            with urllib.request.urlopen(url, timeout=10) as response:
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
                
        return "NOT_FOUND"

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

# Helper functions to be used by app.py

# Initialize client
SERVER_ADDRESS = os.environ.get("COMFYUI_SERVER")
if SERVER_ADDRESS:
    client = ComfyUIClient(SERVER_ADDRESS)
else:
    client = ComfyUIClient()

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

def queue_workflow_template(char_filename, video_filename, prompt_text=None, workflow_type='real'):
    """
    Loads workflow template, updates inputs, and queues prompt.
    workflow_type: 'real' or 'anime'
    """
    try:
        # 2. Load workflow
        if workflow_type == 'anime':
            workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '真人换动漫.json')
        else:
            workflow_path = os.path.join(os.path.dirname(__file__), 'comfyapi', '视频换人video_wan2_2_14B_animate.json')
            
        if not os.path.exists(workflow_path):
            return None, f"Workflow file not found: {workflow_path}"
            
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
        seed = random.randint(1, 1000000000000000)
        
        # Real Workflow Nodes
        if "232:63" in workflow:
            workflow["232:63"]["inputs"]["seed"] = seed
        
        if "242:91" in workflow:
            workflow["242:91"]["inputs"]["seed"] = seed
            
        if "64" in workflow and "inputs" in workflow["64"] and "seed" in workflow["64"]["inputs"]:
             workflow["64"]["inputs"]["seed"] = seed
            
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
                video_files = outputs[target_node_id].get('gifs', []) 
                if not video_files:
                     video_files = outputs[target_node_id].get('videos', [])
                if not video_files:
                     video_files = outputs[target_node_id].get('images', [])
                if not video_files:
                     video_files = outputs[target_node_id].get('audio', [])
                
                if video_files:
                    # Found output
                    file_info = video_files[0]
                    filename = file_info.get('filename')
                    subfolder = file_info.get('subfolder', '')
                    file_type = file_info.get('type', 'output')
                    
                    return "SUCCEEDED", {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": file_type
                    }
            
            # If we didn't find the specific node, look for any output
            for node_id, node_output in outputs.items():
                files = node_output.get('videos', []) + node_output.get('gifs', []) + node_output.get('images', []) + node_output.get('audio', [])
                if files:
                    file_info = files[0]
                    # Just return the first file found
                    return "SUCCEEDED", {
                        "filename": file_info.get('filename'),
                        "subfolder": file_info.get('subfolder', ''),
                        "type": file_info.get('type', 'output')
                    }

            return "FAILED", "No output found"
            
        # If not in history, check queue
        status = client.is_task_running(prompt_id)
        if status in ["PENDING", "RUNNING"]:
            return status, None
        
        # If not in queue and not in history, double check history just in case it finished while we were checking queue
        history = client.get_history(prompt_id)
        if prompt_id in history:
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
