import socket
import requests
import time
import os

SERVER_HOST = "dimond.top"
SERVER_PORT = 7860
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

def test_tcp_connection():
    print(f"--- Testing TCP Connection to {SERVER_HOST}:{SERVER_PORT} ---")
    try:
        start = time.time()
        sock = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=5)
        end = time.time()
        sock.close()
        print(f"✅ TCP Connection successful (Latency: {(end-start)*1000:.2f}ms)")
        return True
    except Exception as e:
        print(f"❌ TCP Connection failed: {e}")
        return False

def test_http_get():
    print(f"\n--- Testing HTTP GET {BASE_URL}/object_info ---")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        print(f"Sending headers: {headers}")
        response = requests.get(f"{BASE_URL}/object_info", timeout=10, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("✅ HTTP GET successful")
            return True
        else:
            print(f"❌ HTTP GET failed with status: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
    except Exception as e:
        print(f"❌ HTTP GET Exception: {e}")
        return False

def test_http_upload():
    print(f"\n--- Testing HTTP POST Upload to {BASE_URL}/upload/image ---")
    # Create a dummy file
    filename = "test_connectivity_dummy.txt"
    with open(filename, "w") as f:
        f.write("This is a connectivity test file.")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with open(filename, 'rb') as f:
            files = {'image': (filename, f)}
            data = {'overwrite': 'true', 'subfolder': ''}
            print("Sending POST request...")
            response = requests.post(f"{BASE_URL}/upload/image", files=files, data=data, timeout=10, headers=headers)
            
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("✅ HTTP Upload successful")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ HTTP Upload failed with status: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ HTTP Upload Exception: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    print(f"Diagnosing connection to {BASE_URL}...\n")
    
    if test_tcp_connection():
        if test_http_get():
            test_http_upload()
        else:
            print("\n⚠️ Skipping upload test because GET failed.")
    else:
        print("\n⚠️ Skipping HTTP tests because TCP connection failed.")
