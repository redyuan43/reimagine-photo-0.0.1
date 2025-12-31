import requests
import os

SERVER_URL = "http://localhost:8000/magic_edit"
SMART_START_URL = "http://localhost:8000/smart/start"
SMART_ANSWER_URL = "http://localhost:8000/smart/answer"
SMART_GENERATE_URL = "http://localhost:8000/smart/generate"
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
        'resolution': '1K'
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


def test_smart_flow():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Image not found at {IMAGE_PATH}")
        return

    with open(IMAGE_PATH, "rb") as f:
        files = {"image": f}
        data = {"message": "把这张照片修得更自然更高级，但不要改脸。"}
        print(f"POST {SMART_START_URL}")
        r = requests.post(SMART_START_URL, files=files, data=data, timeout=180)
    print("Status:", r.status_code)
    if r.status_code != 200:
        print(r.text)
        return
    start = r.json()
    print("Start:", start)
    sid = start["session_id"]

    while start.get("status") == "needs_input" and start.get("questions"):
        q = start["questions"][0]
        print("Question:", q["text"], "choices=", q.get("choices"))
        if q.get("choices"):
            ans = q["choices"][0]
        else:
            ans = "保真，不改脸。"
        print(f"POST {SMART_ANSWER_URL} sid={sid} ans={ans}")
        r = requests.post(SMART_ANSWER_URL, json={"session_id": sid, "message": ans}, timeout=120)
        print("Status:", r.status_code)
        if r.status_code != 200:
            print(r.text)
            return
        start = r.json()
        print("Turn:", start)

    print(f"POST {SMART_GENERATE_URL}")
    r = requests.post(SMART_GENERATE_URL, json={"session_id": sid, "resolution": "1K"}, timeout=240)
    print("Status:", r.status_code)
    if r.status_code != 200:
        print(r.text)
        return
    print("Generate:", r.json())


if __name__ == "__main__":
    test_magic_edit()
    test_smart_flow()
