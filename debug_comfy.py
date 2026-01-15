import requests
import os
import uuid

SERVER_ADDRESS = "dimond.top:7860"
URL = f"http://{SERVER_ADDRESS}/upload/image"

def test_connection():
    try:
        print(f"Checking connection to {SERVER_ADDRESS}...")
        resp = requests.get(f"http://{SERVER_ADDRESS}/object_info", timeout=5)
        print(f"Status: {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

def test_upload():
    filename = f"test_{uuid.uuid4()}.txt"
    with open(filename, "w") as f:
        f.write("test content")
    
    try:
        print(f"Uploading {filename} to {URL}...")
        with open(filename, 'rb') as f:
            files = {'image': (filename, f)}
            data = {'overwrite': 'false', 'subfolder': ''}
            response = requests.post(URL, files=files, data=data, timeout=10)
            
            print(f"Upload Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                print("Upload Success")
            else:
                print("Upload Failed")
    except Exception as e:
        print(f"Upload Exception: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    if test_connection():
        test_upload()
