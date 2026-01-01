from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

import server as impl

router = APIRouter()


@router.post("/preview")
async def preview(image: UploadFile = File(...), _auth: None = Depends(impl.require_api_auth)):
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    img = impl._load_image_from_bytes(payload, image.filename or "image.bin")
    try:
        img.thumbnail((1600, 1600))
    except Exception:
        pass
    data, mime = impl._pil_to_bytes(img, "png")
    return StreamingResponse(io.BytesIO(data), media_type=mime, headers={"Cache-Control": "no-cache"})


@router.post("/convert")
async def convert(
    _auth: None = Depends(impl.require_api_auth),
    image: UploadFile = File(...),
    format: str = Form("jpeg"),
    quality: int = Form(90),
    compression: int = Form(6),
    resize_w: int | None = Form(None),
    resize_h: int | None = Form(None),
    color: str = Form("RGB"),
    copyright: str = Form(""),
    metadata: str = Form(""),
    wm_text: str = Form(""),
    wm_pos: str = Form("BR"),
    wm_opacity: float = Form(0.0),
    wm_size: int = Form(24),
):
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    img = impl._load_image_from_bytes(payload, image.filename or "image.bin")
    try:
        if resize_w and resize_h and resize_w > 0 and resize_h > 0:
            img = img.resize((int(resize_w), int(resize_h)))
    except Exception:
        pass
    try:
        col = (color or "RGB").upper()
        if col == "GRAY":
            img = img.convert("L")
        else:
            img = img.convert("RGB")
    except Exception:
        pass

    try:
        txt = (wm_text or "").strip()
        pos = (wm_pos or "BR").upper()
        op = float(wm_opacity or 0.0)
        sz = int(wm_size or 24)
        if txt and op > 0:
            from PIL import Image, ImageDraw, ImageFont

            base = img.convert("RGBA")
            layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            try:
                fnt = ImageFont.truetype("arial.ttf", sz)
            except Exception:
                from PIL import ImageFont as _IF

                fnt = _IF.load_default()
            tw, th = d.textsize(txt, font=fnt)
            margin = max(8, sz // 2)
            if pos == "TL":
                x = margin
                y = margin
            else:
                x = base.size[0] - tw - margin
                y = base.size[1] - th - margin
            bg = int(255 * op * 0.6)
            fg = int(255 * op)
            d.rectangle([x - 6, y - 4, x + tw + 6, y + th + 4], fill=(0, 0, 0, bg))
            d.text((x, y), txt, font=fnt, fill=(255, 255, 255, fg))
            img = Image.alpha_composite(base, layer).convert("RGB")
    except Exception:
        pass

    extra = {}
    try:
        meta_obj = impl.json.loads(metadata or "{}")
        if isinstance(meta_obj, dict):
            cam = meta_obj.get("camera")
            exif_obj = meta_obj.get("exif") or {}
            iptc_obj = meta_obj.get("iptc") or {}
            if cam:
                extra["Description"] = str(cam)
            artist = exif_obj.get("Artist") or iptc_obj.get("Byline")
            if artist:
                extra["Artist"] = str(artist)
            software = exif_obj.get("Software") or "Lumima Retouch"
            if software:
                extra["Software"] = str(software)
            dt = exif_obj.get("DateTime")
            if dt:
                extra["DateTime"] = str(dt)
    except Exception:
        pass
    if isinstance(copyright, str) and copyright.strip():
        try:
            extra["Copyright"] = copyright
        except Exception:
            pass

    data, mime = impl._pil_to_bytes(img, format.lower(), quality, compression, extra_info=extra)
    return StreamingResponse(io.BytesIO(data), media_type=mime, headers={"Cache-Control": "no-cache"})


@router.get("/proxy_image")
def proxy_image(url: str, _auth: None = Depends(impl.require_api_auth)):
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid url")
    try:
        r = impl.requests.get(url, timeout=30)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"fetch failed {r.status_code}")
        ct = r.headers.get("content-type") or "application/octet-stream"
        return StreamingResponse(io.BytesIO(r.content), media_type=ct)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
