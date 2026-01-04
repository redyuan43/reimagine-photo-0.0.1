from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

import server as impl

router = APIRouter(dependencies=[Depends(impl.require_api_auth)])


@router.post("/smart/start", response_model=impl.SmartSessionStartResponse)
async def smart_start(image: UploadFile = File(...), message: str = Form("")):
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    saved_image_path = impl._save_image_bytes(image.filename or "image.png", payload)

    record_id: Optional[int] = None
    try:
        rec = impl._insert_record(
            prompt=(message or "").strip(),
            thinking=None,
            image_path=saved_image_path,
            logs=None,
            original_name=image.filename,
            raw_response=None,
        )
        record_id = rec.id
        try:
            impl._insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
        except Exception:
            pass
    except Exception as exc:
        impl.logger.warning("smart_start create record failed: %s", exc)

    facts = impl._analyze_image_facts_best_effort(saved_image_path, user_prompt=message or "")
    spec = impl._default_spec(facts, message or "")

    selected, candidates = impl._route_templates(spec, facts)
    messages = []
    if isinstance(message, str) and message.strip():
        messages.append({"role": "user", "content": message.strip()})

    patch = {}
    questions = []
    llm_selected = None
    if impl._get_gemini_api_key():
        try:
            patch, questions, llm_selected = impl._llm_clarify_next(spec, facts, messages, candidates)
        except Exception as exc:
            impl.logger.warning("smart_start llm_clarify failed: %s", exc)

    spec = impl._deep_merge(spec, patch or {})
    selected, candidates = impl._route_templates(spec, facts)
    if llm_selected and any(c.get("template") == llm_selected for c in candidates if isinstance(c, dict)):
        selected = llm_selected

    if not questions:
        if selected == "text_design" and not ((spec.get("text_overlay") or {}).get("content") or ""):
            questions = [{"id": "q_text", "text": "需要渲染的文字内容是什么？请逐字给出。", "choices": None}]
        if selected == "sticker_icon" and not ((spec.get("output") or {}).get("background") or ""):
            questions = [{"id": "q_bg", "text": "贴纸背景要透明还是白色？", "choices": ["transparent", "white"]}]
        if selected == "negative_space" and not ((spec.get("output") or {}).get("negative_space") or ""):
            questions = [
                {
                    "id": "q_space",
                    "text": "需要留白的位置是哪里？例如：top-left / top-right / bottom-left / bottom-right / center。",
                    "choices": ["top-left", "top-right", "bottom-left", "bottom-right", "center"],
                }
            ]
        face_count = facts.get("face_count")
        if isinstance(face_count, int) and face_count > 0 and (spec.get("must_keep") or {}).get("identity") is None:
            questions = (questions or [])[:1] + [{"id": "q_id", "text": "人物面部/身份是否必须完全不变？", "choices": ["必须不变", "允许略微调整"]}]

    status = "ready" if (not questions and impl._is_ready_to_render(spec, selected)) else "needs_input"

    session_id = impl._insert_smart_session(saved_image_path, image.filename, spec, facts, status=status, record_id=record_id)
    try:
        if isinstance(message, str) and message.strip():
            impl._add_smart_session_message(session_id, "user", message.strip())
    except Exception:
        pass
    impl._update_smart_session(session_id, template_selected=selected, template_candidates=candidates, status=status)

    prompt_preview = None
    if status == "ready":
        try:
            prompt_preview, _ = impl._compile_prompt(spec, facts, selected)
        except Exception:
            prompt_preview = None

    log_path = impl._write_json_log(
        "smart_start",
        saved_image_path,
        [],
        params={
            "session_id": session_id,
            "template_selected": selected,
            "template_candidates": candidates,
            "spec": spec,
            "facts": facts,
            "questions": questions,
            "llm_model": os.getenv("SMART_LLM_MODEL", "gemini-2.5-flash"),
        },
        steps=[],
        summary="",
        events=[{"level": "INFO", "message": "smart_start created", "value": {"status": status}}],
        local_output_paths=[],
        record_id=record_id,
    )
    if record_id:
        try:
            impl._update_record_logs(record_id, log_path)
        except Exception:
            pass

    return impl.SmartSessionStartResponse(
        session_id=session_id,
        record_id=record_id,
        status=status,
        spec=spec,
        facts=facts,
        questions=[impl.SmartQuestionModel(**q) for q in questions],
        template_selected=selected,
        template_candidates=candidates,
        prompt_preview=prompt_preview,
        image_model=os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview"),
        plan_items=impl._spec_to_plan_items(spec, facts),
        summary=facts.get("analysis_summary") if isinstance(facts, dict) else None,
    )


@router.post("/smart/start_stream")
async def smart_start_stream(image: UploadFile = File(...), message: str = Form("")):
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    saved_image_path = impl._save_image_bytes(image.filename or "image.png", payload)

    record_id: Optional[int] = None
    try:
        rec = impl._insert_record(
            prompt=(message or "").strip(),
            thinking=None,
            image_path=saved_image_path,
            logs=None,
            original_name=image.filename,
            raw_response=None,
        )
        record_id = rec.id
        try:
            impl._insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
        except Exception:
            pass
    except Exception as exc:
        impl.logger.warning("smart_start_stream create record failed: %s", exc)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(payload)
    tmp.flush()
    tmp.close()

    base_url = os.getenv("DASHSCOPE_COMPAT_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = os.getenv("DASHSCOPE_API_KEY")

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
                impl.logger.warning("smart_start_stream push 失败: %s", exc)

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
                            {"type": "text", "text": impl.get_enhanced_prompt(message or "")},
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
                impl.logger.info("smart_start_stream 连接建立，开始流式分析")
                for chunk in resp:
                    try:
                        delta = chunk.choices[0].delta
                        if delta and getattr(delta, "content", None):
                            c = delta.content
                            if c:
                                if os.getenv("SSE_LOG_CHUNK", "0") == "1":
                                    impl.logger.info("smart_start_stream chunk 长度=%d", len(c))
                                if os.getenv("SSE_LOG_TEXT", "0") == "1":
                                    impl.logger.info("%s", c)
                            nonlocal buffer, sent
                            buffer += c
                            new_items = impl._extract_professional_items(buffer, sent)
                            for it in new_items:
                                impl.logger.info("smart_start_stream 提取项 序号=%d 类别=%s 类型=%s", sent + 1, it.get("category"), it.get("type"))
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
                impl.logger.warning("smart_start_stream 流式调用失败: %s", e)
                try:
                    fallback_result = impl.analyze_image_with_qwen3_vl_plus(
                        tmp.name, user_prompt=message or "", stream_output=False, enable_thinking=True
                    )
                    impl.logger.info("smart_start_stream 回退分析完成")
                except Exception as e2:
                    impl.logger.warning("smart_start_stream 回退调用失败: %s", e2)

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
                final_plans = []
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
                push({"type": "final", "summary": summary})

                facts: dict = {}
                try:
                    from PIL import Image as _Image

                    img = _Image.open(saved_image_path)
                    w, h = img.size
                    facts.update(
                        {
                            "width": int(w),
                            "height": int(h),
                            "orientation": "landscape" if w >= h else "portrait",
                            "aspect_ratio": impl._best_aspect_ratio(w, h),
                        }
                    )
                except Exception:
                    pass
                if isinstance(ui, dict):
                    facts.update(impl._extract_image_facts_from_ui(ui))
                    facts["analysis_summary"] = summary
                    if ui.get("filter_recommendations"):
                        facts["filter_recommendations"] = ui.get("filter_recommendations")

                spec = impl._default_spec(facts, message or "")
                selected, candidates = impl._route_templates(spec, facts)
                messages = []
                if isinstance(message, str) and message.strip():
                    messages.append({"role": "user", "content": message.strip()})

                patch = {}
                questions = []
                llm_selected = None
                if impl._get_gemini_api_key():
                    try:
                        patch, questions, llm_selected = impl._llm_clarify_next(spec, facts, messages, candidates)
                    except Exception as exc:
                        impl.logger.warning("smart_start_stream llm_clarify failed: %s", exc)

                spec = impl._deep_merge(spec, patch or {})
                selected, candidates = impl._route_templates(spec, facts)
                if llm_selected and any(c.get("template") == llm_selected for c in candidates if isinstance(c, dict)):
                    selected = llm_selected

                if not questions:
                    if selected == "text_design" and not ((spec.get("text_overlay") or {}).get("content") or ""):
                        questions = [{"id": "q_text", "text": "需要渲染的文字内容是什么？请逐字给出。", "choices": None}]
                    if selected == "sticker_icon" and not ((spec.get("output") or {}).get("background") or ""):
                        questions = [{"id": "q_bg", "text": "贴纸背景要透明还是白色？", "choices": ["transparent", "white"]}]
                    if selected == "negative_space" and not ((spec.get("output") or {}).get("negative_space") or ""):
                        questions = [
                            {
                                "id": "q_space",
                                "text": "需要留白的位置是哪里？例如：top-left / top-right / bottom-left / bottom-right / center。",
                                "choices": ["top-left", "top-right", "bottom-left", "bottom-right", "center"],
                            }
                        ]
                    face_count = facts.get("face_count")
                    if isinstance(face_count, int) and face_count > 0 and (spec.get("must_keep") or {}).get("identity") is None:
                        questions = (questions or [])[:1] + [{"id": "q_id", "text": "人物面部/身份是否必须完全不变？", "choices": ["必须不变", "允许略微调整"]}]

                status = "ready" if (not questions and impl._is_ready_to_render(spec, selected)) else "needs_input"

                session_id = impl._insert_smart_session(
                    saved_image_path, image.filename, spec, facts, status=status, record_id=record_id
                )
                try:
                    if isinstance(message, str) and message.strip():
                        impl._add_smart_session_message(session_id, "user", message.strip())
                except Exception:
                    pass
                impl._update_smart_session(
                    session_id, template_selected=selected, template_candidates=candidates, status=status
                )

                prompt_preview = None
                if status == "ready":
                    try:
                        prompt_preview, _ = impl._compile_prompt(spec, facts, selected)
                    except Exception:
                        prompt_preview = None

                log_path = impl._write_json_log(
                    "smart_start_stream",
                    saved_image_path,
                    [],
                    params={
                        "session_id": session_id,
                        "template_selected": selected,
                        "template_candidates": candidates,
                        "spec": spec,
                        "facts": facts,
                        "questions": questions,
                        "llm_model": os.getenv("SMART_LLM_MODEL", "gemini-2.5-flash"),
                    },
                    steps=[],
                    summary=summary,
                    events=[{"level": "INFO", "message": "smart_start_stream created", "value": {"status": status}}],
                    local_output_paths=[],
                    record_id=record_id,
                )
                if record_id:
                    try:
                        impl._update_record_logs(record_id, log_path)
                    except Exception:
                        pass

                session = impl.SmartSessionStartResponse(
                    session_id=session_id,
                    record_id=record_id,
                    status=status,
                    spec=spec,
                    facts=facts,
                    questions=[impl.SmartQuestionModel(**q) for q in questions],
                    template_selected=selected,
                    template_candidates=candidates,
                    prompt_preview=prompt_preview,
                    image_model=os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview"),
                    plan_items=impl._spec_to_plan_items(spec, facts),
                )
                try:
                    payload = session.model_dump()
                except AttributeError:
                    payload = session.dict()
                push({"type": "session", "session": payload})
            except Exception as e:
                impl.logger.warning("smart_start_stream 最终解析失败: %s", e)
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


@router.post("/smart/answer", response_model=impl.SmartSessionAnswerResponse)
async def smart_answer(req: impl.SmartSessionAnswerRequest):
    sess = impl._get_smart_session(int(req.session_id))
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    if req.answers:
        message = "\n".join([f"Q: {k}, A: {v}" for k, v in req.answers.items()])
    else:
        message = (req.message or "").strip()

    if not message:
        raise HTTPException(status_code=400, detail="empty message or answers")

    spec = sess.get("spec") or {}
    facts = sess.get("facts") or {}
    candidates = sess.get("template_candidates") or []
    impl._add_smart_session_message(sess["id"], "user", message)

    history = impl._list_smart_session_messages(sess["id"], limit=50)
    msgs = [{"role": m["role"], "content": m["content"]} for m in history]

    patch = {}
    questions = []
    llm_selected = None
    if impl._get_gemini_api_key():
        try:
            patch, questions, llm_selected = impl._llm_clarify_next(spec, facts, msgs, candidates)
        except Exception as exc:
            impl.logger.warning("smart_answer llm_clarify failed: %s", exc)

    spec = impl._deep_merge(spec, patch or {})
    selected, candidates = impl._route_templates(spec, facts)
    if llm_selected and any(c.get("template") == llm_selected for c in candidates if isinstance(c, dict)):
        selected = llm_selected

    if not questions:
        if selected == "text_design" and not ((spec.get("text_overlay") or {}).get("content") or ""):
            questions = [{"id": "q_text", "text": "需要渲染的文字内容是什么？请逐字给出。", "choices": None}]
        if selected == "sticker_icon" and not ((spec.get("output") or {}).get("background") or ""):
            questions = [{"id": "q_bg", "text": "贴纸背景要透明还是白色？", "choices": ["transparent", "white"]}]
        if selected == "negative_space" and not ((spec.get("output") or {}).get("negative_space") or ""):
            questions = [
                {
                    "id": "q_space",
                    "text": "需要留白的位置是哪里？例如：top-left / top-right / bottom-left / bottom-right / center。",
                    "choices": ["top-left", "top-right", "bottom-left", "bottom-right", "center"],
                }
            ]

    status = "ready" if (not questions and impl._is_ready_to_render(spec, selected)) else "needs_input"
    impl._update_smart_session(sess["id"], spec=spec, facts=facts, template_selected=selected, template_candidates=candidates, status=status)

    prompt_preview = None
    if status == "ready":
        try:
            prompt_preview, _ = impl._compile_prompt(spec, facts, selected)
        except Exception:
            prompt_preview = None

    impl._write_json_log(
        "smart_answer",
        sess["image_path"],
        [],
        params={
            "session_id": sess["id"],
            "template_selected": selected,
            "template_candidates": candidates,
            "spec_patch": patch,
            "spec": spec,
            "facts": facts,
            "questions": questions,
            "llm_model": os.getenv("SMART_LLM_MODEL", "gemini-2.5-flash"),
        },
        steps=[],
        summary="",
        events=[{"level": "INFO", "message": "smart_answer processed", "value": {"status": status}}],
        local_output_paths=[],
        record_id=sess.get("record_id"),
    )

    return impl.SmartSessionAnswerResponse(
        session_id=sess["id"],
        status=status,
        spec=spec,
        facts=facts,
        questions=[impl.SmartQuestionModel(**q) for q in questions],
        template_selected=selected,
        template_candidates=candidates,
        prompt_preview=prompt_preview,
        image_model=os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview"),
        plan_items=impl._spec_to_plan_items(spec, facts),
        summary=facts.get("analysis_summary") if isinstance(facts, dict) else None,
    )


@router.post("/smart/generate", response_model=impl.SmartSessionGenerateResponse)
async def smart_generate(req: impl.SmartSessionGenerateRequest):
    sess = impl._get_smart_session(int(req.session_id))
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    spec = sess.get("spec") or {}
    facts = sess.get("facts") or {}
    selected = sess.get("template_selected") or "photo_retouch"
    if sess.get("status") != "ready":
        selected, _cands = impl._route_templates(spec, facts)
        if not impl._is_ready_to_render(spec, selected):
            raise HTTPException(status_code=400, detail="session not ready; answer pending questions")

    if isinstance(req.resolution, str) and req.resolution.strip():
        spec = impl._deep_merge(spec, {"output": {"resolution": req.resolution.strip()}})
    elif not (spec.get("output") or {}).get("resolution"):
        spec = impl._deep_merge(spec, {"output": {"resolution": "1K"}})
    if isinstance(req.aspect_ratio, str) and req.aspect_ratio.strip():
        spec = impl._deep_merge(spec, {"output": {"aspect_ratio": req.aspect_ratio.strip()}})

    prompt_text, image_config = impl._compile_prompt(spec, facts, selected)

    print("\n" + "=" * 50)
    print("FINAL PROMPT SENT TO GEMINI:")
    print(prompt_text)
    print("=" * 50 + "\n")
    impl.logger.info("FINAL PROMPT SENT TO GEMINI: \n%s", prompt_text)

    image_model = os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview")
    try:
        with open(sess["image_path"], "rb") as f:
            image_bytes = f.read()
    except Exception:
        raise HTTPException(status_code=500, detail="failed to read session image")
    mime_type = impl._infer_mime_from_filename(sess.get("original_name") or sess["image_path"])

    urls, local_paths, raw = impl._gemini_image_edit_native(
        model=image_model,
        prompt_text=prompt_text,
        image_bytes=image_bytes,
        mime_type=mime_type,
        aspect_ratio=image_config.get("aspectRatio"),
        resolution=image_config.get("imageSize"),
    )

    record_id = sess.get("record_id")
    if record_id:
        try:
            for p in local_paths:
                impl._insert_record_image(record_id=record_id, kind="final", image_path=p)
        except Exception:
            pass

    # Convert relative URLs to absolute URLs for cross-device access
    served_urls: list[str] = []
    if local_paths:
        base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
        served_urls = [f"{base}/static/{Path(p).name}" for p in local_paths]
    else:
        # If URLs are already absolute, use them as-is; otherwise prepend base URL
        base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
        for url in urls:
            if url.startswith("http://") or url.startswith("https://"):
                served_urls.append(url)
            else:
                served_urls.append(f"{base}{url}")

    log_path = impl._write_json_log(
        "smart_generate",
        sess["image_path"],
        served_urls,
        params={
            "session_id": sess["id"],
            "template_selected": selected,
            "spec": spec,
            "facts": facts,
            "prompt": prompt_text,
            "image_model": image_model,
            "image_config": image_config,
        },
        steps=[],
        summary="",
        events=[{"level": "INFO", "message": "smart_generate completed", "value": {"outputs": len(served_urls)}}],
        local_output_paths=local_paths,
        record_id=record_id,
    )
    if record_id:
        try:
            impl._update_record_logs(record_id, log_path)
        except Exception:
            pass

    impl._update_smart_session(sess["id"], spec=spec, template_selected=selected, status="generated")

    return impl.SmartSessionGenerateResponse(
        session_id=sess["id"],
        status="generated",
        prompt=prompt_text,
        image_model=image_model,
        image_config=image_config,
        urls=served_urls,
        record_id=record_id,
    )
