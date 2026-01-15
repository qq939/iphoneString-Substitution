import requests
import os

def test_download_tone():
    url = "http://obs.dimond.top/tone.wav"
    output_path = "test_tone.wav"
    
    print(f"Testing download from {url}...")
    
    try:
        # Simulate the exact logic used in app.py
        response = requests.get(url, stream=True, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Download successful. Saved to {output_path}")
            print(f"File size: {os.path.getsize(output_path)} bytes")
        else:
            print(f"Download failed with status: {response.status_code}")
            
    except Exception as e:
        print(f"Download Error: {e}")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
            print("Cleaned up test file")

if __name__ == "__main__":
    test_download_tone()
