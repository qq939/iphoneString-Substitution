import time
import json
import uuid
import urllib.request
import urllib.error

# Configuration
SERVER_ADDRESS = "192.168.0.210:7860"
CLIENT_ID = str(uuid.uuid4())

def queue_prompt(workflow):
    p = {"prompt": workflow, "client_id": CLIENT_ID}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{SERVER_ADDRESS}/prompt", data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
        return None

def get_history(prompt_id):
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        return json.loads(response.read())

def main():
    # Load workflow
    with open('comfyapi/audio_workflow.json', 'r') as f:
        workflow = json.load(f)
    
    # Modify for test
    # Ensure tone.wav exists on server or we might need to upload one. 
    # For this test we assume "tone.wav" (or whatever is in the JSON) works or we just test the prompt structure.
    # The JSON has "tone.wav". If it's missing on server, it might fail execution but queueing should succeed.
    
    # Set text
    workflow["27"]["inputs"]["text"] = "This is a test audio generation with 100 words to verify the ComfyUI response structure and ensure we can correctly retrieve the output filename and path."
    workflow["27"]["inputs"]["seed"] = 12345 # Fixed seed for test
    
    print("Queueing prompt...")
    response = queue_prompt(workflow)
    
    if response:
        prompt_id = response['prompt_id']
        print(f"Prompt ID: {prompt_id}")
        
        print("Waiting for completion...")
        while True:
            history = get_history(prompt_id)
            if prompt_id in history:
                print("Task completed!")
                
                # Save full history to file
                output_file = 'tmp/comfy_response_full.json'
                with open(output_file, 'w') as f:
                    json.dump(history, f, indent=2)
                print(f"Full response saved to {output_file}")
                
                # Print outputs
                outputs = history[prompt_id]['outputs']
                print("Outputs:", json.dumps(outputs, indent=2))
                break
            else:
                print(".", end="", flush=True)
                time.sleep(1)
    else:
        print("Failed to queue prompt")

if __name__ == "__main__":
    main()
