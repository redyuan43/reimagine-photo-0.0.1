import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("API_AUTH_DISABLED", "1")
    for name in list(sys.modules.keys()):
        if name == "server" or name.startswith("backend.routers"):
            del sys.modules[name]
    import server
    return TestClient(server.app)


def _png_file_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), (255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_openapi_smoke(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "paths" in data
    paths = data["paths"]
    assert "/preview" in paths
    assert "/convert" in paths
    assert "/proxy_image" in paths
    assert "/analyze" in paths
    assert "/analyze_stream" in paths
    assert "/smart/start" in paths
    assert "/smart/answer" in paths
    assert "/smart/generate" in paths
    assert "/magic_edit" in paths


def test_preview_returns_image(client: TestClient):
    png = _png_file_bytes()
    resp = client.post("/preview", files={"image": ("t.png", png, "image/png")})
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("image/")
    assert len(resp.content) > 10


def test_convert_returns_blob(client: TestClient):
    png = _png_file_bytes()
    resp = client.post(
        "/convert",
        files={"image": ("t.png", png, "image/png")},
        data={"format": "jpeg", "quality": "80", "compression": "6", "color": "RGB"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("image/")
    assert len(resp.content) > 10


def test_proxy_image_rejects_non_http(client: TestClient):
    resp = client.get("/proxy_image", params={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


def test_records_list(client: TestClient):
    resp = client.get("/records")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data


def test_analyze_returns_items(client: TestClient, monkeypatch):
    import server

    def fake_analyze(*_args, **_kwargs):
        return {
            "ui_analysis": {
                "professional_analysis": [
                    {
                        "id": "p1",
                        "problem": "contrast low",
                        "solution": "increase contrast",
                        "engine": "Analysis",
                        "category": "画质增强",
                        "type": "adjustment",
                        "checked": True,
                    }
                ],
                "summary_ui": "ok",
            }
        }

    monkeypatch.setattr(server, "analyze_image_with_qwen3_vl_plus", fake_analyze)

    png = _png_file_bytes()
    resp = client.post("/analyze", files={"image": ("t.png", png, "image/png")}, data={"prompt": "x"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("analysis"), list)
    assert len(data["analysis"]) >= 1
    assert isinstance(data.get("summary"), str)


def test_analyze_stream_fallback_sends_final(client: TestClient, monkeypatch):
    import server

    def fake_analyze(*_args, **_kwargs):
        return {
            "ui_analysis": {
                "professional_analysis": [
                    {
                        "id": "p1",
                        "problem": "noise",
                        "solution": "denoise",
                        "engine": "Analysis",
                        "category": "画质增强",
                        "type": "adjustment",
                        "checked": True,
                    }
                ],
                "summary_ui": "done",
            }
        }

    monkeypatch.setattr(server, "analyze_image_with_qwen3_vl_plus", fake_analyze)
    monkeypatch.setitem(sys.modules, "openai", None)

    png = _png_file_bytes()
    resp = client.post("/analyze_stream", files={"image": ("t.png", png, "image/png")}, data={"prompt": "x"})
    assert resp.status_code == 200
    assert "text/event-stream" in (resp.headers.get("content-type") or "")
    body = resp.text
    assert "data:" in body
    assert "\"type\": \"final\"" in body or "\"type\":\"final\"" in body


def test_magic_edit_returns_urls_via_stubbed_model(client: TestClient, monkeypatch, tmp_path):
    import server

    class _FakeResp:
        status_code = 200
        output = type(
            "O",
            (),
            {
                "choices": [
                    type(
                        "C",
                        (),
                        {"message": type("M", (), {"content": [{"image": "http://example.invalid/img.png"}]})()},
                    )()
                ]
            },
        )()

    class _FakeMMC:
        @staticmethod
        def call(**_kwargs):
            return _FakeResp()

    def fake_download_and_save_image(_url: str):
        p = Path(server.IMAGES_DIR) / "magic_out.png"
        p.write_bytes(_png_file_bytes())
        return str(p)

    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.setattr(server, "MultiModalConversation", _FakeMMC)
    monkeypatch.setattr(server, "_download_and_save_image", fake_download_and_save_image)

    png = _png_file_bytes()
    resp = client.post("/magic_edit", files={"image": ("t.png", png, "image/png")}, data={"prompt": "x"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("urls"), list)
    assert len(data["urls"]) >= 1
    assert "/static/" in data["urls"][0]


def test_smart_flow_start_answer_generate(client: TestClient, monkeypatch):
    import server

    monkeypatch.setattr(server, "_get_gemini_api_key", lambda: None)
    monkeypatch.setattr(server, "_analyze_image_facts_best_effort", lambda *_a, **_k: {})
    monkeypatch.setattr(server, "_default_spec", lambda *_a, **_k: {})
    monkeypatch.setattr(server, "_route_templates", lambda *_a, **_k: ("photo_retouch", [{"template": "photo_retouch"}]))
    monkeypatch.setattr(server, "_is_ready_to_render", lambda *_a, **_k: True)
    monkeypatch.setattr(server, "_compile_prompt", lambda *_a, **_k: ("prompt", {"aspectRatio": None, "imageSize": None}))

    def fake_image_edit_native(**_kwargs):
        p = Path(server.IMAGES_DIR) / "smart_out.png"
        p.write_bytes(_png_file_bytes())
        return (["http://localhost:8000/static/smart_out.png"], [str(p)], {"ok": True})

    monkeypatch.setattr(server, "_gemini_image_edit_native", fake_image_edit_native)

    png = _png_file_bytes()
    resp_start = client.post("/smart/start", files={"image": ("t.png", png, "image/png")}, data={"message": "x"})
    assert resp_start.status_code == 200
    start_data = resp_start.json()
    session_id = start_data["session_id"]

    resp_answer = client.post("/smart/answer", json={"session_id": session_id, "message": "ok"})
    assert resp_answer.status_code == 200
    answer_data = resp_answer.json()
    assert answer_data["session_id"] == session_id

    resp_gen = client.post("/smart/generate", json={"session_id": session_id})
    assert resp_gen.status_code == 200
    gen_data = resp_gen.json()
    assert gen_data["session_id"] == session_id
    assert isinstance(gen_data.get("urls"), list)
    assert len(gen_data["urls"]) >= 1
