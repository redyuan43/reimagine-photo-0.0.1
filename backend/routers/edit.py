from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import server as impl

router = APIRouter(dependencies=[Depends(impl.require_api_auth)])


@router.post("/magic_edit")
async def magic_edit(
    image: UploadFile = File(...),
    mask: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    n: int = Form(1),
    size: str = Form(""),
    watermark: bool = Form(False),
    negative_prompt: str = Form(""),
    prompt_extend: bool = Form(True),
    aspect_ratio: Optional[str] = Form(None),
    resolution: Optional[str] = Form(None),
    step: Optional[int] = Form(None),
):
    vision_api_key = os.getenv("VISION_API_KEY")
    image_edit_endpoint = os.getenv("IMAGE_EDIT_ENDPOINT")
    model = os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview")

    if not vision_api_key:
        if impl.MultiModalConversation is None:
            raise HTTPException(status_code=500, detail="dashscope SDK not available on server")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Neither VISION_API_KEY nor DASHSCOPE_API_KEY configured")
    else:
        api_key = vision_api_key

    payload = await image.read()
    impl.logger.info("magic_edit received bytes=%d", len(payload or b""))
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    original_local_path = impl._save_image_bytes(image.filename or "image.png", payload)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(image.filename or "image").suffix or ".png")
    tmp.write(payload)
    tmp.flush()
    tmp.close()

    try:
        try:
            img = impl._load_image_from_bytes(payload, image.filename or "image.bin")
        except Exception:
            from PIL import Image as _Image

            img = _Image.open(tmp.name)
        img = impl._resize_image_max(img, 2048)

        ext = (Path(image.filename or "").suffix or "").lower()
        raw_heic_exts = {".heic", ".heif", ".dng", ".raw", ".arw", ".cr2", ".nef", ".raf", ".orf", ".rw2"}
        if ext in [".jpg", ".jpeg"] or ext in raw_heic_exts:
            input_fmt = "jpeg"
            input_mime = "image/jpeg"
        else:
            input_fmt = "png"
            input_mime = "image/png"

        process_bin, _ = impl._pil_to_bytes(img, input_fmt, quality=90 if input_fmt == "jpeg" else None)
        img_data = base64.b64encode(process_bin).decode("utf-8")

        mask_data = None
        if mask:
            mask_bin = await mask.read()
            if mask_bin:
                try:
                    mask_img = impl._load_image_from_bytes(mask_bin, "mask.png")
                    mask_img = mask_img.resize(img.size)
                    mask_proc, _ = impl._pil_to_bytes(mask_img, "png")
                    mask_data = base64.b64encode(mask_proc).decode("utf-8")
                except Exception as e:
                    impl.logger.warning("Failed to process mask: %s", e)

        urls = []
        local_paths = []

        if vision_api_key:
            impl.logger.info("使用 Google Gemini (Native/REST) 接口进行图片编辑: %s", model)

            base_url = image_edit_endpoint.replace("/openai/", "") if image_edit_endpoint else "https://generativelanguage.googleapis.com/v1beta"
            native_url = f"{base_url.rstrip('/')}/models/{model}:generateContent?key={vision_api_key}"

            final_prompt = f"[Standard Quality Requirements]\n{impl.GEMINI_BASE_PROMPT}\n\n[User Specific Edit Instruction]\n{prompt}"
            if mask_data:
                final_prompt += "\n\nNote: A mask image is provided. The second image is the mask where white areas indicate where the edits should be applied. Please perform inpainting/editing in the white areas of the mask while keeping other parts unchanged."

            print("\n" + "=" * 50)
            print("FINAL PROMPT SENT TO GEMINI (MAGIC_EDIT):")
            print(final_prompt)
            print("=" * 50 + "\n")
            impl.logger.info("FINAL PROMPT SENT TO GEMINI (MAGIC_EDIT): \n%s", final_prompt)

            parts = [
                {"text": final_prompt},
                {"inline_data": {"mime_type": input_mime, "data": img_data}},
            ]
            if mask_data:
                parts.append({"inline_data": {"mime_type": "image/png", "data": mask_data}})

            payload_json = {
                "contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }

            if aspect_ratio or resolution:
                image_config = {}
                if aspect_ratio:
                    image_config["aspectRatio"] = aspect_ratio
                if resolution:
                    image_config["imageSize"] = resolution
                payload_json["generationConfig"]["imageConfig"] = image_config

            impl.logger.info("发送请求到 Google Native API: %s (MIME: %s, Ratio: %s, Res: %s)", native_url, input_mime, aspect_ratio, resolution)
            resp_google = impl.requests.post(native_url, json=payload_json, timeout=90)

            if resp_google.status_code == 200:
                result = resp_google.json()
                impl.logger.info("Google API 响应成功，正在解析内容...")
                try:
                    candidates = result.get("candidates", [])
                    if not candidates:
                        impl.logger.warning("Gemini 未返回任何候选结果。完整响应: %s", result)

                    for cand in candidates:
                        finish_reason = cand.get("finishReason")
                        if finish_reason and finish_reason != "STOP":
                            impl.logger.warning("Gemini 任务未正常停止，原因: %s", finish_reason)

                        parts = cand.get("content", {}).get("parts", [])
                        if not parts:
                            impl.logger.warning("Gemini 候选结果中没有 parts。候选内容: %s", cand)

                        for part in parts:
                            img_part = part.get("inline_data") or part.get("inlineData")
                            if img_part:
                                b64_out = img_part.get("data")
                                if not b64_out:
                                    continue
                                out_bytes = base64.b64decode(b64_out)

                                mime_type = img_part.get("mime_type") or img_part.get("mimeType") or "image/png"
                                ext = ".png"
                                if mime_type and ("jpeg" in mime_type or "jpg" in mime_type):
                                    ext = ".jpg"

                                step_str = f"_step{step}" if step is not None else ""
                                out_filename = f"gen{step_str}{ext}"
                                out_path = impl._save_image_bytes(out_filename, out_bytes)
                                local_paths.append(out_path)

                                base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
                                urls.append(f"{base}/static/{Path(out_path).name}")
                                impl.logger.info("成功提取并保存生成图像: %s", out_path)
                            elif "file_data" in part or "fileData" in part:
                                impl.logger.info("Gemini 返回了 file_data: %s", part.get("file_data") or part.get("fileData"))
                            elif "text" in part:
                                impl.logger.info("Gemini 返回文本消息: %s", part["text"])
                except Exception as e:
                    impl.logger.error("解析 Gemini 返回数据失败: %s. 完整响应: %s", str(e), result)

                size_used = size
            else:
                impl.logger.error("Google API 返回错误: %d %s", resp_google.status_code, resp_google.text)
                raise HTTPException(status_code=resp_google.status_code, detail=f"Google API error: {resp_google.text}")

            if not urls:
                error_msg = "Google Gemini 未能生成图像。请检查提示词是否合规或模型是否支持此操作。"
                if "result" in locals() and result.get("promptFeedback", {}).get("blockReason"):
                    error_msg = f"提示词被安全过滤拦截: {result['promptFeedback']['blockReason']}"
                elif "result" in locals() and result.get("candidates") and result["candidates"][0].get("finishReason") == "SAFETY":
                    error_msg = "响应因安全策略被拦截。"

                impl.logger.error(error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
        else:
            fmt = input_fmt
            mime = input_mime
            b64 = img_data
            data_url = f"data:{mime};base64,{b64}"
            contents: list[dict] = [{"image": data_url}]
            impl.logger.info("magic_edit prompt len=%d", len(prompt or ""))
            print("magic_edit 提示词:", prompt)
            if prompt:
                contents.append({"text": prompt})
            messages = [{"role": "user", "content": contents}]

            model = os.getenv("IMAGE_EDIT_MODEL", "qwen-image-edit-plus")
            kwargs = dict(
                api_key=api_key,
                model=model,
                messages=messages,
                stream=False,
                n=n,
                watermark=watermark,
                negative_prompt=negative_prompt or " ",
                prompt_extend=prompt_extend,
            )
            size_used = impl._normalize_size_param(size, n)
            if size_used:
                kwargs["size"] = size_used

            resp = impl.MultiModalConversation.call(**kwargs)
            if getattr(resp, "status_code", None) == 200:
                try:
                    for c in resp.output.choices[0].message.content:
                        if isinstance(c, dict) and c.get("image"):
                            urls.append(c["image"])
                except Exception:
                    pass
            else:
                impl.logger.error(
                    "magic_edit 非200 status=%s code=%s message=%s",
                    getattr(resp, "status_code", None),
                    getattr(resp, "code", None),
                    getattr(resp, "message", None),
                )
                raise HTTPException(status_code=getattr(resp, "status_code", 500), detail=getattr(resp, "message", "image edit failed"))

        if urls:
            try:
                if not vision_api_key:
                    for u in urls:
                        p = impl._download_and_save_image(u)
                        if p:
                            local_paths.append(p)

                params = {
                    "model": model,
                    "n": n,
                    "size": size_used or size,
                    "watermark": watermark,
                    "negative_prompt": negative_prompt,
                    "prompt_extend": prompt_extend,
                    "endpoint": image_edit_endpoint or os.getenv("IMAGE_EDIT_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1"),
                }
                steps = [{"text": prompt}] if prompt else []
                events = [
                    {"level": "INFO", "message": "magic_edit 完成", "outputs": len(urls)},
                    {"level": "DEBUG", "message": "请求参数", "value": params},
                ]
                log_path = impl._write_json_log(
                    "magic_edit",
                    original_local_path,
                    urls,
                    params,
                    steps,
                    prompt,
                    events,
                    local_output_paths=local_paths,
                )
                rec = impl._insert_record(
                    prompt=prompt or "",
                    thinking=None,
                    image_path=original_local_path,
                    logs=log_path,
                    original_name=image.filename,
                    raw_response=impl._safe_json_dump({"urls": urls}),
                )
                try:
                    impl._insert_record_image(record_id=rec.id, kind="input", image_path=original_local_path)
                except Exception:
                    pass
                try:
                    if local_paths:
                        if len(local_paths) == 1:
                            impl._insert_record_image(record_id=rec.id, kind="final", image_path=local_paths[0])
                        else:
                            for p in local_paths[:-1]:
                                impl._insert_record_image(record_id=rec.id, kind="intermediate", image_path=p)
                            impl._insert_record_image(record_id=rec.id, kind="final", image_path=local_paths[-1])
                except Exception as exc:
                    impl.logger.warning("保存输出图片记录失败: %s", exc)
            except Exception as exc:
                impl.logger.warning("magic_edit 写日志失败: %s", exc)
            try:
                served_urls: list[str] = []
                if local_paths:
                    base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
                    served_urls = [f"{base}/static/{Path(p).name}" for p in local_paths]
                else:
                    served_urls = urls
                return {"urls": served_urls}
            except Exception:
                return {"urls": urls}

        raise HTTPException(status_code=502, detail="Model returned no image URLs")

    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
