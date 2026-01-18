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
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging (used throughout comfy_utils for diagnostics)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Server list for dual-try mechanism (used in: ComfyUIClient.find_fastest_server, check_status fallbacks)
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
                response = requests.get(url, timeout=30, headers=headers)
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
        return self.check_connection(timeout=10)

    def get_object_info(self, node_class=None):
        """
        Gets object info (node definitions) from the server.
        If node_class is provided, returns info only for that class.
        """
        try:
            url = f"{self.base_url}/object_info"
            if node_class:
                url = f"{url}/{node_class}"
            
            with urllib.request.urlopen(url, timeout=60) as response:
                data = json.loads(response.read())
                return data
        except Exception as e:
            logger.error(f"Get object info failed: {e}")
            return None

    def queue_prompt(self, prompt):
        """
        Sends the workflow to the server.
        """
        try:
            p = {"prompt": prompt, "client_id": self.client_id}
            data = json.dumps(p).encode('utf-8')
            
            url = f"{self.base_url}/prompt"
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=60) as response:
                response_data = json.loads(response.read())
                if 'prompt_id' in response_data:
                    return response_data['prompt_id'], self.server_address
        except Exception as e:
            error_msg = str(e)
            error_body = ""
            if hasattr(e, 'read'):
                try:
                    error_body = e.read().decode('utf-8')
                    logger.warning(f"Failed to queue prompt. Response: {error_body}")
                    
                    # Try to parse error to give helpful hints
                    try:
                        err_json = json.loads(error_body)
                        node_errors = err_json.get('node_errors', {})
                        for node_id, errors in node_errors.items():
                            class_type = errors.get('class_type')
                            for err in errors.get('errors', []):
                                if err.get('type') == 'value_not_in_list' and class_type == 'UNETLoader':
                                    logger.info("Attempting to fetch available UNET models...")
                                    info = self.get_object_info('UNETLoader')
                                    if info:
                                        # structure: {'UNETLoader': {'input': {'required': {'unet_name': [['model1', 'model2'], ...]}}}}
                                        models = info.get('UNETLoader', {}).get('input', {}).get('required', {}).get('unet_name', [[]])[0]
                                        logger.info(f"Available UNET models on server ({len(models)}): {models}")
                    except:
                        pass
                        
                except:
                    pass
            logger.warning(f"Failed to queue prompt: {e}")
            raise # Propagate exception to caller
            
        return None, None

    def get_history(self, prompt_id, server_address=None):
        """
        Queries history for the given prompt_id.
        """
        try:
            base_url = f"http://{server_address}" if server_address else self.base_url
            url = f"{base_url}/history/{prompt_id}"
            logger.info(f"Fetching ComfyUI history: {url}")
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                return data
        except Exception as e:
            logger.warning(f"Failed to get history for {prompt_id} from {server_address or self.base_url}: {e}")
            pass
        return None

    def upload_file(self, file_path, subfolder="", overwrite=True):
        """
        Uploads a file to ComfyUI.
        """
        try:
            url = f"{self.base_url}/upload/image"
            with open(file_path, 'rb') as f:
                files = {'image': f}
                data = {'overwrite': str(overwrite).lower(), 'subfolder': subfolder}
                response = requests.post(url, files=files, data=data, timeout=60)
                
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Upload exception: {e}")
            return None
    
    def download_output_file(self, filename, subfolder="", file_type="output", output_dir=".", server_address=None):
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
            base_url = f"http://{server_address}" if server_address else self.base_url
            url = f"{base_url}/view?{query_string}"
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            local_path = os.path.join(output_dir, filename)
            logger.info(f"Downloading {url} to {local_path}...")
            
            urllib.request.urlretrieve(url, local_path)
            return local_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise # Propagate exception
        
    def get_queue(self, server_address=None):
        """
        Gets the current queue status.
        """
        try:
            base_url = f"http://{server_address}" if server_address else self.base_url
            url = f"{base_url}/queue"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                return data
        except Exception as e:
            logger.error(f"Get queue failed from {server_address or self.base_url}: {e}")
            return None
            
    def is_task_running(self, prompt_id, server_address=None):
        """
        Checks if a task is currently running or pending.
        """
        queue_data = self.get_queue(server_address)
        
        if queue_data is None:
            return "UNKNOWN"
            
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
        return None, None, str(e)
    finally:
        shutil.rmtree(temp_dir)

def submit_job(character_path, video_path):
    try:
        char_res = client.upload_file(character_path)
        video_res = client.upload_file(video_path)
        
        if not char_res or not video_res:
            return None, None, "Failed to upload files"
            
        return queue_workflow_template(char_res.get('name'), video_res.get('name'))
    except Exception as e:
        logger.error(f"Submit job error: {e}")
        return None, None, str(e)

def cancel_job(prompt_id):
    return client.cancel_task(prompt_id)

def adjust_segment_length(workflow, segment_duration):
    try:
        if "49" in workflow and workflow.get("49", {}).get("class_type") == "WanVaceToVideo":
            fps = 16
            node_id_video = "68"
            if (
                node_id_video in workflow
                and "inputs" in workflow[node_id_video]
                and "fps" in workflow[node_id_video]["inputs"]
            ):
                fps = workflow[node_id_video]["inputs"]["fps"]
            target = int(math.ceil(segment_duration * fps))
            if target < 4:
                target = 4
            if "49" in workflow and "inputs" in workflow["49"]:
                workflow["49"]["inputs"]["length"] = target
        else:
            fps = 16
            node_id_video = "232:15"
            if (
                node_id_video in workflow
                and "inputs" in workflow[node_id_video]
                and "fps" in workflow[node_id_video]["inputs"]
            ):
                fps = workflow[node_id_video]["inputs"]["fps"]
            target = int(math.ceil(segment_duration * fps))
            base_a = workflow.get("232:62", {}).get("inputs", {}).get("length")
            base_b = workflow.get("242:90", {}).get("inputs", {}).get("length")
            max_allowed = None
            for v in (base_a, base_b):
                if isinstance(v, int):
                    max_allowed = v if max_allowed is None else min(max_allowed, v)
            min_allowed = 4
            if max_allowed is not None:
                target = min(target, max_allowed)
            if target < min_allowed:
                target = min_allowed
            for node_id in ["232:62", "242:90"]:
                if node_id in workflow and "inputs" in workflow[node_id]:
                    workflow[node_id]["inputs"]["length"] = target
    except Exception as e:
        logger.warning(f"Failed to adjust segment length: {e}")
    return workflow

def queue_workflow_template(char_filename, video_filename, prompt_text=None, workflow_type='real', segment_duration=None):
    try:
        if workflow_type == 'anime':
            workflow_path = os.path.join(
                os.path.dirname(__file__),
                'comfyapi',
                '视频换人2video_wan_vace_14B_v2v.json',
            )
        else:
            workflow_path = os.path.join(
                os.path.dirname(__file__),
                'comfyapi',
                '视频换人video_wan2_2_14B_animate.json',
            )
            
        if not os.path.exists(workflow_path):
            return None, None, f"Workflow file not found: {workflow_path}"
            
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
            
        # Update inputs
        for node_id in ("10", "134"):
            if node_id in workflow and "inputs" in workflow[node_id] and "image" in workflow[node_id]["inputs"]:
                workflow[node_id]["inputs"]["image"] = char_filename
        if "145" in workflow and "inputs" in workflow["145"] and "file" in workflow["145"]["inputs"]:
            workflow["145"]["inputs"]["file"] = video_filename
        if prompt_text and "21" in workflow: workflow["21"]["inputs"]["text"] = prompt_text
        if segment_duration is not None:
            workflow = adjust_segment_length(workflow, segment_duration)
        if workflow_type != 'real':
            seed = random.randint(1, 1000000000000000)
            for node_id in ["232:63", "242:91", "64"]:
                if node_id in workflow and "inputs" in workflow[node_id] and "seed" in workflow[node_id]["inputs"]:
                    workflow[node_id]["inputs"]["seed"] = seed
            
        prompt_id, server_address = client.queue_prompt(workflow)
        return (prompt_id, server_address, None) if prompt_id else (None, None, "Failed to queue prompt")
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, 'read'):
            try:
                error_body = e.read().decode('utf-8')
                error_msg += f" Response: {error_body}"
            except:
                pass
        logger.error(f"Queue workflow template error: {error_msg}")
        return None, None, error_msg

def check_status(prompt_id, server_address=None):
    # If specific server is known, prioritize it. Otherwise check all.
    servers_to_check = [server_address] if server_address else SERVER_LIST
    
    any_network_error = False
    
    for server in servers_to_check:
        try:
            # 1. Check history
            history = client.get_history(prompt_id, server)
            if history is None:
                any_network_error = True
                # Continue to next server or try is_task_running if single server?
                # If single server and network error, we can't do much.
                # If checking multiple, maybe it's on another server.
                # Let's try is_task_running on this server just in case history endpoint is the only one broken (unlikely)
                # But proceed to check queue.
            
            elif prompt_id in history:
                # Found!
                data = history[prompt_id]
                outputs = data.get('outputs', {})

                # 只记录关键信息，避免输出整个 history JSON
                summary_items = []
                for node_id, node_output in outputs.items():
                    for type_key in ['gifs', 'videos', 'images', 'audio']:
                        if type_key in node_output:
                            count = len(node_output[type_key])
                            summary_items.append(f"{node_id}:{type_key}={count}")

                summary_str = ", ".join(summary_items) if summary_items else "no outputs"
                logger.info(
                    f"Task {prompt_id} completed on {server}. Output summary: {summary_str}"
                )
                
                # Collect all outputs to find the best one
                all_files = []
                for node_id, node_output in outputs.items():
                    for type_key in ['gifs', 'videos', 'images', 'audio']:
                        if type_key in node_output:
                            for file_info in node_output[type_key]:
                                all_files.append({
                                    'node_id': node_id,
                                    'type_key': type_key,
                                    'file_info': file_info
                                })
                
                if all_files:
                    # Sort outputs to prioritize video > image > audio
                    def sort_key(item):
                        type_priority = {'videos': 0, 'gifs': 1, 'images': 2, 'audio': 3}
                        node_priority = 0 if item['node_id'] == '15' else 1
                        return (node_priority, type_priority.get(item['type_key'], 99))
                    
                    all_files.sort(key=sort_key)
                    best_file = all_files[0]
                    file_info = best_file['file_info']
                    
                    logger.info(f"Selected output: Node {best_file['node_id']} ({best_file['type_key']}) - {file_info.get('filename')}")
                    
                    return "SUCCEEDED", {
                        "filename": file_info.get('filename'),
                        "subfolder": file_info.get('subfolder', ''),
                        "type": file_info.get('type', 'output')
                    }
                
                return "FAILED", "No output found"
                
            # 2. Check queue
            status = client.is_task_running(prompt_id, server)
            if status == "UNKNOWN":
                any_network_error = True
            elif status in ["PENDING", "RUNNING"]:
                logger.info(f"Task {prompt_id} is {status} on {server}")
                return status, None
            
            # Double check history if queue said NOT_FOUND (and history was checked before)
            # But we already checked history.
            # Race condition: Finished between history check and queue check?
            if history is not None and status == "NOT_FOUND":
                 # Check history again
                 history_retry = client.get_history(prompt_id, server)
                 if history_retry is not None and prompt_id in history_retry:
                      return check_status(prompt_id, server) # Recursion to handle output parsing
                 elif history_retry is None:
                      any_network_error = True

        except Exception as e:
            logger.error(f"Check status error for {prompt_id} on {server}: {e}")
            any_network_error = True

    # If we are here, task was not found in any reachable server.
    if any_network_error:
        logger.warning(f"Network error while checking status for {prompt_id}. Keeping as PENDING.")
        return "PENDING", None 
        
    return "FAILED", "Task not found"

def download_result(file_info, output_dir, server_address=None):
    return client.download_output_file(
        file_info['filename'],
        file_info['subfolder'],
        file_info['type'],
        output_dir,
        server_address
    )


def _load_switch_prompt():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_path = base_dir
        txt_path = os.path.join(root_path, "swichPicture.txt")
        if not os.path.exists(txt_path):
            txt_path = os.path.join(base_dir, "comfyapi", "swichPicture.txt")
            if not os.path.exists(txt_path):
                return None
        with open(txt_path, "r", encoding="utf-8") as f:
            candidates = []
            for line in f:
                text = line.strip()
                if text and len(text) > 4:
                    candidates.append(text)
        if not candidates:
            return None
        return random.choice(candidates)
    except Exception as e:
        logger.warning(f"Failed to load switch prompt: {e}")
        return None


def queue_transition_workflow(start_image_filename, end_image_filename, width=640, height=640, fps=16, prompt_text=None):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        workflow_path = os.path.join(base_dir, "comfyapi", "收尾帧wan2.1_flf2v_720_f16.json")
        if not os.path.exists(workflow_path):
            return None, None, f"Workflow file not found: {workflow_path}"
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        if "52" in workflow and "inputs" in workflow["52"] and "image" in workflow["52"]["inputs"]:
            workflow["52"]["inputs"]["image"] = start_image_filename
        if "72" in workflow and "inputs" in workflow["72"] and "image" in workflow["72"]["inputs"]:
            workflow["72"]["inputs"]["image"] = end_image_filename
        if "83" in workflow and "inputs" in workflow["83"]:
            node_inputs = workflow["83"]["inputs"]
            node_inputs["width"] = int(width)
            node_inputs["height"] = int(height)
            if "length" in node_inputs:
                node_inputs["length"] = 16
        for node in workflow.values():
            if isinstance(node, dict):
                inputs = node.get("inputs")
                if isinstance(inputs, dict) and "fps" in inputs:
                    inputs["fps"] = int(fps)
        if prompt_text is None:
            prompt_text = _load_switch_prompt()
        if prompt_text and "6" in workflow and "inputs" in workflow["6"]:
            workflow["6"]["inputs"]["text"] = prompt_text
        prompt_id, server_address = client.queue_prompt(workflow)
        if prompt_id:
            return prompt_id, server_address, None
        return None, None, "Failed to queue transition workflow"
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, "read"):
            try:
                error_body = e.read().decode("utf-8")
                error_msg += f" Response: {error_body}"
            except Exception:
                pass
        logger.error(f"Queue transition workflow error: {error_msg}")
        return None, None, error_msg
