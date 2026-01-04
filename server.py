import os
import json
import base64
import tempfile
import requests
import time
import logging
import io
import sqlite3
import secrets
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
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

def _env_truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_prod_env() -> bool:
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or os.getenv("NODE_ENV") or "").strip().lower()
    return env in {"prod", "production"}


def _get_api_auth_token() -> Optional[str]:
    token = os.getenv("API_AUTH_TOKEN") or os.getenv("SERVER_TOKEN") or ""
    token = token.strip()
    return token or None


def _api_auth_enabled() -> bool:
    if _env_truthy(os.getenv("API_AUTH_DISABLED")):
        return False
    if _env_truthy(os.getenv("API_AUTH_ENABLED")):
        return True
    if _is_prod_env():
        return True
    return bool(_get_api_auth_token())


def require_api_auth(request: Request) -> None:
    if request.method == "OPTIONS":
        return
    if not _api_auth_enabled():
        return
    expected = _get_api_auth_token()
    if not expected:
        raise HTTPException(status_code=500, detail="Server misconfigured")
    auth = (request.headers.get("authorization") or "").strip()
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = (request.headers.get("x-api-key") or "").strip()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def _get_cors_allow_origins() -> list[str]:
    raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if raw:
        items = [s.strip() for s in raw.split(",") if s.strip()]
        if items:
            return items
    return ["*"] # Allow all origins by default for better compatibility


app = FastAPI()
_cors_kwargs = dict(
    allow_origins=_get_cors_allow_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
_cors_origin_regex = (os.getenv("CORS_ALLOW_ORIGIN_REGEX") or "").strip()
if _cors_origin_regex:
    _cors_kwargs["allow_origin_regex"] = _cors_origin_regex
app.add_middleware(CORSMiddleware, **_cors_kwargs)

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


class SmartQuestionModel(BaseModel):
    id: str
    text: str
    choices: Optional[List[str]] = None


class SmartSessionStartResponse(BaseModel):
    session_id: int
    record_id: Optional[int] = None
    status: str
    spec: dict
    facts: Optional[dict] = None
    questions: List[SmartQuestionModel] = []
    template_selected: Optional[str] = None
    template_candidates: Optional[list] = None
    prompt_preview: Optional[str] = None
    image_model: Optional[str] = None
    plan_items: Optional[List[dict]] = None
    summary: Optional[str] = None


class SmartSessionAnswerResponse(BaseModel):
    session_id: int
    status: str
    spec: dict
    facts: Optional[dict] = None
    questions: List[SmartQuestionModel] = []
    template_selected: Optional[str] = None
    template_candidates: Optional[list] = None
    prompt_preview: Optional[str] = None
    image_model: Optional[str] = None
    plan_items: Optional[List[dict]] = None
    summary: Optional[str] = None


class SmartSessionGenerateResponse(BaseModel):
    session_id: int
    status: str
    prompt: str
    image_model: str
    image_config: dict
    urls: List[str]
    record_id: Optional[int] = None


class SmartSessionAnswerRequest(BaseModel):
    session_id: int
    message: Optional[str] = None
    answers: Optional[dict] = None


class SmartSessionGenerateRequest(BaseModel):
    session_id: int
    resolution: Optional[str] = None
    aspect_ratio: Optional[str] = None


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smart_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                original_name TEXT,
                spec_json TEXT NOT NULL,
                facts_json TEXT,
                template_selected TEXT,
                template_candidates_json TEXT,
                status TEXT NOT NULL,
                record_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smart_session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
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
    p = Path(filename or "image.png")
    ext = p.suffix or ".png"
    prefix = p.stem
    dest_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{prefix}_{uuid4().hex[:4]}{ext}"
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


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _json_dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: Optional[str], default: object):
    if not isinstance(s, str) or not s.strip():
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _insert_smart_session(image_path: str, original_name: Optional[str], spec: dict, facts: Optional[dict], status: str, record_id: Optional[int] = None) -> int:
    created_at = _now_iso()
    updated_at = created_at
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO smart_sessions (image_path, original_name, spec_json, facts_json, template_selected, template_candidates_json, status, record_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_path,
                original_name,
                _json_dumps(spec or {}),
                _json_dumps(facts or {}) if facts else None,
                None,
                None,
                status,
                record_id,
                created_at,
                updated_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _update_smart_session(session_id: int, spec: Optional[dict] = None, facts: Optional[dict] = None, template_selected: Optional[str] = None, template_candidates: Optional[list] = None, status: Optional[str] = None, record_id: Optional[int] = None) -> None:
    fields = []
    vals = []
    if spec is not None:
        fields.append("spec_json = ?")
        vals.append(_json_dumps(spec or {}))
    if facts is not None:
        fields.append("facts_json = ?")
        vals.append(_json_dumps(facts or {}))
    if template_selected is not None:
        fields.append("template_selected = ?")
        vals.append(template_selected)
    if template_candidates is not None:
        fields.append("template_candidates_json = ?")
        vals.append(_json_dumps(template_candidates or []))
    if status is not None:
        fields.append("status = ?")
        vals.append(status)
    if record_id is not None:
        fields.append("record_id = ?")
        vals.append(record_id)
    fields.append("updated_at = ?")
    vals.append(_now_iso())
    vals.append(session_id)
    with _get_conn() as conn:
        conn.execute(f"UPDATE smart_sessions SET {', '.join(fields)} WHERE id = ?", tuple(vals))
        conn.commit()


def _get_smart_session(session_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, image_path, original_name, spec_json, facts_json, template_selected, template_candidates_json, status, record_id, created_at, updated_at
            FROM smart_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "image_path": row["image_path"],
        "original_name": row["original_name"],
        "spec": _json_loads(row["spec_json"], {}),
        "facts": _json_loads(row["facts_json"], None),
        "template_selected": row["template_selected"],
        "template_candidates": _json_loads(row["template_candidates_json"], []),
        "status": row["status"],
        "record_id": row["record_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _add_smart_session_message(session_id: int, role: str, content: str) -> None:
    created_at = _now_iso()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO smart_session_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, created_at),
        )
        conn.commit()


def _list_smart_session_messages(session_id: int, limit: int = 50) -> List[dict]:
    limit = max(1, min(int(limit or 50), 200))
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM smart_session_messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [
        {"id": int(r["id"]), "session_id": int(r["session_id"]), "role": r["role"], "content": r["content"], "created_at": r["created_at"]}
        for r in rows
    ]


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


def _spec_to_plan_items(spec: dict, facts: dict) -> List[dict]:
    items = []
    
    # 1. 基础画质优化建议
    quality = facts.get("quality", {})
    if quality.get("light_issue"):
        items.append({
            "id": "item_light",
            "problem": quality["light_issue"],
            "solution": "应用智能补光与对比度增强",
            "category": "画质增强",
            "checked": True
        })
    if quality.get("color_issue"):
        items.append({
            "id": "item_color",
            "problem": quality["color_issue"],
            "solution": "执行全局色彩平衡与饱和度映射",
            "category": "色彩优化",
            "checked": True
        })
    if quality.get("sharpness_issue"):
        items.append({
            "id": "item_sharp",
            "problem": quality["sharpness_issue"],
            "solution": "进行超分辨率锐化与纹理细节恢复",
            "category": "细节修复",
            "checked": True
        })
    if quality.get("composition_issue"):
        items.append({
            "id": "item_comp",
            "problem": quality["composition_issue"],
            "solution": "优化构图布局与视觉重心引导",
            "category": "构图优化",
            "checked": True
        })
    if quality.get("background_issue"):
        items.append({
            "id": "item_bg",
            "problem": quality["background_issue"],
            "solution": "简化背景干扰并增强空间层次感",
            "category": "背景处理",
            "checked": True
        })
    if quality.get("local_defects") and quality["local_defects"] != "无明显瑕疵或噪点":
        items.append({
            "id": "item_defect",
            "problem": quality["local_defects"],
            "solution": "执行局部瑕疵修复与降噪处理",
            "category": "修复细节",
            "checked": True
        })
        
    # 3. 模板特定的建议
    task_type = spec.get("task_type")
    if task_type == "text_design":
        items.append({
            "id": "item_text",
            "problem": "包含排版文字需求",
            "solution": "应用智能文本布局与字体设计",
            "category": "排版设计",
            "checked": True
        })
    elif task_type == "sticker_icon":
        items.append({
            "id": "item_sticker",
            "problem": "贴纸/图标需求",
            "solution": "执行主体抠图与透明背景转换",
            "category": "素材制作",
            "checked": True
        })

    # 4. 滤镜建议 (从 facts 中获取，如果有的话)
    fr = facts.get("filter_recommendations") or {}
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
            "problem": "探索艺术滤镜风格",
            "solution": primary.get("description") or "Apply Artistic Filter",
            "engine": "Filter",
            "category": "风格滤镜",
            "type": "adjustment",
            "checked": False,
            "options": options,
        })

    return items


def _parse_ui_to_plan_items(ui: dict) -> List[dict]:
    items = []
    prof_analysis = ui.get("professional_analysis") or []
    
    # 检测是否包含“方案”或“选项”类的内容，如果是，则可能是一组互斥选项
    has_options = any(("方案" in (p.get("problem") or "") or "选项" in (p.get("problem") or "")) for p in prof_analysis)
    
    for idx, p in enumerate(prof_analysis):
        # 优先使用 AI 返回的 checked 状态（如果存在）
        # 否则如果是选项模式，默认只选中第一个
        ai_checked = p.get("checked")
        problem_text = p.get("problem") or ""
        is_option = "方案" in problem_text or "选项" in problem_text
        
        category = p.get("category") or "发现问题"
        if is_option:
            category = "可选方案"
        
        if ai_checked is not None:
            checked = bool(ai_checked)
        elif has_options and is_option:
            checked = (idx == 0) # 仅第一个方案默认选中
        else:
            checked = True
            
        items.append({
            "id": p.get("id") or str(idx + 1),
            "problem": problem_text,
            "solution": p.get("solution") or "",
            "engine": p.get("engine") or "Analysis",
            "category": category,
            "type": "generative" if (p.get("type") == "generative") else "adjustment",
            "checked": checked,
            "isOption": is_option,
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
            "problem": "探索艺术滤镜风格",
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

def analyze_image_with_qwen3_vl_plus(image_path: str, user_prompt: str = "", verbose: bool = True, stream_output: bool = True, enable_thinking: bool = False):
    prompt_text = get_enhanced_prompt(user_prompt)
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
        "model": "qwen3-vl-flash",
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

def _encode_image_to_data_url(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError("Unsupported image type")
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


_ASPECT_RATIOS = [
    ("1:1", 1.0),
    ("4:3", 4 / 3),
    ("3:4", 3 / 4),
    ("16:9", 16 / 9),
    ("9:16", 9 / 16),
    ("5:4", 5 / 4),
    ("4:5", 4 / 5),
    ("3:2", 3 / 2),
    ("2:3", 2 / 3),
    ("21:9", 21 / 9),
]


def _best_aspect_ratio(w: int, h: int) -> str:
    try:
        w = int(w or 1)
        h = int(h or 1)
        r = w / max(1, h)
        best = min(_ASPECT_RATIOS, key=lambda x: abs(x[1] - r))
        return best[0]
    except Exception:
        return "1:1"


def _extract_image_facts_from_ui(ui: Optional[dict]) -> dict:
    if not isinstance(ui, dict):
        return {}
    basic = ui.get("photo_basic_info") or {}
    q = ui.get("photo_quality_analysis") or {}
    try:
        face_count = basic.get("face_count")
        if isinstance(face_count, str) and face_count.strip().isdigit():
            face_count = int(face_count.strip())
        elif isinstance(face_count, (int, float)):
            face_count = int(face_count)
        else:
            face_count = None
    except Exception:
        face_count = None
    return {
        "photo_type": basic.get("photo_type"),
        "scene_type": basic.get("scene_type"),
        "main_subject": basic.get("main_subject"),
        "face_count": face_count,
        "quality": {
            "light_issue": q.get("light_issue"),
            "color_issue": q.get("color_issue"),
            "sharpness_issue": q.get("sharpness_issue"),
            "composition_issue": q.get("composition_issue"),
            "background_issue": q.get("background_issue"),
            "local_defects": q.get("local_defects"),
        },
    }


def _analyze_image_facts_best_effort(image_path: str, user_prompt: str = "") -> dict:
    facts: dict = {}
    try:
        from PIL import Image as _Image
        img = _Image.open(image_path)
        w, h = img.size
        facts.update(
            {
                "width": int(w),
                "height": int(h),
                "orientation": "landscape" if w >= h else "portrait",
                "aspect_ratio": _best_aspect_ratio(w, h),
            }
        )
    except Exception:
        pass
    try:
        if os.getenv("DASHSCOPE_API_KEY"):
            result = analyze_image_with_qwen3_vl_plus(image_path, user_prompt=user_prompt or "", stream_output=False, enable_thinking=False)
            if isinstance(result, dict):
                ui = result.get("ui_analysis")
                ui_facts = _extract_image_facts_from_ui(ui if isinstance(ui, dict) else None)
                facts.update(ui_facts)
                facts["analysis_summary"] = sanitize_summary_ui((ui or {}).get("summary_ui") if isinstance(ui, dict) else "")
                if isinstance(ui, dict) and ui.get("filter_recommendations"):
                    facts["filter_recommendations"] = ui.get("filter_recommendations")
    except Exception as exc:
        logger.info("smart_session analyze fallback: %s", exc)
    return facts


def _deep_merge(dst: dict, patch: dict) -> dict:
    if not isinstance(dst, dict):
        dst = {}
    if not isinstance(patch, dict):
        return dst
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            dst[k] = _deep_merge(dst.get(k) or {}, v)
        else:
            dst[k] = v
    return dst


def _default_spec(facts: Optional[dict], user_text: str) -> dict:
    t = (user_text or "").lower()
    face_count = (facts or {}).get("face_count")
    subject = None
    if isinstance(face_count, int) and face_count > 0:
        subject = "portrait" if face_count == 1 else "group"
    # 从文本识别任务类型
    if any(x in t for x in ["logo", "海报", "宣传", "封面", "标题", "排版", "字体", "文字"]):
        task_type = "text_design"
    elif any(x in t for x in ["贴纸", "sticker", "icon", "图标", "透明背景", "transparent"]):
        task_type = "sticker_icon"
    elif any(x in t for x in ["电商", "主图", "白底", "棚拍", "product"]):
        task_type = "product_shot"
    elif any(x in t for x in ["风景", "天空", "山", "海", "landscape"]):
        task_type = "landscape_enhance"
    # 如果文本没有明确意图，则从 facts 识别
    elif facts:
        photo_type = str(facts.get("photo_type") or "").lower()
        scene_type = str(facts.get("scene_type") or "").lower()
        main_subject = str(facts.get("main_subject") or "").lower()
        
        if any(x in photo_type or x in scene_type or x in main_subject for x in ["风景", "自然", "风光", "山水", "户外", "landscape", "nature", "scenery", "mountain", "sea", "sky"]):
            task_type = "landscape_enhance"
        elif any(x in photo_type or x in main_subject for x in ["人像", "人物", "portrait", "person", "human", "face"]):
            task_type = "photoreal_portrait"
        elif any(x in photo_type or x in main_subject for x in ["商品", "电商", "product", "item", "object"]):
            task_type = "product_shot"
        else:
            task_type = "photo_retouch"
    else:
        task_type = "photo_retouch"
    spec = {
        "task_type": task_type,
        "subject": subject,
        "faithfulness": "faithful" if task_type in {"photo_retouch", "landscape_enhance", "product_shot"} else "creative",
        "must_keep": {
            "identity": True if subject in {"portrait", "group"} else None,
            "composition": True,
            "text_content": True if task_type == "text_design" else None,
        },
        "style": {
            "preset": None,
        },
        "text_overlay": {
            "content": None,
            "font_style": None,
            "layout": None,
            "language": None,
        },
        "output": {
            "aspect_ratio": (facts or {}).get("aspect_ratio"),
            "resolution": None,
            "negative_space": None,
            "background": None,
        },
        "edits": {
            "instruction": (user_text or "").strip() or None,
        },
    }
    return spec


def _route_templates(spec: dict, facts: Optional[dict]) -> tuple[str, list]:
    spec = spec or {}
    facts = facts or {}
    task_type = spec.get("task_type")
    text_content = (spec.get("text_overlay") or {}).get("content")
    out = spec.get("output") or {}
    bg = out.get("background")
    neg = out.get("negative_space")
    subject = spec.get("subject") or facts.get("main_subject")
    
    # 额外从 facts 中提取关键特征
    photo_type = facts.get("photo_type", "")
    scene_type = facts.get("scene_type", "")
    
    candidates = []

    def add(name: str, score: float, reason: str):
        candidates.append({"template": name, "score": float(score), "reason": reason})

    # 1. 文字设计模板
    if task_type == "text_design" or (isinstance(text_content, str) and text_content.strip()):
        add("text_design", 0.95, "包含文字/排版需求")
    
    # 2. 贴纸/图标模板
    if task_type == "sticker_icon" or (isinstance(bg, str) and "transparent" in bg.lower()):
        add("sticker_icon", 0.9, "贴纸/图标或透明背景")
        
    # 3. 电商/产品模板
    if task_type == "product_shot" or "商品" in photo_type or "电商" in photo_type:
        add("product_shot", 0.88, "电商/产品拍摄场景")
        
    # 4. 留白构图模板
    if task_type == "negative_space" or neg:
        add("negative_space", 0.86, "明确的留白构图需求")
        
    # 5. 风景增强模板
    is_landscape = (
        task_type == "landscape_enhance" or 
        subject in {"landscape", "nature", "scenery", "mountain", "sea", "ocean", "forest"} or 
        any(k in str(photo_type).lower() for k in ["风景", "自然", "风光", "山水", "户外", "landscape", "nature", "scenery"]) or
        any(k in str(scene_type).lower() for k in ["公园", "山", "海", "天空", "建筑", "城市", "park", "mountain", "sea", "sky", "building", "city", "outdoor"])
    )
    if is_landscape:
        add("landscape_enhance", 0.92, "风景、建筑或自然风光")
        
    # 6. 写实人像模板
    face_count = facts.get("face_count", 0)
    is_portrait = subject in {"portrait", "group"} or face_count > 0 or "人像" in photo_type or "人物" in photo_type
    if is_portrait:
        add("photoreal_portrait", 0.88, "检测到人物主体")

    # 默认兜底
    add("photo_retouch", 0.6, "通用修图优化")

    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = candidates[0]["template"] if candidates else "photo_retouch"
    return selected, candidates


def _compile_prompt(spec: dict, facts: Optional[dict], template_selected: str) -> tuple[str, dict]:
    spec = spec or {}
    facts = facts or {}
    out = spec.get("output") or {}
    image_config = {}
    if out.get("aspect_ratio"):
        image_config["aspectRatio"] = out.get("aspect_ratio")
    if out.get("resolution"):
        image_config["imageSize"] = out.get("resolution")

    must_keep = spec.get("must_keep") or {}
    edits = spec.get("edits") or {}
    style = spec.get("style") or {}
    text_overlay = spec.get("text_overlay") or {}

    lines: list[str] = []

    if template_selected == "text_design":
        lines.append("[Task]\nDesign a clean, professional visual with accurate text rendering.")
    elif template_selected == "sticker_icon":
        lines.append("[Task]\nCreate a clean sticker/icon style rendition based on the provided image.")
    elif template_selected == "product_shot":
        lines.append("[Task]\nCreate a high-end, studio product photograph based on the provided image.")
    elif template_selected == "negative_space":
        lines.append("[Task]\nCreate a minimalist composition with intentional negative space.")
    elif template_selected == "landscape_enhance":
        lines.append("[Task]\nEnhance this landscape photo naturally and realistically.")
    elif template_selected == "photoreal_portrait":
        lines.append("[Task]\nPhotorealistic portrait retouching with natural results.")
    else:
        lines.append("[Task]\nFaithful photo restoration and enhancement.")

    lines.append(
        "[Standard Quality Requirements]\n"
        "Restore this image to stunning quality, ultra-high detail, and exceptional clarity. "
        "Apply advanced restoration techniques to eliminate noise, artifacts, and any imperfections. "
        "Optimize lighting to appear natural, balanced, and dynamic, enhancing depth and textures without overexposed highlights or excessively dark shadows. "
        "Colors should be meticulously restored to achieve a vibrant, rich, and harmonious aesthetic, characteristic of leading design magazines. "
        "Even if the original is black and white or severely faded, intelligently recolor and enhance it to meet this benchmark standard, "
        "with deep blacks, clean whites, and rich, realistic tones. "
        "The final image should appear as though captured with a high-end camera and professionally post-processed, possessing maximum depth and realism."
    )

    delta_lines = []
    user_instruction = edits.get("instruction")
    if isinstance(user_instruction, str) and user_instruction.strip():
        delta_lines.append(user_instruction.strip())
    if template_selected in {"photo_retouch", "photoreal_portrait", "product_shot", "landscape_enhance"}:
        delta_lines.extend(
            [
                "Remove noise, compression artifacts, and imperfections.",
                "Fix exposure and white balance to look natural.",
                "Recover detail without oversharpening; keep realistic texture.",
            ]
        )
    if template_selected == "product_shot":
        delta_lines.append("Use a clean background suitable for ecommerce, with realistic soft shadows.")
    if template_selected == "negative_space":
        neg = out.get("negative_space")
        if isinstance(neg, str) and neg.strip():
            delta_lines.append(f"Place the main subject to create negative space at: {neg.strip()}.")
        else:
            delta_lines.append("Place the main subject to create generous negative space for overlay text.")
    if template_selected == "sticker_icon":
        bg = out.get("background") or "white"
        delta_lines.append(f"Sticker style with bold, clean outlines and simple cel-shading. Background must be {bg}.")
    if template_selected == "text_design":
        content = text_overlay.get("content")
        if isinstance(content, str) and content.strip():
            delta_lines.append(f'Render the exact text: "{content.strip()}".')
        font_style = text_overlay.get("font_style")
        if isinstance(font_style, str) and font_style.strip():
            delta_lines.append(f"Font style: {font_style.strip()}.")
        layout = text_overlay.get("layout")
        if isinstance(layout, str) and layout.strip():
            delta_lines.append(f"Layout: {layout.strip()}.")
    if delta_lines:
        lines.append("[Edit]\n" + "\n".join(delta_lines))

    style_lines = []
    preset = style.get("preset")
    if isinstance(preset, str) and preset.strip():
        style_lines.append(f"Overall style: {preset.strip()}.")
    if template_selected == "photoreal_portrait":
        style_lines.append("Use portrait photography aesthetics: natural skin texture, gentle contrast, soft background separation.")
    if template_selected == "product_shot":
        style_lines.append("Lighting: three-point softbox setup. Camera angle: slightly elevated 45-degree. Ultra-realistic.")
    if template_selected == "landscape_enhance":
        style_lines.append("Enhance depth and atmosphere subtly; keep colors natural and believable.")
    if style_lines:
        lines.append("[Style]\n" + "\n".join(style_lines))

    avoid_lines = [
        "No hallucinated details or extra objects unless requested.",
        "No plastic skin, no oversharpening halos, no excessive HDR.",
        "No random or misspelled text artifacts.",
        "Avoid unnatural saturation or color shifts.",
    ]
    lines.append("[Avoid]\n" + "\n".join(avoid_lines))

    prompt = "\n\n".join(lines).strip()
    return prompt, image_config


def _get_gemini_api_key() -> Optional[str]:
    return os.getenv("VISION_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _gemini_generate_content(model: str, contents: object, generation_config: Optional[dict] = None, tools: Optional[list] = None, timeout: int = 90) -> dict:
    api_key = _get_gemini_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing VISION_API_KEY/GEMINI_API_KEY for Gemini calls")
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    payload: dict = {"contents": contents} if isinstance(contents, list) else {"contents": [{"parts": [{"text": str(contents)}]}]}
    if generation_config:
        payload["generationConfig"] = generation_config
    if tools:
        payload["tools"] = tools
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Gemini error: {resp.text}")
    return resp.json()


def _extract_text_from_gemini(result: dict) -> str:
    try:
        cands = result.get("candidates") or []
        if not cands:
            return ""
        parts = (cands[0].get("content") or {}).get("parts") or []
        texts = []
        for p in parts:
            t = p.get("text")
            if isinstance(t, str) and t.strip():
                texts.append(t)
        return "\n".join(texts).strip()
    except Exception:
        return ""


def _llm_clarify_next(spec: dict, facts: Optional[dict], messages: List[dict], template_candidates: list) -> tuple[dict, list, Optional[str]]:
    model = os.getenv("SMART_LLM_MODEL", "gemini-2.0-flash")
    prompt_obj = {
        "facts": facts or {},
        "spec": spec or {},
        "templates_available": [
            {"id": "text_design", "desc": "包含文字、排版、海报设计需求"},
            {"id": "sticker_icon", "desc": "贴纸、图标、Logo，通常需要透明背景"},
            {"id": "product_shot", "desc": "电商产品图、商业摄影、白底图"},
            {"id": "landscape_enhance", "desc": "风景照美化、滤镜、细节增强"},
            {"id": "photoreal_portrait", "desc": "写实人像、写真、证件照美化"},
            {"id": "photo_retouch", "desc": "通用修图、消除笔、老照片修复"}
        ],
        "conversation": messages[-20:],
    }
    instruction = (
        "你是一个图片编辑意图澄清助手。你的目标是：\n"
        "1) 深入分析用户需求，更新 spec（意图规格）。\n"
        "   - **特别注意**：如果用户提出了具体的编辑指令（如：去掉某物、换个颜色、移动位置），必须将其记录在 spec 的 edits.instruction 中。如果已有指令，请根据新需求进行追加或合并。\n"
        "2) 引导式对话：如果用户意图模糊，或者你可以通过询问获得更好的生成效果，请务必提出 1-2 个针对性的问题。\n"
        "   - **特别注意**：如果 conversation 为空（用户只点了分析没说话），你必须基于图片事实主动发起第一次对话，询问用户想要达到的效果，并给出 2-3 个基于图片的具体建议选项。\n"
        "3) 精准路由：从 templates_available 中选择最匹配的一个。即使当前信息不完全，只要图片内容明确（如风景、人像、产品），就应优先选择对应的专业模板，而不是 photo_retouch。\n\n"
        "JSON 输出要求（严禁 Markdown）：\n"
        "{\n"
        '  \"spec_patch\": { \"task_type\": \"...\", \"subject\": \"...\", \"style\": {\"preset\": \"...\"}, ... },\n'
        '  \"questions\": [{\"id\":\"q1\",\"text\":\"针对性的提问\",\"choices\":[\"选项A\",\"选项B\"]}],\n'
        '  \"template_selected\": \"最匹配的模板ID\" \n'
        "}\n"
        "注意：\n"
        "- 优先路由：如果 facts 显示是风景，template_selected 必须是 landscape_enhance；如果是人，必须是 photoreal_portrait。\n"
        "- 提问策略：不要问废话。如果用户没说话，你的问题应该是：'我看到这是一张[图片描述]，您是想[针对性方案A]还是[针对性方案B]？'\n"
        "  - 例如风景照：'这张风景照的光影很美，您是想增强日落氛围，还是让天空更通透？'\n"
        "- spec_patch 尽量详细，利用 facts 中的信息填充细节。\n"
    )
    full_prompt = instruction + "\n\n" + json.dumps(prompt_obj, ensure_ascii=False)
    result = _gemini_generate_content(
        model=model,
        contents=[{"parts": [{"text": full_prompt}]}],
        generation_config={"temperature": 0.2, "maxOutputTokens": 600},
        timeout=90,
    )
    text = _extract_text_from_gemini(result)
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    obj = _json_loads(cleaned, {})
    patch = obj.get("spec_patch") if isinstance(obj, dict) else {}
    questions = obj.get("questions") if isinstance(obj, dict) else []
    template_selected = obj.get("template_selected") if isinstance(obj, dict) else None
    if not isinstance(patch, dict):
        patch = {}
    if not isinstance(questions, list):
        questions = []
    normalized_questions = []
    for i, q in enumerate(questions[:2]):
        if not isinstance(q, dict):
            continue
        qid = q.get("id") or f"q{i+1}"
        qtext = q.get("text") or q.get("question") or ""
        choices = q.get("choices") or q.get("options")
        if not isinstance(choices, list):
            choices = None
        if isinstance(qtext, str) and qtext.strip():
            normalized_questions.append({"id": str(qid), "text": qtext.strip(), "choices": choices})
    return patch, normalized_questions, template_selected if isinstance(template_selected, str) and template_selected.strip() else None


def _is_ready_to_render(spec: dict, template_selected: str) -> bool:
    spec = spec or {}
    if template_selected == "text_design":
        content = ((spec.get("text_overlay") or {}).get("content") or "")
        return bool(isinstance(content, str) and content.strip())
    if template_selected == "sticker_icon":
        bg = ((spec.get("output") or {}).get("background") or "")
        return bool(isinstance(bg, str) and bg.strip())
    if template_selected == "negative_space":
        neg = (spec.get("output") or {}).get("negative_space")
        return bool(neg)
    return True


def _infer_mime_from_filename(filename: str) -> str:
    ext = (Path(filename or "").suffix or "").lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    return "image/png"


def _gemini_image_edit_native(model: str, prompt_text: str, image_bytes: bytes, mime_type: str, aspect_ratio: Optional[str], resolution: Optional[str], timeout: int = 120) -> tuple[list[str], list[str], dict]:
    api_key = _get_gemini_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing VISION_API_KEY/GEMINI_API_KEY for Gemini calls")
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload_json: dict = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": mime_type, "data": img_b64}},
                ]
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    if aspect_ratio or resolution:
        image_config = {}
        if aspect_ratio:
            image_config["aspectRatio"] = aspect_ratio
        if resolution:
            image_config["imageSize"] = resolution
        payload_json["generationConfig"]["imageConfig"] = image_config
    resp = requests.post(url, json=payload_json, timeout=timeout)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Gemini image error: {resp.text}")
    result = resp.json()
    urls = []
    local_paths = []
    try:
        candidates = result.get("candidates") or []
        for cand in candidates:
            parts = (cand.get("content") or {}).get("parts") or []
            for part in parts:
                img_part = part.get("inline_data") or part.get("inlineData")
                if not img_part:
                    continue
                b64_out = img_part.get("data")
                if not b64_out:
                    continue
                out_bytes = base64.b64decode(b64_out)
                mime_out = img_part.get("mime_type") or img_part.get("mimeType") or "image/png"
                ext = ".png"
                if isinstance(mime_out, str) and ("jpeg" in mime_out or "jpg" in mime_out):
                    ext = ".jpg"
                out_path = _save_image_bytes(f"smart{ext}", out_bytes)
                local_paths.append(out_path)
                # Always use relative paths for static files to work with Vite proxy
                urls.append(f"/static/{Path(out_path).name}")
    except Exception as exc:
        logger.warning("smart_generate parse response failed: %s", exc)
    if not urls:
        if isinstance(result, dict) and result.get("promptFeedback", {}).get("blockReason"):
            raise HTTPException(status_code=400, detail=f"prompt blocked: {result['promptFeedback']['blockReason']}")
        raise HTTPException(status_code=400, detail="Gemini did not return any images")
    return urls, local_paths, result


async def magic_edit(
    image: UploadFile = File(...),
    mask: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    n: int = Form(1),
    size: str = Form(""),
    watermark: bool = Form(False),
    negative_prompt: str = Form(""),
    prompt_extend: bool = Form(True),
    aspect_ratio: Optional[str] = Form(None),  # 新增：比例参数
    resolution: Optional[str] = Form(None),    # 新增：分辨率参数
    step: Optional[int] = Form(None),          # 新增：步骤编号
):
    # 优先使用 VISION_API_KEY (Google Gemini OpenAI 兼容模式)
    vision_api_key = os.getenv("VISION_API_KEY")
    image_edit_endpoint = os.getenv("IMAGE_EDIT_ENDPOINT")
    model = os.getenv("IMAGE_EDIT_MODEL", "gemini-3-pro-image-preview")

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

        mask_data = None
        if mask:
            mask_bin = await mask.read()
            if mask_bin:
                try:
                    mask_img = _load_image_from_bytes(mask_bin, "mask.png")
                    mask_img = mask_img.resize(img.size) # 确保 Mask 与原图尺寸一致
                    mask_proc, _ = _pil_to_bytes(mask_img, "png")
                    mask_data = base64.b64encode(mask_proc).decode("utf-8")
                except Exception as e:
                    logger.warning("Failed to process mask: %s", e)

        urls = []
        local_paths = []

        # 如果是 OpenAI/Google 模式
        if vision_api_key:
            logger.info("使用 Google Gemini (Native/REST) 接口进行图片编辑: %s", model)
            
            base_url = image_edit_endpoint.replace("/openai/", "") if image_edit_endpoint else "https://generativelanguage.googleapis.com/v1beta"
            native_url = f"{base_url.rstrip('/')}/models/{model}:generateContent?key={vision_api_key}"
            
            # 组合基础提示词和用户指令
            final_prompt = f"[Standard Quality Requirements]\n{GEMINI_BASE_PROMPT}\n\n[User Specific Edit Instruction]\n{prompt}"
            if mask_data:
                final_prompt += "\n\nNote: A mask image is provided. The second image is the mask where white areas indicate where the edits should be applied. Please perform inpainting/editing in the white areas of the mask while keeping other parts unchanged."
            
            print("\n" + "="*50)
            print("FINAL PROMPT SENT TO GEMINI (MAGIC_EDIT):")
            print(final_prompt)
            print("="*50 + "\n")
            logger.info("FINAL PROMPT SENT TO GEMINI (MAGIC_EDIT): \n%s", final_prompt)

            # 构造请求体
            parts = [
                {"text": final_prompt},
                {
                    "inline_data": {
                        "mime_type": input_mime,
                        "data": img_data
                    }
                }
            ]
            if mask_data:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": mask_data
                    }
                })

            payload_json = {
                "contents": [{
                    "parts": parts
                }],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"]
                }
            }

            # 如果传入了比例或分辨率，加入到配置中
            if aspect_ratio or resolution:
                image_config = {}
                if aspect_ratio:
                    image_config["aspectRatio"] = aspect_ratio
                if resolution:
                    image_config["imageSize"] = resolution
                payload_json["generationConfig"]["imageConfig"] = image_config
            
            logger.info("发送请求到 Google Native API: %s (MIME: %s, Ratio: %s, Res: %s)", 
                        native_url, input_mime, aspect_ratio, resolution)
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
                                
                                # 文件名包含步骤信息
                                step_str = f"_step{step}" if step is not None else ""
                                out_filename = f"gen{step_str}{ext}"
                                out_path = _save_image_bytes(out_filename, out_bytes)
                                local_paths.append(out_path)
                                
                                # 转换为可以直接访问的 URL
                                # Always use relative paths for static files to work with Vite proxy
                                urls.append(f"/static/{Path(out_path).name}")
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
                    # Always use relative paths for static files to work with Vite proxy
                    served_urls = [f"/static/{Path(p).name}" for p in local_paths]
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
                messages = [{"role":"user","content":[{"type":"image_url","image_url":{"url":data_url}},{"type":"text","text":get_enhanced_prompt(prompt)}]}]
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
                    fallback_result = analyze_image_with_qwen3_vl_plus(tmp.name, user_prompt=prompt, stream_output=False, enable_thinking=True)
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

from backend.routers import analyze as analyze_router
from backend.routers import edit as edit_router
from backend.routers import media as media_router
from backend.routers import records as records_router
from backend.routers import smart as smart_router

app.include_router(records_router.router)
app.include_router(media_router.router)
app.include_router(analyze_router.router)
app.include_router(smart_router.router)
app.include_router(edit_router.router)

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
