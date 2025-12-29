import os
import json
import base64
import tempfile
import requests
import time
import logging
import io
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from starlette.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import threading
import mimetypes
def _load_local_env():
    paths = [Path('.local.env'), Path('.env.local')]
    for p in paths:
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        s = line.strip()
                        if not s or s.startswith('#'):
                            continue
                        if '=' not in s:
                            continue
                        k, v = s.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
            except Exception:
                pass

_load_local_env()

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import dashscope
    from dashscope import MultiModalConversation
    def _normalize_endpoint(v: str) -> str:
        try:
            v = (v or "").strip()
            if not v:
                return "https://dashscope.aliyuncs.com/api/v1"
            # If user provided a full service path, truncate to /api/v1
            if "/api/v1" in v:
                base = v.split("/api/v1", 1)[0] + "/api/v1"
                return base
            # Fallback: accept host root and append /api/v1
            if v.endswith("/"):
                v = v[:-1]
            return v + "/api/v1"
        except Exception:
            return "https://dashscope.aliyuncs.com/api/v1"
    dashscope.base_http_api_url = _normalize_endpoint(os.getenv("IMAGE_EDIT_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1"))
except Exception:
    MultiModalConversation = None

try:
    from enhanced_prompt import get_enhanced_prompt, sanitize_summary_ui
except ImportError:
    def get_enhanced_prompt():
        return "你是一名图像分析专家，请对输入的图片进行专业级别的结构化解析。"
    def sanitize_summary_ui(text: str) -> str:
        return (text or "").strip()

# 简化：不使用 dashscope 直接调用本地/指定推理服务

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR = DATA_DIR / "images"
LOGS_DIR = DATA_DIR / "logs"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"
LOG_PATH = DATA_DIR / "server.log"

GEMINI_BASE_PROMPT = (
    "Restore this image to stunning quality, ultra-high detail, and exceptional clarity. "
    "Apply advanced restoration techniques to eliminate noise, artifacts, and any imperfections. "
    "Optimize lighting to appear natural, balanced, and dynamic, enhancing depth and textures without overexposed highlights or excessively dark shadows. "
    "Colors should be meticulously restored to achieve a vibrant, rich, and harmonious aesthetic, characteristic of leading design magazines. "
    "Even if the original is black and white or severely faded, intelligently recolor and enhance it to meet this benchmark standard, "
    "with deep blacks, clean whites, and rich, realistic tones. The final image should appear as though captured with a high-end camera "
    "and professionally post-processed, possessing maximum depth and realism."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger("reimagine")

from starlette.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(IMAGES_DIR)), name="static")


class RecordModel(BaseModel):
    id: int
    prompt: str
    thinking: Optional[str] = None
    image_path: str
    logs: Optional[str] = None
    original_name: Optional[str] = None
    raw_response: Optional[str] = None
    created_at: str


class RecordImageModel(BaseModel):
    id: int
    record_id: int
    kind: str  # input, intermediate, final, other
    image_path: str
    created_at: str


class RecordDetailModel(RecordModel):
    images: List[RecordImageModel] = []


class RecordListResponse(BaseModel):
    total: int
    items: List[RecordModel]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                thinking TEXT,
                image_path TEXT NOT NULL,
                logs TEXT,
                original_name TEXT,
                raw_response TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Backfill new columns if table already existed
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(records)")}
        if "original_name" not in cols:
            conn.execute("ALTER TABLE records ADD COLUMN original_name TEXT")
        if "raw_response" not in cols:
            conn.execute("ALTER TABLE records ADD COLUMN raw_response TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS record_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                image_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_record(row: sqlite3.Row) -> RecordModel:
    return RecordModel(
        id=row["id"],
        prompt=row["prompt"],
        thinking=row["thinking"],
        image_path=row["image_path"],
        logs=row["logs"],
        original_name=row["original_name"] if "original_name" in row.keys() else None,
        raw_response=row["raw_response"] if "raw_response" in row.keys() else None,
        created_at=row["created_at"],
    )


def _row_to_image(row: sqlite3.Row) -> RecordImageModel:
    return RecordImageModel(
        id=row["id"],
        record_id=row["record_id"],
        kind=row["kind"],
        image_path=row["image_path"],
        created_at=row["created_at"],
    )


def _save_image_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename or "image").suffix or ".png"
    dest_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{ext}"
    dest_path = IMAGES_DIR / dest_name
    with open(dest_path, "wb") as f:
        f.write(data)
    logger.info("Saved image to %s (%d bytes)", dest_path, len(data))
    return str(dest_path)

def _download_and_save_image(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            logger.warning("下载输出失败 status=%s url=%s", r.status_code, url)
            return None
        ct = r.headers.get("content-type") or "image/png"
        ext = ".png"
        try:
            guess = mimetypes.guess_extension(ct.split(";")[0].strip())
            if guess:
                ext = guess
        except Exception:
            pass
        name = f"output{ext}"
        return _save_image_bytes(name, r.content)
    except Exception as exc:
        logger.warning("下载输出异常: %s", exc)
        return None

def _file_metadata(path: str) -> dict:
    try:
        p = Path(path)
        st = p.stat()
        mime, _ = mimetypes.guess_type(str(p))
        return {
            "path": str(p.resolve()),
            "exists": True,
            "size_bytes": st.st_size,
            "modified_at": datetime.utcfromtimestamp(st.st_mtime).isoformat(),
            "mime": mime or "unknown",
        }
    except Exception:
        return {"path": path, "exists": False}

def _load_image_from_bytes(data: bytes, filename: str):
    try:
        from PIL import Image as _Image
    except Exception:
        raise HTTPException(status_code=500, detail="Pillow not available on server")
    # Try HEIC regardless of extension
    try:
        import pillow_heif as _pheif
        heif = _pheif.read_heif(data)
        return _Image.frombytes(heif.mode, heif.size, heif.data)
    except Exception:
        pass
    # Try RAW regardless of extension
    try:
        import rawpy as _rawpy
        import numpy as _np
        with _rawpy.imread(io.BytesIO(data)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8, gamma=(1, 1))
        return _Image.fromarray(rgb)
    except Exception:
        pass
    # Fallback to common image types
    try:
        return _Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported image payload")

def _pil_to_bytes(img, fmt: str, quality: int | None = None, compression: int | None = None, extra_info: dict | None = None):
    buf = io.BytesIO()
    f = (fmt or 'jpeg').lower()
    if f == 'jpeg':
        q = int(quality or 90)
        try:
            img.save(buf, format='JPEG', quality=q, subsampling=0)
        except Exception:
            img.save(buf, format='JPEG', quality=q)
        mime = 'image/jpeg'
    elif f == 'png':
        c = int(compression or 6)
        try:
            from PIL.PngImagePlugin import PngInfo
            pi = PngInfo()
            if extra_info:
                for k, v in extra_info.items():
                    try:
                        pi.add_text(str(k), str(v))
                    except Exception:
                        pass
                if extra_info.get('DateTime'):
                    try:
                        pi.add_text('CreationTime', str(extra_info['DateTime']))
                    except Exception:
                        pass
            img.save(buf, format='PNG', compress_level=c, pnginfo=pi)
        except Exception:
            img.save(buf, format='PNG', compress_level=c)
        mime = 'image/png'
    elif f == 'webp':
        q = int(quality or 85)
        img.save(buf, format='WEBP', quality=q)
        mime = 'image/webp'
    elif f == 'tiff':
        try:
            from PIL.TiffImagePlugin import ImageFileDirectory_v2
            ifd = ImageFileDirectory_v2()
            if extra_info:
                desc = str(extra_info.get('Description') or '')
                cr = str(extra_info.get('Copyright') or '')
                artist = str(extra_info.get('Artist') or '')
                software = str(extra_info.get('Software') or '')
                dt = str(extra_info.get('DateTime') or '')
                if desc:
                    ifd[270] = desc
                if cr:
                    ifd[33432] = cr
                if artist:
                    ifd[315] = artist
                if software:
                    ifd[305] = software
                if dt:
                    ifd[306] = dt
            img.save(buf, format='TIFF', tiffinfo=ifd)
        except Exception:
            img.save(buf, format='TIFF')
        mime = 'image/tiff'
    else:
        raise HTTPException(status_code=400, detail="Unsupported output format")
    return buf.getvalue(), mime

def _resize_image_max(img, max_side: int):
    try:
        w, h = img.size
        m = int(max_side)
        if w <= m and h <= m:
            return img
        if w >= h:
            nw = m
            nh = int(h * m / w)
        else:
            nh = m
            nw = int(w * m / h)
        return img.resize((nw, nh))
    except Exception:
        return img

def _write_json_log(operation: str, input_path: str | None, output_urls: list[str] | None, params: dict | None, steps: list | None, summary: str | None, events: list[dict] | None, local_output_paths: Optional[list[str]] = None, record_id: Optional[int] = None) -> str:
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "operation": operation,
        "input": _file_metadata(input_path) if input_path else None,
        "outputs": output_urls or [],
        "local_outputs": [ _file_metadata(p) for p in (local_output_paths or []) ],
        "params": params or {},
        "steps": steps or [],
        "summary": summary or "",
        "events": events or [],
        "record_id": record_id,
    }
    fname = f"log_{operation}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}.json"
    fpath = LOGS_DIR / fname
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("日志已写入 %s", fpath)
    except Exception as exc:
        logger.error("写入日志失败: %s", exc)
    return str(fpath)

def _update_record_logs(record_id: int, logs_path: str) -> None:
    try:
        with _get_conn() as conn:
            conn.execute("UPDATE records SET logs = ? WHERE id = ?", (logs_path, record_id))
            conn.commit()
        logger.info("记录 %s 日志路径更新: %s", record_id, logs_path)
    except Exception as exc:
        logger.warning("更新记录日志失败: %s", exc)


def _insert_record(
    prompt: str,
    thinking: Optional[str],
    image_path: str,
    logs: Optional[str],
    original_name: Optional[str] = None,
    raw_response: Optional[str] = None,
) -> RecordModel:
    created_at = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO records (prompt, thinking, image_path, logs, original_name, raw_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt, thinking, image_path, logs, original_name, raw_response, created_at),
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, prompt, thinking, image_path, logs, original_name, raw_response, created_at FROM records WHERE id = ?",
            (new_id,),
        ).fetchone()
    logger.info("Created record %s", new_id)
    return _row_to_record(row)


def _insert_record_image(record_id: int, kind: str, image_path: str) -> RecordImageModel:
    created_at = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO record_images (record_id, kind, image_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (record_id, kind, image_path, created_at),
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, record_id, kind, image_path, created_at FROM record_images WHERE id = ?",
            (new_id,),
        ).fetchone()
    logger.info("Saved record image %s (record=%s kind=%s)", new_id, record_id, kind)
    return _row_to_image(row)


def _get_record(record_id: int) -> Optional[RecordModel]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, prompt, thinking, image_path, logs, original_name, raw_response, created_at FROM records WHERE id = ?",
            (record_id,),
        ).fetchone()
    return _row_to_record(row) if row else None


def _list_record_images(record_id: int) -> List[RecordImageModel]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, record_id, kind, image_path, created_at
            FROM record_images
            WHERE record_id = ?
            ORDER BY created_at ASC
            """,
            (record_id,),
        ).fetchall()
    return [_row_to_image(r) for r in rows]


def _list_records(limit: int = 50, offset: int = 0) -> RecordListResponse:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, prompt, thinking, image_path, logs, original_name, raw_response, created_at
            FROM records
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        total_row = conn.execute("SELECT COUNT(1) as c FROM records").fetchone()
        total = total_row["c"] if total_row else 0
    items = [_row_to_record(r) for r in rows]
    return RecordListResponse(total=total, items=items)


def _read_log_tail(lines: int = 200) -> List[str]:
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        content = f.readlines()
    lines = max(1, min(lines, 2000))
    return [line.rstrip("\n") for line in content[-lines:]]


def _extract_thinking(result: Optional[dict]) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    keys = [
        "thinking",
        "thoughts",
        "reasoning",
        "analysis",
        "chain_of_thought",
        "chain_of_thoughts",
    ]
    for k in keys:
        if k in result:
            val = result.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, list):
                joined = "\n".join([str(x) for x in val if str(x).strip()])
                if joined.strip():
                    return joined.strip()
    return None


def _safe_json_dump(data: object) -> Optional[str]:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return None


_init_db()


@app.post("/records", response_model=RecordModel)
async def create_record(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    thinking: Optional[str] = Form(None),
    logs: Optional[str] = Form(None),
    raw_response: Optional[str] = Form(None),
    original_name: Optional[str] = Form(None),
):
    payload = await image.read()
    image_path = _save_image_bytes(image.filename or "image.png", payload)
    record = _insert_record(
        prompt=prompt or "",
        thinking=thinking,
        image_path=image_path,
        logs=logs,
        original_name=original_name or image.filename,
        raw_response=raw_response,
    )
    _insert_record_image(record_id=record.id, kind="input", image_path=image_path)
    return record


@app.get("/records", response_model=RecordListResponse)
def list_records(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return _list_records(limit=limit, offset=offset)


@app.get("/records/{record_id}", response_model=RecordDetailModel)
def get_record(record_id: int):
    record = _get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"record {record_id} not found")
    images = _list_record_images(record_id)
    return RecordDetailModel(**record.model_dump(), images=images)


@app.get("/logs")
def fetch_logs(lines: int = 200):
    lines = max(1, min(lines, 2000))
    return {"lines": _read_log_tail(lines)}

@app.post("/preview")
async def preview(image: UploadFile = File(...)):
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    img = _load_image_from_bytes(payload, image.filename or "image.bin")
    try:
        img.thumbnail((1600, 1600))
    except Exception:
        pass
    data, mime = _pil_to_bytes(img, 'png')
    return StreamingResponse(io.BytesIO(data), media_type=mime, headers={"Cache-Control": "no-cache"})

@app.post("/convert")
async def convert(
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
    img = _load_image_from_bytes(payload, image.filename or "image.bin")
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
            from PIL import ImageDraw, ImageFont, Image
            base = img.convert("RGBA")
            layer = Image.new("RGBA", base.size, (0,0,0,0))
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
            d.rectangle([x - 6, y - 4, x + tw + 6, y + th + 4], fill=(0,0,0,bg))
            d.text((x, y), txt, font=fnt, fill=(255,255,255,fg))
            img = Image.alpha_composite(base, layer).convert("RGB")
    except Exception:
        pass

    # Basic metadata embedding (best-effort)
    info = {}
    if isinstance(metadata, str) and metadata.strip():
        try:
            info["Description"] = metadata
        except Exception:
            pass
    if isinstance(copyright, str) and copyright.strip():
        try:
            info["Copyright"] = copyright
        except Exception:
            pass

    extra = {}
    exif_obj = {}
    try:
        meta_obj = json.loads(metadata or "{}")
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

    data, mime = _pil_to_bytes(img, format.lower(), quality, compression, extra_info=extra)
    return StreamingResponse(io.BytesIO(data), media_type=mime, headers={"Cache-Control": "no-cache"})

@app.get("/proxy_image")
def proxy_image(url: str):
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid url")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"fetch failed {r.status_code}")
        ct = r.headers.get("content-type") or "application/octet-stream"
        return StreamingResponse(io.BytesIO(r.content), media_type=ct, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/records/{record_id}/images", response_model=RecordImageModel)
async def upload_record_image(
    record_id: int,
    image: UploadFile = File(...),
    kind: str = Form("intermediate"),
):
    kind = (kind or "intermediate").strip().lower()
    if kind not in {"input", "intermediate", "final", "other"}:
        raise HTTPException(status_code=400, detail="kind must be one of: input, intermediate, final, other")
    if not _get_record(record_id):
        raise HTTPException(status_code=404, detail=f"record {record_id} not found")
    payload = await image.read()
    image_path = _save_image_bytes(image.filename or "image.png", payload)
    record_image = _insert_record_image(record_id=record_id, kind=kind, image_path=image_path)
    return record_image


def _parse_ui_to_plan_items(ui: dict):
    items = []
    for idx, p in enumerate(ui.get("professional_analysis") or []):
        items.append({
            "id": p.get("id") or str(idx + 1),
            "problem": p.get("problem") or "",
            "solution": p.get("solution") or "",
            "engine": p.get("engine") or "Analysis",
            "category": p.get("category") or "发现问题",
            "type": "generative" if (p.get("type") == "generative") else "adjustment",
            "checked": True,
        })

    fr = ui.get("filter_recommendations") or {}
    primary = fr.get("primary_filter") or {}
    alts = fr.get("alternative_filters") or []
    options = []
    if primary.get("name"):
        options.append(primary.get("name"))
    for a in alts:
        if a.get("name"):
            options.append(a.get("name"))
    if options:
        items.append({
            "id": "filter_opt",
            "problem": "",
            "solution": primary.get("description") or "Apply Artistic Filter",
            "engine": "Filter",
            "category": "风格滤镜",
            "type": "adjustment",
            "checked": False,
            "options": options,
        })
    return items

def _sse_event(obj: dict):
    return f"data:{json.dumps(obj, ensure_ascii=False)}\n\n"

def _extract_professional_items(buffer: str, sent_count: int):
    items = []
    idx = buffer.find("\"professional_analysis\"")
    if idx == -1:
        return items
    arr_start = buffer.find("[", idx)
    if arr_start == -1:
        return items
    i = arr_start + 1
    brace = 0
    cur = []
    count = 0
    while i < len(buffer):
        ch = buffer[i]
        cur.append(ch)
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
            if brace == 0:
                seg = "{" + "".join(cur).split("{",1)[1]
                try:
                    obj = json.loads(seg)
                    count += 1
                    if count > sent_count:
                        items.append(obj)
                except Exception:
                    pass
                cur = []
                j = i + 1
                while j < len(buffer) and buffer[j] in [",", " ", "\n", "\r", "\t"]:
                    j += 1
                i = j - 1
        elif ch == "]":
            break
        i += 1
    return items

def analyze_image_with_qwen3_vl_plus(image_path: str, verbose: bool = True, stream_output: bool = True, enable_thinking: bool = False):
    prompt_text = get_enhanced_prompt()
    with open(image_path, 'rb') as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')

    base_url = os.getenv("DASHSCOPE_COMPAT_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    start_time = time.time()
    print("图像分析配置:")
    print(f"   图像文件: {image_path}")
    print(f"   详细统计: {'开启' if verbose else '关闭'}")
    print(f"   流式输出: {'开启' if stream_output else '关闭'}")
    print(f"   模型: qwen3-vl-plus")
    print(f"   接口: {base_url}")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print("-" * 60)

    data_url = f"data:image/jpeg;base64,{base64_image}"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt_text},
            ],
        },
    ]

    # 直接使用 HTTP 兼容模式调用一次
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    body = {
        "model": "qwen3-vl-plus",
        "messages": messages,
        "temperature": 0.1,
        "top_p": 0.1,
        "max_tokens": 2048,
        "stream": bool(stream_output),
        "extra_body": {
            "enable_thinking": bool(enable_thinking),
            "thinking_budget": 81920,
        },
    }
    print("HTTP兼容模式调用")
    r = requests.post(url, json=body, headers=headers, timeout=180, stream=bool(stream_output))
    print(f"HTTP状态码: {r.status_code}")
    if r.status_code != 200:
        try:
            print(f"响应: {r.text[:300]}")
        except Exception:
            pass
        return None
    if stream_output:
        text = ""
        for line in r.iter_lines():
            if not line:
                continue
            try:
                s = line.decode("utf-8").strip()
                if not s:
                    continue
                if s.startswith("data:"):
                    s = s[5:].strip()
                data = json.loads(s)
                chs = data.get("choices") or []
                if chs:
                    delta = chs[0].get("delta") or {}
                    if delta.get("content"):
                        c = delta.get("content")
                        print(c, end='', flush=True)
                        text += c
            except Exception:
                continue
    else:
        data = r.json()
        try:
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except Exception:
            text = ""
    if verbose:
        end_time = time.time()
        total_time = end_time - start_time
        print("\n\n性能统计:")
        print(f"   总耗时: {total_time:.2f}秒")
        print(f"   完成时间: {datetime.now().strftime('%H:%M:%S')}")
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())

@app.post("/analyze")
async def analyze(image: UploadFile = File(...), prompt: str = Form("")):
    print("收到分析请求")
    buf = await image.read()
    print(f"接收字节: {len(buf)}")
    logger.info("Analyze request received bytes=%d prompt_len=%d", len(buf), len(prompt or ""))
    saved_image_path = _save_image_bytes(image.filename or "image.png", buf)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(buf)
    tmp.flush()
    tmp.close()

    result = analyze_image_with_qwen3_vl_plus(tmp.name, stream_output=True, enable_thinking=True)
    thinking_text = _extract_thinking(result if isinstance(result, dict) else None)
    raw_json = _safe_json_dump(result) if isinstance(result, (dict, list)) else None
    ui = result.get("ui_analysis") if isinstance(result, dict) else None
    items = _parse_ui_to_plan_items(ui or {})
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
    logger.info("Analyze response items=%d summary_len=%d", len(items), len(summary or ""))
    try:
        rec = _insert_record(
            prompt=prompt or "",
            thinking=thinking_text,
            image_path=saved_image_path,
            logs=raw_json,
            original_name=image.filename,
            raw_response=raw_json,
        )
        try:
            _insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Failed to persist analyze record: %s", exc)
    return {"analysis": items, "summary": sanitize_summary_ui(summary or "")}

def _encode_image_to_data_url(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError("Unsupported image type")
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"

@app.post("/magic_edit")
async def magic_edit(
    image: UploadFile = File(...),
    prompt: str = Form(""),
    n: int = Form(1),
    size: str = Form(""),
    watermark: bool = Form(False),
    negative_prompt: str = Form(""),
    prompt_extend: bool = Form(True),
):
    # 优先使用 VISION_API_KEY (Google Gemini OpenAI 兼容模式)
    vision_api_key = os.getenv("VISION_API_KEY")
    image_edit_endpoint = os.getenv("IMAGE_EDIT_ENDPOINT")
    model = os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-preview")

    if not vision_api_key:
        # 退回到 DashScope
        if MultiModalConversation is None:
            raise HTTPException(status_code=500, detail="dashscope SDK not available on server")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Neither VISION_API_KEY nor DASHSCOPE_API_KEY configured")
    else:
        api_key = vision_api_key

    payload = await image.read()
    logger.info("magic_edit received bytes=%d", len(payload or b""))
    if not payload:
        raise HTTPException(status_code=400, detail="No image payload")
    original_local_path = _save_image_bytes(image.filename or "image.png", payload)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(image.filename or "image").suffix or ".png")
    tmp.write(payload)
    tmp.flush(); tmp.close()

    try:
        try:
            img = _load_image_from_bytes(payload, image.filename or "image.bin")
        except Exception:
            from PIL import Image as _Image
            img = _Image.open(tmp.name)
        img = _resize_image_max(img, 2048)
        
        # 准备缩放后的图片字节流和对应的 MIME 类型
        ext = (Path(image.filename or "").suffix or "").lower()
        raw_heic_exts = {'.heic', '.heif', '.dng', '.raw', '.arw', '.cr2', '.nef', '.raf', '.orf', '.rw2'}
        if ext in ['.jpg', '.jpeg'] or ext in raw_heic_exts:
            input_fmt = 'jpeg'
            input_mime = 'image/jpeg'
        else:
            input_fmt = 'png'
            input_mime = 'image/png'
        
        # 使用处理后的图片（缩放后），避免原始图片过大或格式不兼容
        process_bin, _ = _pil_to_bytes(img, input_fmt, quality=90 if input_fmt=='jpeg' else None)
        img_data = base64.b64encode(process_bin).decode("utf-8")

        urls = []
        local_paths = []

        # 如果是 OpenAI/Google 模式
        if vision_api_key:
            logger.info("使用 Google Gemini (Native/REST) 接口进行图片编辑: %s", model)
            
            base_url = image_edit_endpoint.replace("/openai/", "") if image_edit_endpoint else "https://generativelanguage.googleapis.com/v1beta"
            native_url = f"{base_url.rstrip('/')}/models/{model}:generateContent?key={vision_api_key}"
            
            # 组合基础提示词和用户指令
            final_prompt = f"[Standard Quality Requirements]\n{GEMINI_BASE_PROMPT}\n\n[User Specific Edit Instruction]\n{prompt}"
            
            # 构造请求体 (严格遵循 SDK 示例的 contents 结构)
            payload_json = {
                "contents": [{
                    "parts": [
                        {"text": final_prompt},
                        {
                            "inline_data": {
                                "mime_type": input_mime,
                                "data": img_data
                            }
                        }
                    ]
                }]
            }
            
            logger.info("发送请求到 Google Native API: %s (MIME: %s)", native_url, input_mime)
            resp_google = requests.post(native_url, json=payload_json, timeout=90) # 增加超时时间
            
            if resp_google.status_code == 200:
                result = resp_google.json()
                logger.info("Google API 响应成功，正在解析内容...")
                # 解析返回的 parts 提取图片
                try:
                    candidates = result.get("candidates", [])
                    if not candidates:
                        logger.warning("Gemini 未返回任何候选结果。完整响应: %s", result)
                    
                    for cand in candidates:
                        finish_reason = cand.get("finishReason")
                        if finish_reason and finish_reason != "STOP":
                            logger.warning("Gemini 任务未正常停止，原因: %s", finish_reason)
                            
                        parts = cand.get("content", {}).get("parts", [])
                        if not parts:
                            logger.warning("Gemini 候选结果中没有 parts。候选内容: %s", cand)
                            
                        for part in parts:
                            img_part = part.get("inline_data") or part.get("inlineData")
                            if img_part:
                                b64_out = img_part.get("data")
                                if not b64_out:
                                    continue
                                # 将 base64 转存为本地文件
                                out_bytes = base64.b64decode(b64_out)
                                
                                # 获取正确的后缀
                                mime_type = img_part.get('mime_type') or img_part.get('mimeType') or 'image/png'
                                ext = ".png"
                                if mime_type and ("jpeg" in mime_type or "jpg" in mime_type):
                                    ext = ".jpg"
                                
                                out_filename = f"gen_{uuid4().hex[:8]}{ext}"
                                out_path = _save_image_bytes(out_filename, out_bytes)
                                local_paths.append(out_path)
                                
                                # 转换为可以直接访问的 URL
                                base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
                                urls.append(f"{base}/static/{Path(out_path).name}")
                                logger.info("成功提取并保存生成图像: %s", out_path)
                            elif "file_data" in part or "fileData" in part:
                                logger.info("Gemini 返回了 file_data: %s", part.get("file_data") or part.get("fileData"))
                            elif "text" in part:
                                text_msg = part["text"]
                                logger.info("Gemini 返回文本消息: %s", text_msg)
                                # 如果没有图像但有文本，且文本看起来像错误信息，记录下来
                except Exception as e:
                    logger.error("解析 Gemini 返回数据失败: %s. 完整响应: %s", str(e), result)
                
                size_used = size
            else:
                logger.error("Google API 返回错误: %d %s", resp_google.status_code, resp_google.text)
                raise HTTPException(status_code=resp_google.status_code, detail=f"Google API error: {resp_google.text}")

            # 如果没有生成图片，尝试给出更具体的错误
            if not urls:
                error_msg = "Google Gemini 未能生成图像。请检查提示词是否合规或模型是否支持此操作。"
                # 检查是否有安全过滤
                if 'result' in locals() and result.get("promptFeedback", {}).get("blockReason"):
                    error_msg = f"提示词被安全过滤拦截: {result['promptFeedback']['blockReason']}"
                elif 'result' in locals() and result.get("candidates") and result["candidates"][0].get("finishReason") == "SAFETY":
                    error_msg = "响应因安全策略被拦截。"
                
                logger.error(error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
        else:
            # 原有的 DashScope 逻辑
            fmt = input_fmt
            mime = input_mime
            b64 = img_data # 复用已经缩放好的数据
            data_url = f"data:{mime};base64,{b64}"
            contents: list[dict] = [{"image": data_url}]
            logger.info("magic_edit prompt len=%d", len(prompt or ""))
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
            size_used = _normalize_size_param(size, n)
            if size_used:
                kwargs["size"] = size_used

            resp = MultiModalConversation.call(**kwargs)
            if getattr(resp, "status_code", None) == 200:
                try:
                    for c in resp.output.choices[0].message.content:
                        if isinstance(c, dict) and c.get("image"):
                            urls.append(c["image"]) 
                except Exception:
                    pass
            else:
                logger.error("magic_edit 非200 status=%s code=%s message=%s", getattr(resp, "status_code", None), getattr(resp, "code", None), getattr(resp, "message", None))
                raise HTTPException(status_code=getattr(resp, "status_code", 500), detail=getattr(resp, "message", "image edit failed"))

        if urls:
            try:
                # 只有非 Google 模式才需要重新下载 (因为 Google 模式下 local_paths 已经填好了)
                if not vision_api_key:
                    for u in urls:
                        p = _download_and_save_image(u)
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
                log_path = _write_json_log("magic_edit", original_local_path, urls, params, steps, prompt, events, local_output_paths=local_paths)
                rec = _insert_record(
                    prompt=prompt or "",
                    thinking=None,
                    image_path=original_local_path,
                    logs=log_path,
                    original_name=image.filename,
                    raw_response=_safe_json_dump({"urls": urls}),
                )
                try:
                    _insert_record_image(record_id=rec.id, kind="input", image_path=original_local_path)
                except Exception:
                    pass
                try:
                    if local_paths:
                        if len(local_paths) == 1:
                            _insert_record_image(record_id=rec.id, kind="final", image_path=local_paths[0])
                        else:
                            for p in local_paths[:-1]:
                                _insert_record_image(record_id=rec.id, kind="intermediate", image_path=p)
                            _insert_record_image(record_id=rec.id, kind="final", image_path=local_paths[-1])
                except Exception as exc:
                    logger.warning("保存输出图片记录失败: %s", exc)
            except Exception as exc:
                logger.warning("magic_edit 写日志失败: %s", exc)
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

@app.post("/analyze_stream")
async def analyze_stream(image: UploadFile = File(...), prompt: str = Form("")):
    payload = await image.read()
    logger.info("SSE 收到分析请求 bytes=%d", len(payload))
    
    # 保存原图到永久存储
    saved_image_path = _save_image_bytes(image.filename or "image.png", payload)
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(payload)
    tmp.flush()
    tmp.close()
    logger.info("SSE 临时文件=%s", tmp.name)

    base_url = os.getenv("DASHSCOPE_COMPAT_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    logger.info("SSE 配置 模型=qwen3-vl-plus接口=%s", base_url)

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
                logger.warning("SSE push 失败: %s", exc)

        def worker():
            fallback_result = None
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=base_url)
                with open(tmp.name, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{b64}"
                messages = [{"role":"user","content":[{"type":"image_url","image_url":{"url":data_url}},{"type":"text","text":get_enhanced_prompt()}]}]
                resp = client.chat.completions.create(model="qwen3-vl-plus", messages=messages, stream=True, temperature=0.1, top_p=0.1, extra_body={"enable_thinking": False, "thinking_budget": 81920})
                logger.info("SSE 连接建立，开始流式分析")
                for chunk in resp:
                    try:
                        delta = chunk.choices[0].delta
                        if delta and getattr(delta, "content", None):
                            c = delta.content
                            if c:
                                if os.getenv("SSE_LOG_CHUNK", "0") == "1":
                                    logger.info("SSE chunk 长度=%d", len(c))
                                if os.getenv("SSE_LOG_TEXT", "0") == "1":
                                    logger.info("%s", c)
                            nonlocal buffer, sent
                            buffer += c
                            new_items = _extract_professional_items(buffer, sent)
                            for it in new_items:
                                logger.info("SSE 提取项 序号=%d 类别=%s 类型=%s", sent+1, it.get('category'), it.get('type'))
                                sent += 1
                                ui = {"professional_analysis": [it]}
                                plans = _parse_ui_to_plan_items(ui)
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
                logger.warning("SSE 流式调用失败: %s", e)
                # 回退到非流式分析，确保总结与遗漏项可用
                try:
                    fallback_result = analyze_image_with_qwen3_vl_plus(tmp.name, stream_output=False, enable_thinking=True)
                    logger.info("SSE 回退分析完成")
                except Exception as e2:
                    logger.warning("SSE 回退调用失败: %s", e2)
            # finalize
            try:
                cleaned = buffer.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                data = json.loads(cleaned) if cleaned else {}
                # 若流式数据不可用，使用回退结果
                if not isinstance(data, dict) or (isinstance(data, dict) and not data):
                    if isinstance(fallback_result, dict):
                        data = fallback_result
                # 推送未发送过的计划项（包括滤镜推荐等）
                ui = data.get("ui_analysis") if isinstance(data, dict) else None
                if isinstance(ui, dict):
                    final_plans = _parse_ui_to_plan_items(ui)
                    for p in final_plans:
                        pid = p.get("id")
                        if pid and pid in sent_ids:
                            continue
                        if pid:
                            sent_ids.add(pid)
                        push({"type": "item", "item": p})
                # 提取总结（包含嵌套 ui_analysis.summary_ui 兜底）
                summary = ""
                if isinstance(data, dict):
                    summary = data.get("summary_ui") or data.get("summary") or ""
                if not summary and isinstance(ui, dict):
                    summary = ui.get("summary_ui") or ""
                # 若仍为空，尝试从回退结果提取
                if not summary and isinstance(fallback_result, dict):
                    fu = fallback_result.get("ui_analysis") if isinstance(fallback_result, dict) else None
                    summary = fallback_result.get("summary_ui") or fallback_result.get("summary") or ((fu or {}).get("summary_ui") or "")
                summary = sanitize_summary_ui(summary or "")
                logger.info("SSE 最终总结长度=%d", len(summary or ""))
                
                # 保存分析记录到数据库
                record_id = None
                try:
                    thinking_text = _extract_thinking(data if isinstance(data, dict) else None)
                    raw_json = _safe_json_dump(data) if isinstance(data, (dict, list)) else None
                    rec = _insert_record(
                        prompt=prompt or "",
                        thinking=thinking_text,
                        image_path=saved_image_path,
                        logs=raw_json,
                        original_name=image.filename,
                        raw_response=raw_json,
                    )
                    record_id = rec.id
                    try:
                        _insert_record_image(record_id=rec.id, kind="input", image_path=saved_image_path)
                    except Exception:
                        pass
                    logger.info("SSE 已保存分析记录 record_id=%d", record_id)
                except Exception as exc:
                    logger.warning("SSE 保存记录失败: %s", exc)
                
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
                    _write_json_log("analyze_stream", tmp.name, [], params, steps, summary, events, local_output_paths=[], record_id=record_id)
                except Exception as exc:
                    logger.warning("SSE 写日志失败: %s", exc)
                push({"type": "final", "summary": summary})
            except Exception as e:
                logger.warning("SSE 最终解析失败: %s", e)
                push({"type": "final", "summary": ""})
            finally:
                push({"type": "__end__"})

        threading.Thread(target=worker, daemon=True).start()

        while True:
            evt = await queue.get()
            if isinstance(evt, dict) and evt.get("type") == "__end__":
                break
            yield _sse_event(evt)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
def _normalize_size_param(size: str, n: int) -> Optional[str]:
    try:
        if n != 1:
            return None
        s = (size or "").strip()
        if not s:
            return None
        if "*" not in s:
            return None
        parts = s.split("*")
        w = int(parts[0])
        h = int(parts[1])
        # 如果尺寸不超过 2048*2048，则保持照片默认尺寸
        if w <= 2048 and h <= 2048:
            return s
        # 若超过 2048 的限制，则归一化到 2048*2048（模型只接受到此上限）
        logger.info("magic_edit 归一化输出尺寸 %s -> 2048*2048", s)
        return "2048*2048"
    except Exception:
        return None

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
