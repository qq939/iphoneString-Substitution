import logging
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging (used in: upload_file for OBS operations)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OBS_BASE_URL = "http://obs.dimond.top"  # Used in: upload_file target URL construction

def upload_file(file_path, file_name, mime_type=None):
    """
    Upload file to OBS URL using requests.put (equivalent to curl --upload-file).
    """
    target_url = f"{OBS_BASE_URL}/{file_name}"
    try:
        print(f"DEBUG: Uploading {file_path} to {target_url}...", flush=True)
        logger.info(f"Starting upload: {file_path} -> {target_url}")
        
        if not os.path.exists(file_path):
            msg = f"File not found: {file_path}"
            print(f"DEBUG: {msg}", flush=True)
            logger.error(msg)
            return None

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=1,  # Wait 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
            allowed_methods=["PUT"]  # Retry on PUT requests
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Use requests.put to upload file content
        with open(file_path, 'rb') as f:
            headers = {}
            if mime_type:
                headers['Content-Type'] = mime_type
                
            # verify=False is equivalent to -k in curl
            # Set timeout to (connect_timeout, read_timeout)
            response = session.put(target_url, data=f, headers=headers, verify=False, timeout=(10, 300))
            
        if response.status_code in [200, 201]:
            print(f"DEBUG: Upload successful: {target_url}", flush=True)
            logger.info(f"Upload successful: {target_url}")
            return target_url
        else:
            print(f"DEBUG: Upload failed with status code {response.status_code}", flush=True)
            print(f"DEBUG: Response text: {response.text}", flush=True)
            logger.error(f"Upload failed. Code: {response.status_code}, Text: {response.text}")
            return None
            
    except Exception as e:
        print(f"DEBUG: Upload error: {e}", flush=True)
        logger.error(f"Upload exception: {e}")
        return None
