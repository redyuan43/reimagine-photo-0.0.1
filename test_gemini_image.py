import requests
import base64
import json
import os

# 配置信息
API_KEY = "AIzaSyA3s7_iOSN6oo2HajDNBoD2aS6Y3c5_8vE"
MODEL = "gemini-3-pro-image-preview"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

# 测试图片路径
IMAGE_PATH = "/home/nano/reimagine-photo-0.0.1/data/images/20251229103154_59d4f54d.jpg"
PROMPT = "Restore this image to stunning quality, ultra-high detail, and exceptional clarity. Apply advanced restoration techniques to eliminate noise, artifacts, and any imperfections. Optimize lighting to appear natural, balanced, and dynamic, enhancing depth and textures without overexposed highlights or excessively dark shadows. Colors should be meticulously restored to achieve a vibrant, rich, and harmonious aesthetic, characteristic of leading design magazines. Even if the original is black and white or severely faded, intelligently recolor and enhance it to meet this benchmark standard, with deep blacks, clean whites, and rich, realistic tones. The final image should appear as though captured with a high-end camera and professionally post-processed, possessing maximum depth and realism."

def test_gemini_edit():
    if not os.path.exists(IMAGE_PATH):
        print(f"错误: 找不到图片 {IMAGE_PATH}")
        return

    # 读取并编码图片
    with open(IMAGE_PATH, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")

    # 构造请求体
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_data
                    }
                }
            ]
        }]
    }

    print(f"正在发送请求到: {ENDPOINT}")
    print(f"提示词: {PROMPT}")
    
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=90)
        print(f"状态码: {response.status_code}")
        
        result = response.json()
        
        if response.status_code == 200:
            candidates = result.get("candidates", [])
            if not candidates:
                print("警告: candidates 为空")
                if "promptFeedback" in result:
                    print(f"提示词反馈: {result['promptFeedback']}")
                return

            for i, cand in enumerate(candidates):
                content = cand.get("content", {})
                parts = content.get("parts", [])
                for j, part in enumerate(parts):
                    # 同时支持 snake_case 和 camelCase
                    img_part = part.get("inline_data") or part.get("inlineData")
                    
                    if img_part:
                        mime_type = img_part.get('mime_type') or img_part.get('mimeType') or 'image/png'
                        # 保存测试结果
                        out_data = base64.b64decode(img_part["data"])
                        # 根据 MIME 类型决定后缀
                        ext = "png"
                        if mime_type and ("jpeg" in mime_type or "jpg" in mime_type):
                            ext = "jpg"
                        
                        out_path = f"test_output_gemini_{i+1}_{j+1}.{ext}"
                        with open(out_path, "wb") as out_f:
                            out_f.write(out_data)
                        print(f"成功保存图片: {out_path} (MIME: {mime_type})")
                    elif "text" in part:
                        print(f"文本回复: {part['text']}")
        else:
            print(f"请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")

    except Exception as e:
        print(f"发生异常: {str(e)}")

if __name__ == "__main__":
    test_gemini_edit()
