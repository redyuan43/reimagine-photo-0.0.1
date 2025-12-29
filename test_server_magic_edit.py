import requests
import os

SERVER_URL = "http://localhost:8000/magic_edit"
IMAGE_PATH = "/home/nano/reimagine-photo-0.0.1/data/images/20251229103154_59d4f54d.jpg"
PROMPT = "Make it look more professional"

def test_magic_edit():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Image not found at {IMAGE_PATH}")
        return

    files = {
        'image': open(IMAGE_PATH, 'rb')
    }
    data = {
        'prompt': PROMPT,
        'aspect_ratio': '1:1',
        'resolution': '1024x1024'
    }

    print(f"Sending request to {SERVER_URL}...")
    try:
        response = requests.post(SERVER_URL, files=files, data=data, timeout=120)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("Response JSON:")
            import json
            print(json.dumps(result, indent=2))
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_magic_edit()
