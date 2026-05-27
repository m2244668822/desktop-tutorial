#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlparse


APP_DIR = Path(
    os.environ.get("CHAT_FRONTEND_APP_DIR", "/Users/user/.chat_frontend")
).expanduser()
HTML_PATH = Path(
    os.environ.get("CHAT_FRONTEND_HTML", str(APP_DIR / "chat.html"))
).expanduser()
UPLOAD_DIR = APP_DIR / "uploads"
ARCHIVE_DIR = APP_DIR / "archives"
PORT = int(os.environ.get("CHAT_SERVER_PORT", "5001"))
SOURCE_ROOT = Path(
    os.environ.get("CHAT_SOURCE_ROOT", str(Path(__file__).resolve().parents[1]))
).expanduser()
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
try:
    from core.task_board import task_items_payload, task_summary_payload
except Exception:
    def task_summary_payload(workspace_root):
        return {"ok": False, "status_counts": {"pending": 0, "running": 0, "completed": 0, "failed": 0}, "total": 0}

    def task_items_payload(workspace_root, *, status="", limit=30, compact=False):
        return {"ok": False, "items": [], "count": 0, "total": 0, "filter": status or "all"}
ENV_CANDIDATES = [
    Path(os.environ.get("CHAT_ENV_FILE", "")).expanduser(),
    SOURCE_ROOT / ".env",
    SOURCE_ROOT / "500" / "llama32-chat" / ".env",
    SOURCE_ROOT / "500" / "llama32-chat" / "config" / ".env",
]


AGENT_LABELS = {
    "dispatcher": "總管",
    "researcher": "研究學習中樞",
    "engineer": "工程師",
    "xiaobian": "小編",
    "proclaimer": "申言者",
    "whitehat": "帽子",
    "general": "通用助手",
}


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def html_bytes() -> bytes:
    text = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
    text = text.replace("{{ server_api_token | default('') }}", "")
    return text.encode("utf-8")


def safe_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._\-\u4e00-\u9fff]", "_", name or "upload")
    return name[:120] or "upload"


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path or not str(path) or (not path.exists()) or (not path.is_file()):
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        v = value.strip()
        if v and not v.startswith(("'", '"')) and "#" in v:
            v = v.split("#", 1)[0].rstrip()
        data[key.strip()] = v.strip('"').strip("'")
    return data


def _merge_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in ENV_CANDIDATES:
        file_data = _load_env_file(path)
        for k, v in file_data.items():
            if k not in merged:
                merged[k] = v
    for k in (
        "NVAPI_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "CHAT_PREFERRED_PROVIDER",
    ):
        if os.environ.get(k):
            merged[k] = os.environ[k]
    return merged


def _is_valid_key(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    low = v.lower()
    bad_tokens = ("placeholder", "your_", "_here", "replace_me", "changeme", "example")
    if any(t in low for t in bad_tokens):
        return False
    return len(v) >= 30


def _provider_status() -> dict[str, object]:
    env = _merge_env()
    nvidia_ok = _is_valid_key(env.get("NVAPI_API_KEY", ""))
    openai_ok = _is_valid_key(env.get("OPENAI_API_KEY", ""))
    gemini_ok = _is_valid_key(env.get("GEMINI_API_KEY", "")) or _is_valid_key(
        env.get("GOOGLE_API_KEY", "")
    )
    groq_ok = _is_valid_key(env.get("GROQ_API_KEY", ""))

    providers = [
        ("nvidia", "NVIDIA", nvidia_ok),
        ("openai", "OpenAI", openai_ok),
        ("gemini", "Gemini", gemini_ok),
        ("groq", "Groq", groq_ok),
    ]
    connected = [p[0] for p in providers if p[2]]

    preferred_env = (env.get("CHAT_PREFERRED_PROVIDER", "") or "").strip().lower()
    if preferred_env in connected:
        preferred = preferred_env
    elif connected:
        preferred = connected[0]
    else:
        preferred = "nvidia"

    catalog = []
    for key, label, ok in providers:
        tier = (
            "primary" if key == preferred and ok else ("enabled" if ok else "disabled")
        )
        catalog.append(
            {
                "key": key,
                "label": label,
                "visible": True,
                "classification": {"tier": tier},
            }
        )

    return {
        "chat_preferred_provider": preferred,
        "nvidia": nvidia_ok,
        "nvidia_key_configured": nvidia_ok,
        "openai": openai_ok,
        "openai_key_configured": openai_ok,
        "gemini": gemini_ok,
        "gemini_key_configured": gemini_ok,
        "groq": groq_ok,
        "groq_key_configured": groq_ok,
        "provider_catalog": catalog,
        "connected_count": len(connected),
        "total_count": len(providers),
    }


def _http_post_json(
    url: str, payload: dict, headers: dict[str, str], timeout: int = 45
) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_{exc.code}: {raw[:300]}")
    except Exception as exc:
        raise RuntimeError(str(exc))


def _extract_choice_text(data: dict) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                return "\n".join(parts).strip()
    return ""


def _build_system_prompt(agent_key: str, interaction_mode: str) -> str:
    label = AGENT_LABELS.get(agent_key, agent_key)
    mode = interaction_mode or "auto"
    return (
        f"你是 {label}，請以繁體中文回答。"
        f"保持實用、直接、可執行。當模式為 {mode} 時，優先給可落地步驟。"
    )


def _provider_order(env: dict[str, str]) -> list[str]:
    connected: list[str] = []
    if _is_valid_key(env.get("NVAPI_API_KEY", "")):
        connected.append("nvidia")
    if _is_valid_key(env.get("OPENAI_API_KEY", "")):
        connected.append("openai")
    if _is_valid_key(env.get("GROQ_API_KEY", "")):
        connected.append("groq")
    preferred = (env.get("CHAT_PREFERRED_PROVIDER", "") or "").strip().lower()
    if preferred in connected:
        connected.remove(preferred)
        connected.insert(0, preferred)
    return connected


def _chat_with_openai(
    env: dict[str, str], message: str, system_prompt: str
) -> tuple[str, str]:
    model = (env.get("OPENAI_MODEL") or "gpt-4o").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0.35,
    }
    data = _http_post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        {"Authorization": f"Bearer {env.get('OPENAI_API_KEY', '').strip()}"},
    )
    text = _extract_choice_text(data)
    if not text:
        raise RuntimeError("openai_empty_reply")
    return text, model


def _chat_with_nvidia(
    env: dict[str, str], message: str, system_prompt: str
) -> tuple[str, str]:
    model = (env.get("NVIDIA_MODEL") or "meta/llama-3.1-405b-instruct").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0.35,
        "max_tokens": 1200,
    }
    data = _http_post_json(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        payload,
        {"Authorization": f"Bearer {env.get('NVAPI_API_KEY', '').strip()}"},
    )
    text = _extract_choice_text(data)
    if not text:
        raise RuntimeError("nvidia_empty_reply")
    return text, model


def _chat_with_groq(
    env: dict[str, str], message: str, system_prompt: str
) -> tuple[str, str]:
    model = (env.get("GROQ_MODEL") or "llama-3.1-8b-instant").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0.35,
    }
    data = _http_post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        payload,
        {"Authorization": f"Bearer {env.get('GROQ_API_KEY', '').strip()}"},
    )
    text = _extract_choice_text(data)
    if not text:
        raise RuntimeError("groq_empty_reply")
    return text, model


def _generate_model_reply(
    message: str, agent_key: str, interaction_mode: str
) -> tuple[str, str, str]:
    env = _merge_env()
    provider_order = _provider_order(env)
    system_prompt = _build_system_prompt(agent_key, interaction_mode)
    errors: list[str] = []
    for provider in provider_order:
        try:
            if provider == "openai":
                text, model = _chat_with_openai(env, message, system_prompt)
            elif provider == "nvidia":
                text, model = _chat_with_nvidia(env, message, system_prompt)
            elif provider == "groq":
                text, model = _chat_with_groq(env, message, system_prompt)
            else:
                continue
            return text, provider, model
        except Exception as exc:
            errors.append(f"{provider}:{exc}")
            continue
    if errors:
        raise RuntimeError("; ".join(errors[:3]))
    raise RuntimeError("no_provider_key")


class Handler(BaseHTTPRequestHandler):
    server_version = "LightChatFrontend/1.0"

    def log_message(self, fmt: str, *args):
        return

    def send_bytes(self, body: bytes, content_type: str, status: int = HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: object, status: int = HTTPStatus.OK):
        self.send_bytes(json_bytes(payload), "application/json; charset=utf-8", status)

    def read_json(self) -> dict:
        raw_len = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(raw_len) if raw_len else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/chat", "/index.html"}:
            self.send_bytes(html_bytes(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self.send_json(
                {"ok": True, "mode": "lightweight", "time": datetime.now().isoformat()}
            )
            return
        if path == "/status":
            payload = {"ok": True, "mode": "lightweight_frontend"}
            payload.update(_provider_status())
            self.send_json(payload)
            return
        if path == "/api/orchestrator/status":
            self.send_json(
                {
                    "ok": True,
                    "kal": {"running": True},
                    "counters": {"pending_goals": 0, "completed_goals": 0},
                    "components": {
                        "distiller": True,
                        "validator": True,
                        "brave_search": False,
                    },
                }
            )
            return
        if path == "/trace/learning-status":
            self.send_json({"ok": True, "cycles": 0, "pending": 0, "recent": []})
            return
        if path == "/agent/tasks/summary":
            self.send_json(task_summary_payload(SOURCE_ROOT))
            return
        if path == "/agent/tasks":
            qs = parse_qs(parsed.query or "")
            try:
                limit = int((qs.get("limit") or ["30"])[0] or 30)
            except Exception:
                limit = 30
            status_filter = (qs.get("status") or [""])[0]
            compact = (qs.get("compact") or [""])[0].lower() in {"1", "true", "yes", "on"}
            self.send_json(task_items_payload(SOURCE_ROOT, status=status_filter, limit=limit, compact=compact))
            return
        if path == "/history":
            self.send_json([])
            return
        if path == "/archive/list":
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            files = []
            for item in sorted(
                ARCHIVE_DIR.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            ):
                files.append(
                    {"name": item.name, "size_kb": round(item.stat().st_size / 1024, 1)}
                )
            self.send_json({"files": files})
            return
        if path.startswith("/uploads/"):
            name = safe_name(path.rsplit("/", 1)[-1])
            target = (UPLOAD_DIR / name).resolve()
            try:
                target.relative_to(UPLOAD_DIR.resolve())
            except Exception:
                self.send_bytes(b"Forbidden", "text/plain", HTTPStatus.FORBIDDEN)
                return
            if not target.exists():
                self.send_bytes(b"Not Found", "text/plain", HTTPStatus.NOT_FOUND)
                return
            ctype = "application/octet-stream"
            if target.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                ctype = "image/" + (
                    "jpeg"
                    if target.suffix.lower() in {".jpg", ".jpeg"}
                    else target.suffix.lower().strip(".")
                )
            self.send_bytes(target.read_bytes(), ctype)
            return
        self.send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self.read_json()
        if path == "/chat/agent":
            message = str(payload.get("message", "")).strip()
            agent_key = str(payload.get("agent", "dispatcher")).strip() or "dispatcher"
            label = AGENT_LABELS.get(agent_key, agent_key)
            if not message:
                reply = f"【{label}】已連線。請輸入訊息。"
                provider_used = "lightweight"
                model_used = "lightweight-local"
            else:
                try:
                    reply, provider_used, model_used = _generate_model_reply(
                        message,
                        agent_key,
                        str(payload.get("interaction_mode", "auto")),
                    )
                except Exception as exc:
                    reply = (
                        f"【{label}】目前雲端模型暫時不可用，請稍後再試。\n"
                        f"診斷：{str(exc)[:240]}"
                    )
                    provider_used = "fallback"
                    model_used = "lightweight-fallback"
            self.send_json(
                {
                    "reply": reply,
                    "agent": agent_key,
                    "provider": provider_used,
                    "model": model_used,
                    "interaction_mode": payload.get("interaction_mode", "auto"),
                    "response_time": 0.01,
                    "quick_replies": [
                        {"id": "status_check", "text": "狀態查詢", "category": "系統"},
                        {
                            "id": "engineer_optimize",
                            "text": "系統優化",
                            "category": "工程",
                        },
                        {
                            "id": "researcher_search",
                            "text": "搜尋開源框架",
                            "category": "研究",
                        },
                    ],
                }
            )
            return
        if path == "/api/upload_file":
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            filename = safe_name(str(payload.get("filename", "upload.bin")))
            raw_b64 = str(payload.get("data", ""))
            try:
                raw = base64.b64decode(raw_b64)
            except Exception:
                raw = b""
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            final = (
                f"{Path(filename).stem[:40]}_{stamp}{Path(filename).suffix or '.bin'}"
            )
            (UPLOAD_DIR / final).write_bytes(raw)
            self.send_json({"ok": True, "filename": final, "url": f"/uploads/{final}"})
            return
        if path == "/archive/export":
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            target = (
                ARCHIVE_DIR / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            target.write_text(
                json.dumps(
                    {"mode": "lightweight", "created_at": datetime.now().isoformat()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.send_json(
                {
                    "ok": True,
                    "records": 0,
                    "size_kb": round(target.stat().st_size / 1024, 1),
                    "file": str(target),
                }
            )
            return
        if path == "/archive/cleanup":
            self.send_json(
                {"ok": True, "deleted_records": 0, "merged_archived_records": 0}
            )
            return
        self.send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)


def main() -> int:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not HTML_PATH.exists():
        raise SystemExit(f"Missing HTML file: {HTML_PATH}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Lightweight chat frontend serving http://127.0.0.1:{PORT}/", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
