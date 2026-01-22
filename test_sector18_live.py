import requests

BASE_URL = "http://127.0.0.1:5015"

def test_sector18():
    print("Fetching Sector 18 prompt...")
    try:
        response = requests.get(f"{BASE_URL}/sector18_get_prompt")
        response.raise_for_status()
        data = response.json()
        
        if data['status'] == 'success':
            print("Sector 18 Fetch SUCCESS")
            print("Content preview:", data['content'][:100] + "..." if len(data['content']) > 100 else data['content'])
        else:
            print("Sector 18 Fetch FAILED:", data)
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_sector18()
