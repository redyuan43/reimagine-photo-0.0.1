from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import server as impl

router = APIRouter(dependencies=[Depends(impl.require_api_auth)])


@router.post("/records", response_model=impl.RecordModel)
async def create_record(
    _auth: None = Depends(impl.require_api_auth),
    image: UploadFile = File(...),
    prompt: str = Form(...),
    thinking: Optional[str] = Form(None),
    logs: Optional[str] = Form(None),
    raw_response: Optional[str] = Form(None),
    original_name: Optional[str] = Form(None),
):
    payload = await image.read()
    image_path = impl._save_image_bytes(image.filename or "image.png", payload)
    record = impl._insert_record(
        prompt=prompt or "",
        thinking=thinking,
        image_path=image_path,
        logs=logs,
        original_name=original_name or image.filename,
        raw_response=raw_response,
    )
    impl._insert_record_image(record_id=record.id, kind="input", image_path=image_path)
    return record


@router.get("/records", response_model=impl.RecordListResponse)
def list_records(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return impl._list_records(limit=limit, offset=offset)


@router.get("/records/{record_id}", response_model=impl.RecordDetailModel)
def get_record(record_id: int):
    record = impl._get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"record {record_id} not found")
    images = impl._list_record_images(record_id)
    return impl.RecordDetailModel(**record.model_dump(), images=images)


@router.get("/logs")
def fetch_logs(lines: int = 200, _auth: None = Depends(impl.require_api_auth)):
    lines = max(1, min(lines, 2000))
    return {"lines": impl._read_log_tail(lines)}


@router.post("/records/{record_id}/images", response_model=impl.RecordImageModel)
async def upload_record_image(
    record_id: int,
    _auth: None = Depends(impl.require_api_auth),
    image: UploadFile = File(...),
    kind: str = Form("intermediate"),
):
    kind = (kind or "intermediate").strip().lower()
    if kind not in {"input", "intermediate", "final", "other"}:
        raise HTTPException(status_code=400, detail="kind must be one of: input, intermediate, final, other")
    if not impl._get_record(record_id):
        raise HTTPException(status_code=404, detail=f"record {record_id} not found")
    payload = await image.read()
    image_path = impl._save_image_bytes(image.filename or "image.png", payload)
    record_image = impl._insert_record_image(record_id=record_id, kind=kind, image_path=image_path)
    return record_image
