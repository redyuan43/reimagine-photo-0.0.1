from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import server as impl

router = APIRouter()


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
    )


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

    log_path = impl._write_json_log(
        "smart_generate",
        sess["image_path"],
        urls,
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
        events=[{"level": "INFO", "message": "smart_generate completed", "value": {"outputs": len(urls)}}],
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
        urls=urls,
        record_id=record_id,
    )

