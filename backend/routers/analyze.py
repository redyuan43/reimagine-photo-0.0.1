from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import tempfile
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

import server as impl

router = APIRouter(dependencies=[Depends(impl.require_api_auth)])


@router.post("/analyze")
async def analyze(image: UploadFile = File(...), prompt: str = Form("")):
    print("收到分析请求")
    buf = await image.read()
    print(f"接收字节: {len(buf)}")
    impl.logger.info("Analyze request received bytes=%d prompt_len=%d", len(buf), len(prompt or ""))
    saved_image_path = impl._save_image_bytes(image.filename or "image.png", buf)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(buf)
    tmp.flush()
    tmp.close()

    result = impl.analyze_image_with_qwen3_vl_plus(tmp.name, user_prompt=prompt, stream_output=True, enable_thinking=True)
    thinking_text = impl._extract_thinking(result if isinstance(result, dict) else None)
    raw_json = impl._safe_json_dump(result) if isinstance(result, (dict, list)) else None
    ui = result.get("ui_analysis") if isinstance(result, dict) else None
    items = impl._parse_ui_to_plan_items(ui or {})
    summary = None
    if isinstance(result, dict):
        if "summary_ui" in result:
            summary = result.get("summary_ui")
        elif "summary" in result:
            summary = result.get("summary")
        elif ui and isinstance(ui, dict):
            summary = ui.get("summary_ui")
    print(f"返回项数: {len(items)}")
    print(f"返回总结长度: {len(summary or '')}")
    impl.logger.info("Analyze response items=%d summary_len=%d", len(items), len(summary or ""))
    try:
        rec = impl._insert_record(
            prompt=prompt or "",
            thinking=thinking_text,
            image_path=saved_image_path,
            logs=raw_json,
            original_name=image.filename,
            raw_response=raw_json,
        )
        try:
            impl._insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
        except Exception:
            pass
    except Exception as exc:
        impl.logger.warning("Failed to persist analyze record: %s", exc)
    return {"analysis": items, "summary": impl.sanitize_summary_ui(summary or "")}


@router.post("/analyze_stream")
async def analyze_stream(image: UploadFile = File(...), prompt: str = Form("")):
    payload = await image.read()
    impl.logger.info("SSE 收到分析请求 bytes=%d", len(payload))

    saved_image_path = impl._save_image_bytes(image.filename or "image.png", payload)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(payload)
    tmp.flush()
    tmp.close()
    impl.logger.info("SSE 临时文件=%s", tmp.name)

    base_url = os.getenv("DASHSCOPE_COMPAT_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    impl.logger.info("SSE 配置 模型=qwen3-vl-plus接口=%s", base_url)

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        buffer = ""
        sent = 0
        sent_ids: set = set()

        def push(evt: dict):
            try:
                asyncio.run_coroutine_threadsafe(queue.put(evt), loop)
            except Exception as exc:
                impl.logger.warning("SSE push 失败: %s", exc)

        def worker():
            fallback_result = None
            try:
                from openai import OpenAI

                client = OpenAI(api_key=api_key, base_url=base_url)
                with open(tmp.name, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{b64}"
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": impl.get_enhanced_prompt(prompt)},
                        ],
                    }
                ]
                resp = client.chat.completions.create(
                    model="qwen3-vl-plus",
                    messages=messages,
                    stream=True,
                    temperature=0.1,
                    top_p=0.1,
                    extra_body={"enable_thinking": False, "thinking_budget": 81920},
                )
                impl.logger.info("SSE 连接建立，开始流式分析")
                for chunk in resp:
                    try:
                        delta = chunk.choices[0].delta
                        if delta and getattr(delta, "content", None):
                            c = delta.content
                            if c:
                                if os.getenv("SSE_LOG_CHUNK", "0") == "1":
                                    impl.logger.info("SSE chunk 长度=%d", len(c))
                                if os.getenv("SSE_LOG_TEXT", "0") == "1":
                                    impl.logger.info("%s", c)
                            nonlocal buffer, sent
                            buffer += c
                            new_items = impl._extract_professional_items(buffer, sent)
                            for it in new_items:
                                impl.logger.info("SSE 提取项 序号=%d 类别=%s 类型=%s", sent + 1, it.get("category"), it.get("type"))
                                sent += 1
                                ui = {"professional_analysis": [it]}
                                plans = impl._parse_ui_to_plan_items(ui)
                                for p in plans:
                                    pid = p.get("id")
                                    if pid and pid in sent_ids:
                                        continue
                                    if pid:
                                        sent_ids.add(pid)
                                    push({"type": "item", "item": p})
                    except Exception:
                        continue
            except Exception as e:
                impl.logger.warning("SSE 流式调用失败: %s", e)
                try:
                    fallback_result = impl.analyze_image_with_qwen3_vl_plus(
                        tmp.name, user_prompt=prompt, stream_output=False, enable_thinking=True
                    )
                    impl.logger.info("SSE 回退分析完成")
                except Exception as e2:
                    impl.logger.warning("SSE 回退调用失败: %s", e2)
            try:
                cleaned = buffer.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                data = json.loads(cleaned) if cleaned else {}
                if not isinstance(data, dict) or (isinstance(data, dict) and not data):
                    if isinstance(fallback_result, dict):
                        data = fallback_result
                ui = data.get("ui_analysis") if isinstance(data, dict) else None
                if isinstance(ui, dict):
                    final_plans = impl._parse_ui_to_plan_items(ui)
                    for p in final_plans:
                        pid = p.get("id")
                        if pid and pid in sent_ids:
                            continue
                        if pid:
                            sent_ids.add(pid)
                        push({"type": "item", "item": p})
                summary = ""
                if isinstance(data, dict):
                    summary = data.get("summary_ui") or data.get("summary") or ""
                if not summary and isinstance(ui, dict):
                    summary = ui.get("summary_ui") or ""
                if not summary and isinstance(fallback_result, dict):
                    fu = fallback_result.get("ui_analysis") if isinstance(fallback_result, dict) else None
                    summary = fallback_result.get("summary_ui") or fallback_result.get("summary") or ((fu or {}).get("summary_ui") or "")
                summary = impl.sanitize_summary_ui(summary or "")
                impl.logger.info("SSE 最终总结长度=%d", len(summary or ""))

                record_id = None
                try:
                    thinking_text = impl._extract_thinking(data if isinstance(data, dict) else None)
                    raw_json = impl._safe_json_dump(data) if isinstance(data, (dict, list)) else None
                    rec = impl._insert_record(
                        prompt=prompt or "",
                        thinking=thinking_text,
                        image_path=saved_image_path,
                        logs=raw_json,
                        original_name=image.filename,
                        raw_response=raw_json,
                    )
                    record_id = rec.id
                    try:
                        impl._insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
                    except Exception:
                        pass
                    impl.logger.info("SSE 已保存分析记录 record_id=%d", record_id)
                except Exception as exc:
                    impl.logger.warning("SSE 保存记录失败: %s", exc)

                try:
                    params = {
                        "model": "qwen3-vl-plus",
                        "base_url": os.getenv("DASHSCOPE_COMPAT_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                        "stream": True,
                    }
                    steps = final_plans if isinstance(ui, dict) else []
                    events = [
                        {"level": "INFO", "message": "SSE 分析完成"},
                        {"level": "DEBUG", "message": "已发送条目总数", "value": len(sent_ids)},
                    ]
                    impl._write_json_log(
                        "analyze_stream",
                        tmp.name,
                        [],
                        params,
                        steps,
                        summary,
                        events,
                        local_output_paths=[],
                        record_id=record_id,
                    )
                except Exception as exc:
                    impl.logger.warning("SSE 写日志失败: %s", exc)
                push({"type": "final", "summary": summary})
            except Exception as e:
                impl.logger.warning("SSE 最终解析失败: %s", e)
                push({"type": "final", "summary": ""})
            finally:
                push({"type": "__end__"})

        threading.Thread(target=worker, daemon=True).start()

        while True:
            evt = await queue.get()
            if isinstance(evt, dict) and evt.get("type") == "__end__":
                break
            yield impl._sse_event(evt)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
