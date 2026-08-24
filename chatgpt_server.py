from flask import Flask, request, jsonify, render_template, send_from_directory
import os
from dotenv import load_dotenv
import json
import time
import logging
import re
import threading
import importlib
import importlib.util
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from ipaddress import ip_address, ip_network
import base64
import hashlib
import hmac
import secrets
import uuid
import shlex
import subprocess
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from werkzeug.utils import secure_filename
import ollama
import requests
from agents import (
    build_agent_prompt,
    extract_signal_terms,
    get_agent_spec,
    list_agent_specs,
    serialize_agent_spec,
)

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("APP_DATA_ROOT", str(BASE_DIR))).expanduser().resolve()
INSTANCE_DIR = Path(os.getenv("APP_INSTANCE_DIR", str(DATA_ROOT / "instance"))).expanduser().resolve()
UPLOADS_DIR = Path(os.getenv("APP_UPLOAD_DIR", str(DATA_ROOT / "uploads"))).expanduser().resolve()
LOGS_DIR = Path(os.getenv("APP_LOG_DIR", str(DATA_ROOT / "logs"))).expanduser().resolve()
ARCHIVE_DIR = Path(os.getenv("APP_ARCHIVE_DIR", str(DATA_ROOT / "archives"))).expanduser().resolve()
DATABASE_PATH = Path(os.getenv("APP_DATABASE_PATH", str(INSTANCE_DIR / "chat_history.db"))).expanduser().resolve()


def _normalize_database_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    # Backward compatibility: "postgres://" -> "postgresql+psycopg://"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    # Prefer psycopg v3 explicitly when caller provides "postgresql://..."
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _redact_database_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password is not None:
                auth += ":***"
            auth += "@"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        masked = parsed._replace(netloc=f"{auth}{host}{port}")
        return masked.geturl()
    except Exception:
        return url


APP_DATABASE_URL = os.getenv("APP_DATABASE_URL", "").strip()
ACTIVE_DATABASE_URI = _normalize_database_url(APP_DATABASE_URL) or f"sqlite:///{DATABASE_PATH}"
ACTIVE_DATABASE_URI_REDACTED = _redact_database_url(ACTIVE_DATABASE_URI)
IS_SQLITE_DB = ACTIVE_DATABASE_URI.startswith("sqlite:")
IS_POSTGRESQL_DB = ACTIVE_DATABASE_URI.startswith("postgresql")
MONITOR_LOG_PATH = Path(os.getenv("APP_MONITOR_LOG_PATH", str(LOGS_DIR / "ai_monitor.log"))).expanduser().resolve()
SQLITE_BUSY_TIMEOUT_MS = max(1000, int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "15000") or 15000))
SQLITE_BUSY_TIMEOUT_SECONDS = SQLITE_BUSY_TIMEOUT_MS / 1000.0
POSTGRES_POOL_SIZE = max(2, int(os.getenv("POSTGRES_POOL_SIZE", "20") or 20))
POSTGRES_MAX_OVERFLOW = max(0, int(os.getenv("POSTGRES_MAX_OVERFLOW", "40") or 40))
POSTGRES_POOL_TIMEOUT = max(5, int(os.getenv("POSTGRES_POOL_TIMEOUT", "30") or 30))
POSTGRES_POOL_RECYCLE = max(60, int(os.getenv("POSTGRES_POOL_RECYCLE", "1800") or 1800))
POSTGRES_CONNECT_TIMEOUT = max(2, int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10") or 10))
VIDEO_DESKTOP_ROOT = Path(
    os.getenv("VIDEO_DESKTOP_ROOT", str(Path.home() / "Desktop" / "AI生成素材"))
).expanduser().resolve()
VIDEO_SOURCE_ASSETS_DIR = Path(
    os.getenv("VIDEO_SOURCE_ASSETS_DIR", str(VIDEO_DESKTOP_ROOT / "source_assets"))
).expanduser().resolve()
VIDEO_SEGMENTS_DIR = Path(
    os.getenv("VIDEO_SEGMENTS_DIR", str(VIDEO_DESKTOP_ROOT / "seedance_segments"))
).expanduser().resolve()
VIDEO_FINAL_DIR = Path(
    os.getenv("VIDEO_FINAL_DIR", str(VIDEO_DESKTOP_ROOT / "final_videos"))
).expanduser().resolve()
ENABLE_PROACTIVE_CNS = os.getenv("ENABLE_PROACTIVE_CNS", "true").lower() == "true"
## Keep CNS runtime/proactive jobs, but disable DB heartbeat persistence by default to reduce noise.
CNS_HEARTBEAT_ENABLED = os.getenv("CNS_HEARTBEAT_ENABLED", "false").strip().lower() == "true"
PROACTIVE_INTERVAL_SECONDS = int(os.getenv("PROACTIVE_INTERVAL_SECONDS", "180"))
ENABLE_STARTUP_AUDIT = os.getenv("ENABLE_STARTUP_AUDIT", "true").lower() == "true"
ENABLE_DAILY_AUTONOMOUS_JOBS = os.getenv("ENABLE_DAILY_AUTONOMOUS_JOBS", "true").lower() == "true"
STARTUP_BOOTSTRAP_ENABLED = os.getenv("STARTUP_BOOTSTRAP_ENABLED", "true").lower() == "true"
STARTUP_LEADER_ONLY = os.getenv("STARTUP_LEADER_ONLY", "true").strip().lower() == "true"
STARTUP_BOOTSTRAP_LOCK_PATH = Path(
    os.getenv("STARTUP_BOOTSTRAP_LOCK_PATH", str(INSTANCE_DIR / "startup_bootstrap.lock"))
).expanduser().resolve()
PRIVACY_MODE = os.getenv("PRIVACY_MODE", "false").strip().lower() == "true"
PRIVACY_REDACTION_TEXT = os.getenv("PRIVACY_REDACTION_TEXT", "[REDACTED]")
LEARNING_MODE = os.getenv("LEARNING_MODE", "true").strip().lower() == "true"
ASK_BACK_MODE = os.getenv("ASK_BACK_MODE", "true").strip().lower() == "true"
PREFER_CLOUD_MODELS = os.getenv("PREFER_CLOUD_MODELS", "true").strip().lower() == "true"
ALLOW_LOCAL_MODEL_FALLBACK = os.getenv("ALLOW_LOCAL_MODEL_FALLBACK", "false").strip().lower() == "true"
EXECUTION_PROVIDER = os.getenv("EXECUTION_PROVIDER", "nvidia").strip().lower()
CHAT_PREFERRED_PROVIDER = os.getenv("CHAT_PREFERRED_PROVIDER", "gemini").strip().lower()
KEY_FAIL_CLOSED = os.getenv("KEY_FAIL_CLOSED", "true").strip().lower() == "true"
REQUIRE_ENCRYPTED_KEYS = os.getenv("REQUIRE_ENCRYPTED_KEYS", "false").strip().lower() == "true"
GEMINI_REQUIRE_ENCRYPTED_KEY = os.getenv("GEMINI_REQUIRE_ENCRYPTED_KEY", "true").strip().lower() == "true"
NVIDIA_REQUIRE_ENCRYPTED_KEY = os.getenv("NVIDIA_REQUIRE_ENCRYPTED_KEY", "false").strip().lower() == "true"
ZZZ_REQUIRE_ENCRYPTED_KEY = os.getenv("ZZZ_REQUIRE_ENCRYPTED_KEY", "true").strip().lower() == "true"
ZZZ_FAIL_CLOSED = os.getenv("ZZZ_FAIL_CLOSED", "true").strip().lower() == "true"
AUTO_MERGE_LEGACY_DATA = os.getenv("AUTO_MERGE_LEGACY_DATA", "true").strip().lower() == "true"
LEGACY_DB_PATHS = os.getenv("LEGACY_DB_PATHS", "").strip()
CHATGPT_BRIDGE_ENABLED = os.getenv("CHATGPT_BRIDGE_ENABLED", "true").strip().lower() == "true"
CHATGPT_BRIDGE_MODEL = os.getenv("CHATGPT_BRIDGE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS = max(60, int(os.getenv("CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS", "300")))
CHATGPT_BRIDGE_MAX_ITEMS = max(5, min(60, int(os.getenv("CHATGPT_BRIDGE_MAX_ITEMS", "20"))))
CHATGPT_BRIDGE_SUMMON_COMMAND = (os.getenv("CHATGPT_BRIDGE_SUMMON_COMMAND", "以利亞") or "以利亞").strip()
CHATGPT_BRIDGE_FULL_SYNC_ENABLED = os.getenv("CHATGPT_BRIDGE_FULL_SYNC_ENABLED", "true").strip().lower() == "true"
CHATGPT_BRIDGE_FULL_SYNC_BATCH_SIZE = max(5, min(200, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_BATCH_SIZE", "40"))))
CHATGPT_BRIDGE_FULL_SYNC_MAX_BATCHES = max(1, min(2000, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_MAX_BATCHES", "500"))))
CHATGPT_BRIDGE_FULL_SYNC_FIELD_MAX_CHARS = max(200, min(50000, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_FIELD_MAX_CHARS", "8000"))))
CHATGPT_BRIDGE_FULL_SYNC_RETRY = max(0, min(5, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_RETRY", "2"))))
CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS = max(
    0,
    min(20, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS", "2"))),
)
N8N_ENABLED = os.getenv("N8N_ENABLED", "false").strip().lower() == "true"
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "").strip()
N8N_CHAT_EVENT_WEBHOOK = os.getenv("N8N_CHAT_EVENT_WEBHOOK", "").strip()
N8N_TASK_EVENT_WEBHOOK = os.getenv("N8N_TASK_EVENT_WEBHOOK", "").strip()
N8N_FEED_EVENT_WEBHOOK = os.getenv("N8N_FEED_EVENT_WEBHOOK", "").strip()
N8N_INGEST_ENABLED = os.getenv("N8N_INGEST_ENABLED", "true").strip().lower() == "true"
N8N_TIMEOUT_SECONDS = max(2, min(60, int(os.getenv("N8N_TIMEOUT_SECONDS", "12"))))
N8N_SEEDANCE_SUBMIT_WEBHOOK = os.getenv("N8N_SEEDANCE_SUBMIT_WEBHOOK", "").strip()
N8N_SEEDANCE_CALLBACK_SECRET = os.getenv("N8N_SEEDANCE_CALLBACK_SECRET", "").strip()
CONVERSATION_FEED_ENABLED = os.getenv("CONVERSATION_FEED_ENABLED", "true").strip().lower() == "true"
CONVERSATION_FEED_MAX_PREVIEW = max(80, min(1200, int(os.getenv("CONVERSATION_FEED_MAX_PREVIEW", "320"))))
MUSIC_PROVIDER_REQUIRE_ENCRYPTED_KEY = os.getenv("MUSIC_PROVIDER_REQUIRE_ENCRYPTED_KEY", "false").strip().lower() == "true"
FAL_KEY = (os.getenv("FAL_KEY", "") or "").strip()
SEEDANCE_ENABLED = os.getenv("SEEDANCE_ENABLED", "false").strip().lower() == "true"
SEEDANCE_PROVIDER = (os.getenv("SEEDANCE_PROVIDER", "fal") or "fal").strip()
SEEDANCE_TEXT_MODEL = (
    os.getenv("SEEDANCE_TEXT_MODEL", "bytedance/seedance-2.0/text-to-video").strip()
    or "bytedance/seedance-2.0/text-to-video"
)
SEEDANCE_IMAGE_MODEL = (
    os.getenv("SEEDANCE_IMAGE_MODEL", "bytedance/seedance-2.0/image-to-video").strip()
    or "bytedance/seedance-2.0/image-to-video"
)
SEEDANCE_DEFAULT_SEGMENT_DURATION = max(
    4, min(15, int(os.getenv("SEEDANCE_DEFAULT_SEGMENT_DURATION", "8")))
)
SEEDANCE_TARGET_MIN_FINAL_DURATION_SECONDS = max(
    30, int(os.getenv("SEEDANCE_TARGET_MIN_FINAL_DURATION_SECONDS", "180"))
)
SEEDANCE_DEFAULT_RESOLUTION = os.getenv("SEEDANCE_DEFAULT_RESOLUTION", "720p").strip() or "720p"
SEEDANCE_DEFAULT_ASPECT_RATIO = os.getenv("SEEDANCE_DEFAULT_ASPECT_RATIO", "9:16").strip() or "9:16"
VIDEO_DEFAULT_BILINGUAL_CAPTIONS = os.getenv("VIDEO_DEFAULT_BILINGUAL_CAPTIONS", "true").strip().lower() == "true"
VIDEO_DEFAULT_THEME_AUDIO = os.getenv("VIDEO_DEFAULT_THEME_AUDIO", "true").strip().lower() == "true"
VIDEO_DEFAULT_ZH_TW_NARRATION = os.getenv("VIDEO_DEFAULT_ZH_TW_NARRATION", "true").strip().lower() == "true"
VIDEO_NARRATION_LOCALE = os.getenv("VIDEO_NARRATION_LOCALE", "zh-TW").strip() or "zh-TW"
VIDEO_NARRATION_TONE = os.getenv("VIDEO_NARRATION_TONE", "mature_natural").strip() or "mature_natural"
VIDEO_NARRATION_VOICE_PROVIDER = os.getenv("VIDEO_NARRATION_VOICE_PROVIDER", "").strip()
VIDEO_CAPTION_STYLE = os.getenv("VIDEO_CAPTION_STYLE", "sentence_pop").strip() or "sentence_pop"
VIDEO_AUDIO_LIBRARY_DIR = Path(
    os.getenv("VIDEO_AUDIO_LIBRARY_DIR", str(VIDEO_DESKTOP_ROOT / "audio_library"))
).expanduser().resolve()
CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS = max(
    10,
    min(300, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS", "60"))),
)
CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS = max(
    30,
    min(7200, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS", "900"))),
)
CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT = os.getenv(
    "CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT",
    "true",
).strip().lower() == "true"
CHATGPT_BRIDGE_FULL_SYNC_JOB_RETENTION = max(
    10,
    min(2000, int(os.getenv("CHATGPT_BRIDGE_FULL_SYNC_JOB_RETENTION", "300"))),
)
CHATGPT_BRIDGE_INGEST_ENABLED = os.getenv("CHATGPT_BRIDGE_INGEST_ENABLED", "true").strip().lower() == "true"
CHATGPT_BRIDGE_INGEST_REQUIRE_TOKEN = os.getenv("CHATGPT_BRIDGE_INGEST_REQUIRE_TOKEN", "true").strip().lower() == "true"
CHATGPT_BRIDGE_INGEST_TOKEN = (os.getenv("CHATGPT_BRIDGE_INGEST_TOKEN", "") or "").strip()
CHATGPT_BRIDGE_INGEST_MAX_ITEMS = max(1, min(500, int(os.getenv("CHATGPT_BRIDGE_INGEST_MAX_ITEMS", "120"))))
CHAT_STORAGE_USER_MAX_CHARS = max(2000, min(200000, int(os.getenv("CHAT_STORAGE_USER_MAX_CHARS", "50000"))))
CHAT_STORAGE_AI_MAX_CHARS = max(2000, min(400000, int(os.getenv("CHAT_STORAGE_AI_MAX_CHARS", "100000"))))
SERVER_API_TOKEN_REQUIRED = os.getenv("SERVER_API_TOKEN_REQUIRED", "true").strip().lower() == "true"
SERVER_API_TOKEN = (os.getenv("SERVER_API_TOKEN", os.getenv("SECRET_CODE", "")) or "").strip()
SERVER_API_IP_ALLOWLIST_ENABLED = os.getenv("SERVER_API_IP_ALLOWLIST_ENABLED", "true").strip().lower() == "true"
SERVER_API_IP_ALLOWLIST = (os.getenv("SERVER_API_IP_ALLOWLIST", "127.0.0.1,::1,localhost") or "").strip()
SERVER_API_TRUST_PROXY_HEADERS = os.getenv("SERVER_API_TRUST_PROXY_HEADERS", "false").strip().lower() == "true"
SERVER_API_IP_ALLOWLIST_ENTRIES = [item.strip() for item in SERVER_API_IP_ALLOWLIST.split(",") if item.strip()]
SYNC_AUTO_RECOVER_ENABLED = os.getenv("SYNC_AUTO_RECOVER_ENABLED", "true").strip().lower() == "true"
SYNC_AUTO_RECOVER_MAX_ROUNDS = max(0, min(5, int(os.getenv("SYNC_AUTO_RECOVER_MAX_ROUNDS", "2"))))
SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS = max(500, min(8000, int(os.getenv("SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS", "3000"))))
DAILY_JOB_HOUR = int(os.getenv("DAILY_JOB_HOUR", "9"))
DAILY_JOB_MINUTE = int(os.getenv("DAILY_JOB_MINUTE", "0"))
DAILY_JOB_MAX_RESULTS = int(os.getenv("DAILY_JOB_MAX_RESULTS", "120"))
DAILY_JOB_MAX_SCAN_FILES = int(os.getenv("DAILY_JOB_MAX_SCAN_FILES", "6000"))
GPT2_BACKEND = os.getenv("GPT2_BACKEND", "auto").lower()
GPT2_SIDECAR_URL = os.getenv("GPT2_SIDECAR_URL", "http://127.0.0.1:5010/generate")
GPT2_SIDECAR_TIMEOUT = int(os.getenv("GPT2_SIDECAR_TIMEOUT", "20"))
FUSE_WHITEHAT_TO_PROCLAIMER = os.getenv("FUSE_WHITEHAT_TO_PROCLAIMER", "true").strip().lower() == "true"
NOTEBOOKLM_ENABLED = os.getenv("NOTEBOOKLM_ENABLED", "false").strip().lower() == "true"
NOTEBOOKLM_API_BASE = os.getenv("NOTEBOOKLM_API_BASE", "https://discoveryengine.googleapis.com").strip() or "https://discoveryengine.googleapis.com"
NOTEBOOKLM_API_VERSION = os.getenv("NOTEBOOKLM_API_VERSION", "v1alpha").strip() or "v1alpha"
NOTEBOOKLM_PROJECT_NUMBER = os.getenv("NOTEBOOKLM_PROJECT_NUMBER", "").strip()
NOTEBOOKLM_LOCATION = os.getenv("NOTEBOOKLM_LOCATION", "global").strip() or "global"
NOTEBOOKLM_DEFAULT_NOTEBOOK_ID = os.getenv("NOTEBOOKLM_DEFAULT_NOTEBOOK_ID", "").strip()
NOTEBOOKLM_ACCESS_TOKEN = os.getenv("NOTEBOOKLM_ACCESS_TOKEN", "").strip()
NOTEBOOKLM_USE_GCLOUD_TOKEN = os.getenv("NOTEBOOKLM_USE_GCLOUD_TOKEN", "false").strip().lower() == "true"
NOTEBOOKLM_GCLOUD_TOKEN_CMD = os.getenv("NOTEBOOKLM_GCLOUD_TOKEN_CMD", "gcloud auth print-access-token").strip() or "gcloud auth print-access-token"
try:
    NOTEBOOKLM_TIMEOUT_SECONDS = int(os.getenv("NOTEBOOKLM_TIMEOUT_SECONDS", "30"))
except Exception:
    NOTEBOOKLM_TIMEOUT_SECONDS = 30
NOTEBOOKLM_TIMEOUT_SECONDS = max(5, min(180, NOTEBOOKLM_TIMEOUT_SECONDS))


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 10) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _fuse_agent_key(agent_key: str | None) -> str:
    normalized = str(agent_key or "").strip().lower()
    if not normalized:
        return ""
    if normalized == "dispatcher":
        return "proclaimer"
    if FUSE_WHITEHAT_TO_PROCLAIMER and normalized == "whitehat":
        return "proclaimer"
    return normalized


def _fused_safety_agent_key() -> str:
    return _fuse_agent_key("whitehat") or "whitehat"


def _normalize_agent_label_with_fusion(agent_label: str | None, assigned_agent: str | None = None) -> str:
    label = str(agent_label or "").strip()
    if not label:
        return ""
    lowered = label.lower()
    if lowered == "dispatcher":
        return "proclaimer.primary"
    if lowered.startswith("dispatcher."):
        suffix = label.split(".", 1)[1] if "." in label else "primary"
        return f"proclaimer.{suffix}"
    if FUSE_WHITEHAT_TO_PROCLAIMER and lowered == "whitehat":
        return "proclaimer.primary"
    if FUSE_WHITEHAT_TO_PROCLAIMER and lowered.startswith("whitehat."):
        suffix = label.split(".", 1)[1] if "." in label else "primary"
        return f"proclaimer.{suffix}"
    if assigned_agent:
        normalized_agent = _fuse_agent_key(assigned_agent)
        if normalized_agent == "proclaimer" and lowered.startswith("proclaimer."):
            return label
    return label


RESPONSE_SAFETY_FILTER_ENABLED = os.getenv(
    "RESPONSE_SAFETY_FILTER_ENABLED",
    "true",
).strip().lower() == "true"
RESPONSE_SAFETY_REGENERATION_RETRIES = _env_int(
    "RESPONSE_SAFETY_REGENERATION_RETRIES",
    default=1,
    minimum=0,
    maximum=3,
)


def _normalize_ratelimit_storage_uri(raw_uri: str) -> str:
    cleaned = str(raw_uri or "").strip()
    if not cleaned:
        return "memory://"
    return cleaned


def resolve_ratelimit_storage_uri() -> tuple[str, str]:
    configured_uri = _normalize_ratelimit_storage_uri(os.getenv("RATELIMIT_STORAGE_URI", "redis://127.0.0.1:6379/0"))
    effective_uri = configured_uri

    if configured_uri.startswith(("redis://", "rediss://")):
        if importlib.util.find_spec("redis") is None:
            logging.warning("RATELIMIT_STORAGE_URI uses redis, but redis package is unavailable; fallback to memory://")
            effective_uri = "memory://"
        else:
            try:
                import redis
                client = redis.Redis.from_url(configured_uri, socket_connect_timeout=1, socket_timeout=1)
                client.ping()
            except Exception as exc:
                logging.warning("Redis rate-limit backend unreachable (%s), fallback to memory://", exc)
                effective_uri = "memory://"

    return configured_uri, effective_uri

for folder in [INSTANCE_DIR, UPLOADS_DIR, LOGS_DIR, ARCHIVE_DIR, VIDEO_DESKTOP_ROOT, VIDEO_SOURCE_ASSETS_DIR, VIDEO_SEGMENTS_DIR, VIDEO_FINAL_DIR, VIDEO_AUDIO_LIBRARY_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Configure logging for monitoring
logging.basicConfig(
    level=logging.INFO,
    filename=str(MONITOR_LOG_PATH),
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# Database configuration (PostgreSQL first, SQLite fallback)
app.config['SQLALCHEMY_DATABASE_URI'] = ACTIVE_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if IS_SQLITE_DB:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'timeout': SQLITE_BUSY_TIMEOUT_SECONDS,
            'check_same_thread': False,
        },
        'poolclass': NullPool,
        'pool_pre_ping': True,
    }
elif IS_POSTGRESQL_DB:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': POSTGRES_POOL_SIZE,
        'max_overflow': POSTGRES_MAX_OVERFLOW,
        'pool_timeout': POSTGRES_POOL_TIMEOUT,
        'pool_recycle': POSTGRES_POOL_RECYCLE,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': POSTGRES_CONNECT_TIMEOUT,
            'application_name': os.getenv('POSTGRES_APP_NAME', 'chengcheng-chat-backend'),
        },
    }
else:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
    }
app.config['UPLOAD_FOLDER'] = str(UPLOADS_DIR)
app.config['DATA_ROOT'] = str(DATA_ROOT)
app.config['INSTANCE_DIR'] = str(INSTANCE_DIR)
app.config['LOGS_DIR'] = str(LOGS_DIR)
configured_ratelimit_uri, effective_ratelimit_uri = resolve_ratelimit_storage_uri()
app.config['RATELIMIT_STORAGE_URI_CONFIGURED'] = configured_ratelimit_uri
app.config['RATELIMIT_STORAGE_URI'] = effective_ratelimit_uri
db = SQLAlchemy(app)


def _remove_db_session_safely():
    """Release scoped sessions inside a Flask application context."""
    with app.app_context():
        db.session.remove()


@event.listens_for(Engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record):
    if not IS_SQLITE_DB:
        return
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()

# Rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=app.config['RATELIMIT_STORAGE_URI'],
)

# AI Models (Data Security: Local models don't send data, cloud models use secure APIs)
KEY_ENCRYPTION_SECRET = os.getenv('KEY_ENCRYPTION_SECRET', '').strip()
ZZZ_SECRET_PROTOCOL_KEY = os.getenv('ZZZ_SECRET_PROTOCOL_KEY', '').strip()
ZZZ_SECURITY_PROTOCOL_ENABLED = os.getenv('ZZZ_SECURITY_PROTOCOL_ENABLED', 'true').strip().lower() == 'true'
ZZZ_OBFUSCATE_RESPONSE = os.getenv('ZZZ_OBFUSCATE_RESPONSE', 'true').strip().lower() == 'true'


def _safe_key_bytes(secret: str) -> bytes:
    return hashlib.sha256((secret or '').encode('utf-8')).digest()


def _xor_cipher(data: bytes, key_bytes: bytes) -> bytes:
    if not key_bytes:
        return data
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))


def encrypt_secret_value(plain_text: str, secret: str) -> str:
    if not plain_text:
        return ''
    if not secret:
        return plain_text
    nonce = secrets.token_bytes(16)
    key_bytes = _safe_key_bytes(f"{secret}:" + base64.urlsafe_b64encode(nonce).decode('utf-8'))
    cipher = _xor_cipher(plain_text.encode('utf-8'), key_bytes)
    return f"enc:v1:{base64.urlsafe_b64encode(nonce).decode('utf-8')}:{base64.urlsafe_b64encode(cipher).decode('utf-8')}"


def decrypt_secret_value(raw_value: str | None, secret: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        return ''
    if not value.startswith('enc:v1:'):
        return value
    if not secret:
        return ''
    try:
        _prefix, _ver, nonce_b64, cipher_b64 = value.split(':', 3)
        nonce = base64.urlsafe_b64decode(nonce_b64.encode('utf-8'))
        cipher = base64.urlsafe_b64decode(cipher_b64.encode('utf-8'))
        key_bytes = _safe_key_bytes(f"{secret}:" + base64.urlsafe_b64encode(nonce).decode('utf-8'))
        plain = _xor_cipher(cipher, key_bytes)
        return plain.decode('utf-8')
    except Exception:
        return ''


def _is_placeholder_secret_value(value: str | None) -> bool:
    stripped = str(value or "").strip().lower()
    if not stripped:
        return False
    placeholder_markers = [
        "your_openai_api_key_here",
        "your_huggingface_api_key_here",
        "your_together_api_key_here",
        "your_openrouter_api_key_here",
        "your_groq_api_key_here",
        "your_zzz_api_key_here",
        "your_gemini_api_key_here",
        "your_",
    ]
    return any(marker in stripped for marker in placeholder_markers)


KEY_RESOLUTION_AUDIT = {}


def resolve_api_key(
    key_name: str,
    legacy_alias: str | None = None,
    require_encrypted: bool = False,
) -> str:
    candidates = [key_name]
    if legacy_alias:
        candidates.append(legacy_alias)

    enforce_encrypted = bool(require_encrypted or REQUIRE_ENCRYPTED_KEYS)
    audit = {
        "key_name": key_name,
        "candidates": candidates,
        "require_encrypted": enforce_encrypted,
        "fail_closed": KEY_FAIL_CLOSED,
        "source": "unresolved",
        "events": [],
    }

    for candidate in candidates:
        encrypted_raw = os.getenv(f"{candidate}_ENC")
        encrypted = str(encrypted_raw or "").strip()
        if encrypted:
            decrypted = decrypt_secret_value(encrypted, KEY_ENCRYPTION_SECRET)
            if decrypted and not _is_placeholder_secret_value(decrypted):
                audit["source"] = "enc"
                audit["selected_candidate"] = candidate
                audit["selected_var"] = f"{candidate}_ENC"
                KEY_RESOLUTION_AUDIT[key_name] = audit
                return decrypted
            audit["events"].append({
                "candidate": candidate,
                "var": f"{candidate}_ENC",
                "reason": "enc_decrypt_failed_or_placeholder",
            })
            if KEY_FAIL_CLOSED:
                continue
        else:
            audit["events"].append({
                "candidate": candidate,
                "var": f"{candidate}_ENC",
                "reason": "enc_empty",
            })
            if enforce_encrypted and KEY_FAIL_CLOSED:
                continue

        plain = (os.getenv(candidate) or '').strip()
        if plain and not _is_placeholder_secret_value(plain):
            if enforce_encrypted and KEY_FAIL_CLOSED:
                audit["events"].append({
                    "candidate": candidate,
                    "var": candidate,
                    "reason": "plain_present_but_rejected_require_encrypted",
                })
                continue
            audit["source"] = "plain"
            audit["selected_candidate"] = candidate
            audit["selected_var"] = candidate
            KEY_RESOLUTION_AUDIT[key_name] = audit
            return plain
        if plain:
            audit["events"].append({
                "candidate": candidate,
                "var": candidate,
                "reason": "plain_placeholder",
            })

    KEY_RESOLUTION_AUDIT[key_name] = audit
    return ''


def _build_zzz_security_headers(prompt_text: str) -> dict:
    if not ZZZ_SECURITY_PROTOCOL_ENABLED:
        return {}

    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(12)
    prompt_hash = hashlib.sha256((prompt_text or '').encode('utf-8')).hexdigest()

    headers = {
        'X-ZZZ-Protocol': 'shield-v1',
        'X-ZZZ-Timestamp': timestamp,
        'X-ZZZ-Nonce': nonce,
        'X-ZZZ-Prompt-SHA256': prompt_hash,
    }

    if ZZZ_SECRET_PROTOCOL_KEY:
        sign_payload = f"{timestamp}.{nonce}.{prompt_hash}"
        signature = hmac.new(
            ZZZ_SECRET_PROTOCOL_KEY.encode('utf-8'),
            sign_payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        headers['X-ZZZ-Signature'] = signature

    return headers


def obfuscate_transport_text(raw_text: str) -> str:
    text = str(raw_text or '')
    if not text:
        return ''

    if ZZZ_SECRET_PROTOCOL_KEY:
        return encrypt_secret_value(text, ZZZ_SECRET_PROTOCOL_KEY).replace('enc:v1:', 'obf:v1:', 1)

    return 'obf:v1::' + base64.urlsafe_b64encode(text.encode('utf-8')).decode('utf-8')


def _is_loopback_or_localhost(ip_text: str) -> bool:
    value = str(ip_text or '').strip().lower()
    if not value:
        return False
    if value in {'localhost', '::1', '127.0.0.1'}:
        return True
    try:
        return ip_address(value).is_loopback
    except Exception:
        return False


def _resolve_server_request_ip() -> str:
    remote = str(getattr(request, 'remote_addr', '') or '').strip()
    if SERVER_API_TRUST_PROXY_HEADERS and _is_loopback_or_localhost(remote):
        xff = str(request.headers.get('X-Forwarded-For', '') or '').strip()
        if xff:
            first_ip = xff.split(',')[0].strip()
            if first_ip:
                return first_ip
        real_ip = str(request.headers.get('X-Real-IP', '') or '').strip()
        if real_ip:
            return real_ip
    return remote or 'unknown'


def _is_server_ip_allowed(client_ip: str) -> bool:
    entries = SERVER_API_IP_ALLOWLIST_ENTRIES
    if not entries:
        return False

    ip_text = str(client_ip or '').strip()
    lowered = ip_text.lower()
    try:
        ip_obj = ip_address(ip_text)
    except Exception:
        ip_obj = None

    for raw in entries:
        candidate = str(raw or '').strip()
        if not candidate:
            continue
        candidate_lower = candidate.lower()

        if candidate_lower == lowered:
            return True
        if candidate_lower == 'localhost' and _is_loopback_or_localhost(ip_text):
            return True

        try:
            if '/' in candidate:
                if ip_obj and ip_obj in ip_network(candidate, strict=False):
                    return True
            else:
                if ip_obj and ip_obj == ip_address(candidate):
                    return True
        except Exception:
            continue

    return False


def _extract_server_api_token_from_request() -> str:
    auth_header = str(request.headers.get('Authorization', '') or '').strip()
    if auth_header:
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
            if token:
                return token
        elif not auth_header.lower().startswith('basic '):
            # Compatible with simple "Authorization: <token>" integrations.
            return auth_header

    for header_name in ('X-Server-Token', 'X-API-Token'):
        token = str(request.headers.get(header_name, '') or '').strip()
        if token:
            return token

    query_token = str(request.args.get('server_token', '') or '').strip()
    if query_token:
        return query_token

    body = request.get_json(silent=True) or {}
    if isinstance(body, dict):
        body_token = str(body.get('server_token', '') or '').strip()
        if body_token:
            return body_token

    return ''


def require_server_api_token(view_func):
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        if not SERVER_API_TOKEN_REQUIRED:
            return view_func(*args, **kwargs)

        expected = str(SERVER_API_TOKEN or '').strip()
        if not expected:
            return jsonify({
                'status': 'failed',
                'reason': 'server_api_token_not_configured',
                'message': 'SERVER_API_TOKEN_REQUIRED=true 但未設定 SERVER_API_TOKEN',
            }), 503

        provided = _extract_server_api_token_from_request()
        if not provided or not hmac.compare_digest(provided, expected):
            return jsonify({
                'status': 'forbidden',
                'reason': 'invalid_server_api_token',
                'message': '缺少或錯誤的 Server API Token',
            }), 403

        if SERVER_API_IP_ALLOWLIST_ENABLED:
            if not SERVER_API_IP_ALLOWLIST_ENTRIES:
                return jsonify({
                    'status': 'failed',
                    'reason': 'server_api_ip_allowlist_not_configured',
                    'message': 'SERVER_API_IP_ALLOWLIST_ENABLED=true 但白名單為空',
                }), 503

            client_ip = _resolve_server_request_ip()
            if not _is_server_ip_allowed(client_ip):
                return jsonify({
                    'status': 'forbidden',
                    'reason': 'source_ip_not_allowed',
                    'message': f'來源 IP 不在白名單：{client_ip}',
                }), 403

        return view_func(*args, **kwargs)

    return _wrapped


def get_server_api_auth_status() -> dict:
    token_configured = bool(SERVER_API_TOKEN)
    return {
        'required': SERVER_API_TOKEN_REQUIRED,
        'token_configured': token_configured,
        'ip_allowlist_enabled': SERVER_API_IP_ALLOWLIST_ENABLED,
        'ip_allowlist_entries_count': len(SERVER_API_IP_ALLOWLIST_ENTRIES),
        'ip_allowlist_preview': SERVER_API_IP_ALLOWLIST_ENTRIES[:8],
        'trust_proxy_headers': SERVER_API_TRUST_PROXY_HEADERS,
        'accept_headers': ['Authorization: Bearer <token>', 'X-Server-Token', 'X-API-Token'],
        'accept_query_param': 'server_token',
        'accept_body_field': 'server_token',
        'fail_closed': bool(SERVER_API_TOKEN_REQUIRED),
        'sync_auto_recover_enabled': SYNC_AUTO_RECOVER_ENABLED,
        'sync_auto_recover_max_rounds': SYNC_AUTO_RECOVER_MAX_ROUNDS,
        'sync_auto_recover_reduce_field_max_chars': SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS,
    }


HF_API_KEY = resolve_api_key('HF_API_KEY')
TOGETHER_API_KEY = resolve_api_key('TOGETHER_API_KEY')
OPENAI_API_KEY = resolve_api_key('OPENAI_API_KEY')
OPENROUTER_API_KEY = resolve_api_key('OPENROUTER_API_KEY')
OPENROUTER_API_KEY_2 = resolve_api_key('OPENROUTER_API_KEY_2')
GROQ_API_KEY = resolve_api_key('GROQ_API_KEY')
GEMINI_API_KEY = resolve_api_key('GEMINI_API_KEY', require_encrypted=GEMINI_REQUIRE_ENCRYPTED_KEY)
NVIDIA_API_KEY = resolve_api_key('NVIDIA_API_KEY', legacy_alias='NVAPI_API_KEY', require_encrypted=NVIDIA_REQUIRE_ENCRYPTED_KEY)
ZZZ_API_KEY = resolve_api_key('ZZZ_API_KEY', legacy_alias='ZHIZENGZENG_API_KEY', require_encrypted=ZZZ_REQUIRE_ENCRYPTED_KEY)
MUSIC_API_KEY = resolve_api_key('MUSIC_API_KEY', legacy_alias='OP_MUSIC_API_KEY', require_encrypted=MUSIC_PROVIDER_REQUIRE_ENCRYPTED_KEY)
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
OPENROUTER_API_BASE = os.getenv('OPENROUTER_API_BASE', 'https://openrouter.ai/api/v1')
GROQ_API_BASE = os.getenv('GROQ_API_BASE', 'https://api.groq.com/openai/v1')
GEMINI_API_BASE = os.getenv('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta')
NVIDIA_API_BASE = os.getenv('NVIDIA_API_BASE', 'https://integrate.api.nvidia.com/v1')
ZZZ_API_BASE = os.getenv('ZZZ_API_BASE', os.getenv('ZHIZENGZENG_API_BASE', 'https://api.zhizengzeng.com/v1'))
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'openrouter/free')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
NVIDIA_MODEL = os.getenv('NVIDIA_MODEL', 'meta/llama-3.1-405b-instruct')
ZZZ_MODEL = os.getenv('ZZZ_MODEL', os.getenv('ZHIZENGZENG_MODEL', 'gpt-4o-mini'))
OPENROUTER_SITE_URL = os.getenv('OPENROUTER_SITE_URL', 'http://127.0.0.1:5001')
OPENROUTER_APP_NAME = os.getenv('OPENROUTER_APP_NAME', 'AI-Desktop-Command-Center')
HF_MODEL = "microsoft/DialoGPT-medium"
TOGETHER_MODEL = "meta-llama/Llama-2-7b-chat-hf"
LOCAL_OLLAMA_MODEL = os.getenv('LOCAL_OLLAMA_MODEL', 'tinyllama')


def has_configured_key(value: str | None) -> bool:
    if not value:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return not _is_placeholder_secret_value(stripped)


def _extract_notebooklm_access_token_from_request(payload: dict | None = None) -> str:
    for header_name in ("X-NotebookLM-Access-Token", "X-Google-Access-Token"):
        token = str(request.headers.get(header_name, "") or "").strip()
        if token:
            return token

    body = payload if isinstance(payload, dict) else {}
    body_token = str(body.get("notebooklm_access_token", "") or "").strip()
    if body_token:
        return body_token

    return ""


def _resolve_notebooklm_access_token(payload: dict | None = None) -> tuple[str, str]:
    request_token = _extract_notebooklm_access_token_from_request(payload=payload)
    if request_token and not _is_placeholder_secret_value(request_token):
        return request_token, "request"

    env_token = str(NOTEBOOKLM_ACCESS_TOKEN or "").strip()
    if env_token and not _is_placeholder_secret_value(env_token):
        return env_token, "env"

    if NOTEBOOKLM_USE_GCLOUD_TOKEN:
        try:
            cmd = shlex.split(NOTEBOOKLM_GCLOUD_TOKEN_CMD)
            if cmd:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=12,
                    check=False,
                )
                token = str(proc.stdout or "").strip()
                if proc.returncode == 0 and token and not _is_placeholder_secret_value(token):
                    return token, "gcloud"
                logging.warning(
                    "NotebookLM token command failed: code=%s stderr=%s",
                    proc.returncode,
                    str(proc.stderr or "").strip()[:300],
                )
        except Exception as exc:
            logging.warning("NotebookLM token command exception: %s", exc)

    return "", ""


def _notebooklm_project_location_from_request(payload: dict | None = None) -> tuple[str, str]:
    body = payload if isinstance(payload, dict) else {}
    project_number = str(
        body.get("project_number")
        or request.args.get("project_number")
        or NOTEBOOKLM_PROJECT_NUMBER
        or ""
    ).strip()
    location = str(
        body.get("location")
        or request.args.get("location")
        or NOTEBOOKLM_LOCATION
        or "global"
    ).strip() or "global"
    return project_number, location


def _notebooklm_notebook_resource_name(notebook_id: str, project_number: str = "", location: str = "") -> str:
    normalized = str(notebook_id or "").strip().strip("/")
    if not normalized:
        raise ValueError("notebook_id 不可為空")
    if "://" in normalized:
        raise ValueError("notebook_id 格式錯誤，禁止使用完整 URL")
    if normalized.startswith("projects/"):
        return normalized
    if not project_number:
        raise ValueError("NOTEBOOKLM_PROJECT_NUMBER 未設定，且 notebook_id 不是完整資源名稱")
    return f"projects/{project_number}/locations/{location or 'global'}/notebooks/{normalized}"


def _normalize_notebooklm_resource_path(path: str) -> str:
    normalized = str(path or "").strip().strip("/")
    if not normalized:
        raise ValueError("path 不可為空")
    if "://" in normalized:
        raise ValueError("path 格式錯誤，禁止使用完整 URL")
    version_prefix = f"{NOTEBOOKLM_API_VERSION}/"
    if normalized.startswith(version_prefix):
        normalized = normalized[len(version_prefix):]
    if not normalized.startswith("projects/"):
        raise ValueError("path 必須以 projects/ 開頭")
    return normalized


def get_notebooklm_runtime_status(resolve_token: bool = False, payload: dict | None = None) -> dict:
    project_number = str(NOTEBOOKLM_PROJECT_NUMBER or "").strip()
    location = str(NOTEBOOKLM_LOCATION or "global").strip() or "global"
    token_source = ""
    token_available = False
    if resolve_token:
        token, token_source = _resolve_notebooklm_access_token(payload=payload)
        token_available = bool(token)
    else:
        token_available = bool(str(NOTEBOOKLM_ACCESS_TOKEN or "").strip()) or NOTEBOOKLM_USE_GCLOUD_TOKEN
        token_source = "env_or_gcloud" if token_available else ""

    missing_config = []
    if not NOTEBOOKLM_ENABLED:
        missing_config.append("NOTEBOOKLM_ENABLED=false")
    if not project_number:
        missing_config.append("NOTEBOOKLM_PROJECT_NUMBER 未設定")
    if not token_available:
        missing_config.append("NotebookLM OAuth Access Token 不可用")

    configured = len(missing_config) == 0
    return {
        "enabled": NOTEBOOKLM_ENABLED,
        "configured": configured,
        "api_base": NOTEBOOKLM_API_BASE,
        "api_version": NOTEBOOKLM_API_VERSION,
        "project_number": project_number,
        "project_number_configured": bool(project_number),
        "location": location,
        "default_notebook_id": NOTEBOOKLM_DEFAULT_NOTEBOOK_ID,
        "timeout_seconds": NOTEBOOKLM_TIMEOUT_SECONDS,
        "token_available": token_available,
        "token_source": token_source,
        "use_gcloud_token": NOTEBOOKLM_USE_GCLOUD_TOKEN,
        "missing_config": missing_config,
        "notes": [
            "NotebookLM Enterprise API 使用 Google OAuth Access Token（非 Gemini API Key）。",
            "可在 request body 傳 notebooklm_access_token，或由 NOTEBOOKLM_ACCESS_TOKEN / gcloud 提供。",
        ],
    }


def notebooklm_api_request(
    method: str,
    resource_path: str,
    payload: dict | None = None,
    params: dict | None = None,
    token_payload: dict | None = None,
) -> dict:
    if not NOTEBOOKLM_ENABLED:
        raise RuntimeError("NotebookLM connector disabled: NOTEBOOKLM_ENABLED=false")

    token, token_source = _resolve_notebooklm_access_token(payload=token_payload)
    if not token:
        raise RuntimeError("NotebookLM access token unavailable (請提供 OAuth access token)")
    if token.startswith("AIza"):
        raise RuntimeError("NotebookLM 需要 OAuth access token，不能使用 Gemini API key (AIza...)")

    normalized_path = _normalize_notebooklm_resource_path(resource_path)
    endpoint = f"{NOTEBOOKLM_API_BASE.rstrip('/')}/{NOTEBOOKLM_API_VERSION}/{normalized_path}"
    request_kwargs = {
        "method": str(method or "GET").upper(),
        "url": endpoint,
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        "params": params or None,
        "timeout": NOTEBOOKLM_TIMEOUT_SECONDS,
    }
    if request_kwargs["method"] != "GET":
        request_kwargs["json"] = payload or {}

    response = requests.request(**request_kwargs)
    data = {}
    try:
        data = response.json()
    except Exception:
        data = {"raw": _bridge_string(response.text, 2000)}

    if response.status_code >= 400:
        error_message = (
            (data.get("error") or {}).get("message")
            if isinstance(data, dict)
            else ""
        ) or _bridge_string(str(data), 500)
        raise RuntimeError(f"NotebookLM API error {response.status_code}: {error_message}")

    return {
        "status_code": response.status_code,
        "endpoint": endpoint,
        "token_source": token_source,
        "data": data,
    }


def inspect_key_format(provider: str, value: str | None) -> dict:
    raw = str(value or "").strip()
    if not raw:
        return {"configured": False, "format_valid": False, "reason": "empty"}
    if not has_configured_key(raw):
        return {"configured": False, "format_valid": False, "reason": "placeholder"}

    provider_key = (provider or "").strip().lower()
    if provider_key == "gemini":
        is_valid = raw.startswith("AIza") and len(raw) >= 35
        reason = "" if is_valid else "unexpected_prefix_or_length"
        return {"configured": True, "format_valid": is_valid, "reason": reason}

    if provider_key == "nvidia":
        is_valid = raw.startswith("nvapi-") and len(raw) >= 24
        reason = "" if is_valid else "unexpected_prefix_or_length"
        return {"configured": True, "format_valid": is_valid, "reason": reason}

    if provider_key in {"zhizengzeng", "zzz"}:
        is_valid = len(raw) >= 20
        reason = "" if is_valid else "too_short"
        return {"configured": True, "format_valid": is_valid, "reason": reason}

    return {"configured": True, "format_valid": True, "reason": ""}


def sanitize_for_storage(value: str | None, max_length: int = 1000) -> str:
    if PRIVACY_MODE:
        return PRIVACY_REDACTION_TEXT[:max_length]
    return str(value or "")[:max_length]


def get_zzz_runtime_guard() -> dict:
    reasons = []
    parsed = urlparse(str(ZZZ_API_BASE or "").strip())
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    if not has_configured_key(ZZZ_API_KEY):
        reasons.append("api_key_unavailable")
    if ZZZ_REQUIRE_ENCRYPTED_KEY:
        zzz_resolution = KEY_RESOLUTION_AUDIT.get("ZZZ_API_KEY", {})
        if zzz_resolution.get("source") != "enc":
            reasons.append("encrypted_key_required")
    if ZZZ_FAIL_CLOSED:
        if not ZZZ_SECURITY_PROTOCOL_ENABLED:
            reasons.append("security_protocol_disabled")
        if not ZZZ_OBFUSCATE_RESPONSE:
            reasons.append("response_obfuscation_disabled")
        if not ZZZ_SECRET_PROTOCOL_KEY:
            reasons.append("missing_secret_protocol_key")
        if scheme != "https":
            reasons.append("non_https_base_url")
        if host != "api.zhizengzeng.com":
            reasons.append("unexpected_zzz_host")
        if not PRIVACY_MODE:
            reasons.append("privacy_mode_required")
    return {
        "ready": len(reasons) == 0,
        "reasons": reasons,
        "base_url": ZZZ_API_BASE,
        "host": host,
        "scheme": scheme,
    }


def is_zzz_provider_ready() -> bool:
    return bool(get_zzz_runtime_guard().get("ready"))


OPENAI_ENABLED = has_configured_key(OPENAI_API_KEY)
HF_ENABLED = has_configured_key(HF_API_KEY)
TOGETHER_ENABLED = has_configured_key(TOGETHER_API_KEY)
OPENROUTER_KEY_SLOT = 1
if not has_configured_key(OPENROUTER_API_KEY) and has_configured_key(OPENROUTER_API_KEY_2):
    OPENROUTER_API_KEY = OPENROUTER_API_KEY_2
    OPENROUTER_KEY_SLOT = 2
OPENROUTER_ENABLED = has_configured_key(OPENROUTER_API_KEY)
GROQ_ENABLED = has_configured_key(GROQ_API_KEY)
GEMINI_ENABLED = has_configured_key(GEMINI_API_KEY)
NVIDIA_ENABLED = has_configured_key(NVIDIA_API_KEY)
ZZZ_ENABLED = has_configured_key(ZZZ_API_KEY)

SUPPORTED_MODEL_CHOICES = {"auto", "tinyllama", "gpt2", "openai", "openrouter", "groq", "gemini", "nvidia", "zhizengzeng", "huggingface", "together"}


def select_preferred_cloud_model(for_execution: bool = False) -> str | None:
    if for_execution and NVIDIA_ENABLED:
        return "nvidia"

    availability = {
        "gemini": GEMINI_ENABLED,
        "openai": OPENAI_ENABLED,
        "openrouter": OPENROUTER_ENABLED,
        "groq": GROQ_ENABLED,
        "zhizengzeng": is_zzz_provider_ready(),
        "together": TOGETHER_ENABLED,
        "huggingface": HF_ENABLED,
    }

    alias_map = {
        "gemin": "gemini",
        "google": "gemini",
        "google-gemini": "gemini",
        "zzz": "zhizengzeng",
        "zzzapi": "zhizengzeng",
        "zzz-api": "zhizengzeng",
        "nvidia-api": "nvidia",
        "nvapi": "nvidia",
    }
    preferred = alias_map.get(CHAT_PREFERRED_PROVIDER, CHAT_PREFERRED_PROVIDER)
    cloud_order = ["gemini", "openai", "openrouter", "groq", "zhizengzeng", "together", "huggingface"]
    if preferred in cloud_order:
        cloud_order = [preferred] + [item for item in cloud_order if item != preferred]

    for provider_key in cloud_order:
        if availability.get(provider_key):
            return provider_key
    return None

# Lazy initialize local GPT-2 so importing the server does not block on model downloads.
gpt2_generator = None
gpt2_init_attempted = False


def has_ml_runtime_backend() -> bool:
    return any(
        importlib.util.find_spec(module_name) is not None
        for module_name in ["torch", "tensorflow", "flax"]
    )


def get_gpt2_status() -> dict:
    return {
        "backend": GPT2_BACKEND,
        "sidecar_url": GPT2_SIDECAR_URL,
        "ml_runtime_available": has_ml_runtime_backend(),
        "transformers_available": importlib.util.find_spec("transformers") is not None,
        "local_generator_ready": gpt2_generator is not None,
    }


def get_gpt2_generator():
    global gpt2_generator, gpt2_init_attempted

    if GPT2_BACKEND == "sidecar":
        return None
    if gpt2_generator is not None:
        return gpt2_generator
    if gpt2_init_attempted:
        return None
    if not has_ml_runtime_backend():
        logging.warning("GPT-2 local backend unavailable: no torch/tensorflow/flax runtime found")
        return None
    if importlib.util.find_spec("transformers") is None:
        logging.warning("GPT-2 local backend unavailable: transformers is not installed")
        return None

    gpt2_init_attempted = True
    try:
        transformers = importlib.import_module('transformers')
        gpt2_generator = transformers.pipeline(
            'text-generation', model='gpt2', device=-1
        )
        logging.info("GPT-2 initialized successfully")
    except Exception as e:
        gpt2_generator = None
        logging.error(f"GPT-2 initialization failed: {e}")

    return gpt2_generator

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    agent_type = db.Column(db.String(50), nullable=True)
    model_used = db.Column(db.String(50), nullable=False)
    signal_tags = db.Column(db.Text, nullable=True)
    routing_reason = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


class AgentTask(db.Model):
    """Stores tasks for specialized agents like 小編."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    goals = db.Column(db.Text, nullable=True)
    style_guidelines = db.Column(db.Text, nullable=True)
    constraints = db.Column(db.Text, nullable=True)
    output_format = db.Column(db.String(200), nullable=True)
    model_hint = db.Column(db.String(50), nullable=True)
    assigned_agent = db.Column(db.String(50), nullable=True)
    agent_label = db.Column(db.String(100), nullable=True)
    issue_tags = db.Column(db.Text, nullable=True)
    learning_report = db.Column(db.Text, nullable=True)
    workflow_parent_id = db.Column(db.Integer, nullable=True)
    workflow_stage = db.Column(db.String(80), nullable=True)
    workflow_run_id = db.Column(db.String(120), nullable=True)
    workflow_relations = db.Column(db.Text, nullable=True)
    source_channel = db.Column(db.String(80), nullable=True)
    external_ref = db.Column(db.String(160), nullable=True)
    status = db.Column(db.String(50), default='pending')
    result = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())


class XiaobianProfile(db.Model):
    """Stores user preferences and context for the 小編 agent."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)  # JSON string
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())


class DispatcherRule(db.Model):
    """Learns routing patterns so the dispatcher can improve over time."""
    id = db.Column(db.Integer, primary_key=True)
    pattern = db.Column(db.String(120), unique=True, nullable=False)
    target_agent = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(50), default='user_feedback')
    notes = db.Column(db.Text, nullable=True)
    hit_count = db.Column(db.Integer, default=1)
    last_matched_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())


class AgentSignal(db.Model):
    """Persistent signal-memory for common words and routing hints."""
    __table_args__ = (
        db.UniqueConstraint('agent_key', 'signal', name='uq_agent_signal'),
    )

    id = db.Column(db.Integer, primary_key=True)
    agent_key = db.Column(db.String(50), nullable=False)
    signal = db.Column(db.String(120), nullable=False)
    source = db.Column(db.String(50), default='runtime')
    weight = db.Column(db.Integer, default=1)
    hit_count = db.Column(db.Integer, default=1)
    last_seen_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())


class CNSHeartbeat(db.Model):
    """Tracks proactive CNS cycles and their results."""
    id = db.Column(db.Integer, primary_key=True)
    cycle_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class AgentNotification(db.Model):
    """Lightweight event notifications emitted by agents/CNS for realtime UI updates."""
    id = db.Column(db.Integer, primary_key=True)
    agent_key = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), default='info')
    category = db.Column(db.String(50), default='runtime')
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    details = db.Column(db.Text, nullable=True)
    related_task_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


ISSUE_TAG_RULES = {
    "ui_ux": ["ui", "ux", "介面", "版面", "排版", "視覺", "設計"],
    "color": ["顏色", "配色", "色彩", "色號"],
    "typography": ["字體", "字級", "字距", "排印"],
    "layout": ["佈局", "布局", "版面", "grid", "欄位"],
    "readability": ["可讀性", "易讀", "閱讀", "資訊層級"],
    "accessibility": ["無障礙", "accessibility", "對比", "contrast"],
    "performance": ["效能", "performance", "速度", "載入"],
    "bug": ["錯誤", "bug", "問題", "異常", "失敗"],
    "content": ["文案", "內容", "敘述", "標題"],
    "api": ["api", "endpoint", "服務", "串接"],
    "security": ["資安", "安全", "漏洞", "風險", "威脅", "憑證", "token", "api key", "security", "hardening"],
    "database": ["資料庫", "sqlite", "sql", "schema", "table"],
    "ops": ["部署", "環境", "外接硬碟", "資料夾", "路徑", "log", "監控"],
    "research": ["研究", "分析", "整理", "比較", "摘要"],
    "mental_health": ["精神", "心理", "心理學", "精神疾病", "憂鬱", "焦慮", "創傷", "求生指南", "mental", "psychology", "psychiatry"],
    "neuroscience": ["腦神經", "神經科學", "神經", "neuroscience", "brain", "cognitive"],
    "bible": ["聖經", "經文", "舊約", "新約", "福音", "bible", "scripture"],
}

SAFETY_BLACK_GRAY_TERMS = [
    "黑灰產",
    "黑產",
    "灰產",
    "詐騙",
    "詐欺",
    "洗錢",
    "博彩",
    "賭博",
    "彩票",
    "暗網",
    "盜刷",
    "非法交易",
    "代收代付",
    "勒索",
    "入侵",
    "木馬",
]

SAFETY_PROMOTION_TERMS = [
    "投注",
    "上分",
    "保證獲利",
    "快速賺",
    "開戶送彩金",
    "刷流水",
    "盤口",
    "賭盤",
    "邀請碼",
    "套利",
    "對沖套利",
]

SAFETY_DEFENSIVE_CONTEXT_TERMS = [
    "防護",
    "防詐",
    "資安",
    "安全",
    "稽核",
    "合規",
    "阻擋",
    "攔截",
    "偵測",
    "風險",
    "教育",
    "研究",
    "防禦",
    "白帽",
    "incident",
    "compliance",
    "security",
    "audit",
    "defense",
]

DEFAULT_DISPATCH_RULES = {}
for agent_key in ["general", "xiaobian", "engineer", "researcher", "proclaimer", "whitehat"]:
    spec = get_agent_spec(agent_key)
    if not spec:
        continue
    canonical_key = _fuse_agent_key(agent_key) or agent_key
    bucket = DEFAULT_DISPATCH_RULES.setdefault(canonical_key, [])
    for tag in list(spec.signal_tags or []):
        if tag and tag not in bucket:
            bucket.append(tag)

CNS_RUNTIME = {
    "thread_started": False,
    "startup_bootstrap_started": False,
    "startup_bootstrap_completed": False,
    "startup_bootstrap_status": "idle",
    "last_cycle_at": None,
    "last_cycle_summary": "尚未執行",
    "last_daily_job_date": None,
    "last_daily_job_at": None,
    "last_daily_job_summary": "尚未執行每日任務",
    "last_security_index": None,
    "last_security_signature": None,
    "chatgpt_bridge_last_at": None,
    "chatgpt_bridge_last_status": "idle",
    "chatgpt_bridge_last_message": "尚未執行",
    "chatgpt_bridge_full_last_at": None,
    "chatgpt_bridge_full_last_status": "idle",
    "chatgpt_bridge_full_last_message": "尚未執行",
    "chatgpt_bridge_ingest_last_at": None,
    "chatgpt_bridge_ingest_last_status": "idle",
    "chatgpt_bridge_ingest_last_message": "尚未執行",
}
CHATGPT_BRIDGE_LAST_TS = 0.0
CHATGPT_BRIDGE_LOCK = threading.Lock()
FULL_SYNC_JOB_LOCK = threading.Lock()
FULL_SYNC_JOBS: dict[str, dict] = {}
FULL_SYNC_JOB_ORDER: list[str] = []

TOPIC_KEYWORDS = {
    "mental": ["精神", "心理", "mental", "psychiatry", "psychiatric"],
    "psychology": ["心理學", "psychology", "counseling", "cognitive", "behavior"],
    "mental_survival": ["精神疾病", "求生指南", "危機", "自救", "suicide", "depression", "anxiety"],
    "neuroscience": ["腦神經", "神經科學", "neuroscience", "brain", "neuron", "神經"],
    "bible": ["聖經", "經文", "新約", "舊約", "福音", "bible", "scripture", "gospel"],
}

RESEARCH_FILE_EXTENSIONS = {
    ".md", ".txt", ".pdf", ".doc", ".docx", ".rtf", ".html", ".htm", ".json", ".csv", ".epub"
}
TEXT_SNIFF_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".json", ".csv", ".rtf"}
SCAN_SKIP_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules", ".cache", ".Trash",
    ".Spotlight-V100", ".fseventsd", "Library", "System"
}


def _parse_json_text(raw_value, fallback):
    if not raw_value:
        return fallback
    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_text(value, fallback_text: str = "") -> str:
    if value is None:
        return fallback_text
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _normalize_workflow_relations(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = _parse_json_text(value, {})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _task_is_blocked(task: AgentTask) -> tuple[bool, list[int]]:
    terminal_statuses = {"completed", "failed", "cancelled"}
    current_status = str(task.status or "").lower()
    if current_status in terminal_statuses:
        return (False, [])

    blocked_by = []
    relations = _normalize_workflow_relations(task.workflow_relations)
    relation_blockers = relations.get("blocked_by") if isinstance(relations.get("blocked_by"), list) else []
    for item in relation_blockers:
        try:
            blocked_by.append(int(item))
        except (TypeError, ValueError):
            continue
    if task.workflow_parent_id:
        blocked_by.append(int(task.workflow_parent_id))

    unresolved = []
    for dependency_id in sorted(set(blocked_by)):
        dependency_task = db.session.get(AgentTask, dependency_id)
        if not dependency_task or str(dependency_task.status or "").lower() != "completed":
            unresolved.append(dependency_id)
    return (len(unresolved) > 0, unresolved)


def _task_blocker_statuses(task: AgentTask) -> list[dict]:
    blocked, blocked_by = _task_is_blocked(task)
    if not blocked:
        return []
    details = []
    for dependency_id in blocked_by:
        dependency_task = db.session.get(AgentTask, dependency_id)
        details.append({
            "task_id": dependency_id,
            "status": str((dependency_task.status if dependency_task else "missing") or "missing").lower(),
            "title": dependency_task.title if dependency_task else "",
        })
    return details


def _build_feed_snapshot(user_message: str, ai_response: str, agent_key: str, model_used: str, routing: dict | None = None) -> dict:
    routing_payload = routing if isinstance(routing, dict) else {}
    return {
        "agent": _fuse_agent_key(agent_key) or agent_key or "general",
        "model_used": model_used or "unknown",
        "user_preview": _bridge_string((user_message or "").strip().replace("\n", " "), CONVERSATION_FEED_MAX_PREVIEW),
        "ai_preview": _bridge_string((ai_response or "").strip().replace("\n", " "), CONVERSATION_FEED_MAX_PREVIEW),
        "signal_tags": routing_payload.get("signal_tags", []),
        "routing_reason": routing_payload.get("reason", ""),
        "captured_at": datetime.now().isoformat(),
    }


def _n8n_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Perob-Webhook-Secret"] = N8N_WEBHOOK_SECRET
    return headers


def _dispatch_n8n_event(webhook_url: str, event_type: str, payload: dict):
    if not N8N_ENABLED or not webhook_url:
        return {"status": "disabled", "event_type": event_type}
    try:
        response = requests.post(
            webhook_url,
            headers=_n8n_headers(),
            json={
                "event_type": event_type,
                "source": "perob",
                "sent_at": datetime.now().isoformat(),
                "payload": payload,
            },
            timeout=N8N_TIMEOUT_SECONDS,
        )
        return {
            "status": "sent" if response.ok else "failed",
            "code": response.status_code,
            "event_type": event_type,
        }
    except Exception as exc:
        logging.warning("n8n event dispatch failed for %s: %s", event_type, exc)
        return {
            "status": "failed",
            "event_type": event_type,
            "error": str(exc),
        }


def _dispatch_n8n_event_async(webhook_url: str, event_type: str, payload: dict):
    def _run():
        try:
            with app.app_context():
                _dispatch_n8n_event(webhook_url, event_type, payload)
        finally:
            _remove_db_session_safely()

    threading.Thread(target=_run, daemon=True).start()


ALLOWED_UPLOAD_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".mp4",
    ".mov",
    ".m4v",
    ".wav",
    ".mp3",
    ".txt",
    ".json",
}


def _allowed_upload_extension(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return bool(suffix and suffix in ALLOWED_UPLOAD_EXTENSIONS)


def _guess_content_type(filename: str) -> str:
    content_type, _ = mimetypes.guess_type(filename or "")
    return content_type or "application/octet-stream"


def _merge_learning_report(task: AgentTask, patch_data: dict) -> dict:
    current = _parse_json_text(task.learning_report, {})
    if not isinstance(current, dict):
        current = {}
    if isinstance(patch_data, dict):
        current.update(patch_data)
    task.learning_report = json.dumps(current, ensure_ascii=False)
    return current


def _video_request_payload(data: dict, task_id: int | None = None) -> dict:
    now_iso = datetime.now().isoformat()
    title = str(data.get("title", "") or "").strip()
    description = str(data.get("description", "") or "").strip()
    user_prompt = str(data.get("user_prompt", "") or "").strip()
    creative_submode = str(data.get("creative_submode", "three_minute_video_generate") or "three_minute_video_generate").strip()
    workflow_engine = str(data.get("video_workflow_engine", "seedance2_n8n") or "seedance2_n8n").strip()
    aspect_ratio = str(data.get("aspect_ratio", SEEDANCE_DEFAULT_ASPECT_RATIO) or SEEDANCE_DEFAULT_ASPECT_RATIO).strip()
    resolution = str(data.get("resolution", SEEDANCE_DEFAULT_RESOLUTION) or SEEDANCE_DEFAULT_RESOLUTION).strip()
    duration = max(
        SEEDANCE_TARGET_MIN_FINAL_DURATION_SECONDS,
        int(data.get("target_final_duration_seconds", SEEDANCE_TARGET_MIN_FINAL_DURATION_SECONDS) or SEEDANCE_TARGET_MIN_FINAL_DURATION_SECONDS),
    )
    source_assets = data.get("source_assets")
    if not isinstance(source_assets, list):
        source_assets = []

    return {
        "task_id": task_id,
        "title": title,
        "description": description,
        "user_prompt": user_prompt,
        "creative_submode": creative_submode,
        "video_workflow_engine": workflow_engine,
        "provider": SEEDANCE_PROVIDER,
        "seedance_enabled": SEEDANCE_ENABLED,
        "text_model": SEEDANCE_TEXT_MODEL,
        "image_model": SEEDANCE_IMAGE_MODEL,
        "target_final_duration_seconds": duration,
        "segment_duration_seconds": int(
            data.get("segment_duration_seconds", SEEDANCE_DEFAULT_SEGMENT_DURATION) or SEEDANCE_DEFAULT_SEGMENT_DURATION
        ),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "subtitle_mode": str(
            data.get("subtitle_mode", "bilingual_caption_burn" if VIDEO_DEFAULT_BILINGUAL_CAPTIONS else "none") or ""
        ).strip(),
        "audio_mode": str(
            data.get("audio_mode", "royalty_free_theme_audio" if VIDEO_DEFAULT_THEME_AUDIO else "none") or ""
        ).strip(),
        "narration_mode": str(
            data.get("narration_mode", "zh_tw_mature_narration" if VIDEO_DEFAULT_ZH_TW_NARRATION else "none") or ""
        ).strip(),
        "narration_locale": VIDEO_NARRATION_LOCALE,
        "narration_tone": VIDEO_NARRATION_TONE,
        "narration_provider": VIDEO_NARRATION_VOICE_PROVIDER,
        "caption_style": VIDEO_CAPTION_STYLE,
        "desktop_root": str(VIDEO_DESKTOP_ROOT),
        "source_assets_dir": str(VIDEO_SOURCE_ASSETS_DIR),
        "segments_dir": str(VIDEO_SEGMENTS_DIR),
        "final_videos_dir": str(VIDEO_FINAL_DIR),
        "audio_library_dir": str(VIDEO_AUDIO_LIBRARY_DIR),
        "source_assets": source_assets,
        "received_at": now_iso,
    }


def _n8n_request_authorized(req) -> bool:
    if not N8N_WEBHOOK_SECRET:
        return True
    candidate = (
        req.headers.get("X-Perob-Webhook-Secret")
        or req.headers.get("X-N8N-Secret")
        or req.args.get("secret")
        or ""
    )
    return hmac.compare_digest(str(candidate), str(N8N_WEBHOOK_SECRET))


def emit_task_lifecycle_event(task: AgentTask, event_type: str, extra: dict | None = None):
    payload = {
        "task": serialize_agent_task(task),
        "progress": serialize_task_progress(task),
        "extra": extra or {},
    }
    _dispatch_n8n_event_async(N8N_TASK_EVENT_WEBHOOK, event_type, payload)


def emit_chat_lifecycle_event(event_type: str, payload: dict):
    _dispatch_n8n_event_async(N8N_CHAT_EVENT_WEBHOOK, event_type, payload)


def _seedance_callback_authorized(req) -> bool:
    if not N8N_SEEDANCE_CALLBACK_SECRET:
        return True
    body = req.get_json(silent=True) or {}
    candidate = (
        req.headers.get("X-Perob-Webhook-Secret")
        or req.headers.get("X-N8N-Secret")
        or req.args.get("secret")
        or body.get("callback_secret")
        or ""
    )
    return hmac.compare_digest(str(candidate), str(N8N_SEEDANCE_CALLBACK_SECRET))


def create_conversation_feed_task(
    user_message: str,
    ai_response: str,
    agent_key: str,
    model_used: str,
    routing: dict | None = None,
    source_channel: str = "chat",
) -> AgentTask | None:
    if not CONVERSATION_FEED_ENABLED:
        return None

    snapshot = _build_feed_snapshot(user_message, ai_response, agent_key, model_used, routing=routing)
    feed_task = AgentTask(
        title=f"對話餵養任務（{snapshot['agent']}）",
        description=(user_message or "")[:8000],
        goals="將本輪對話轉為後續學習、workflow 與 n8n 可重用事件",
        style_guidelines="摘要化、結構化、可供自動化流程復用",
        constraints="不得暴露敏感金鑰；只保留必要對話摘要",
        output_format="feed_snapshot",
        model_hint="system",
        assigned_agent="learner",
        agent_label="learner.feed_memory",
        issue_tags=_json_text(snapshot.get("signal_tags", [])),
        learning_report=_json_text(snapshot),
        workflow_stage="conversation_feed",
        workflow_run_id=f"chat_{uuid.uuid4().hex[:12]}",
        workflow_relations=_json_text({"derived_from": routing or {}}),
        source_channel=source_channel,
        status="completed",
        result=_json_text(snapshot),
    )
    db.session.add(feed_task)
    db.session.commit()
    emit_task_lifecycle_event(feed_task, "task.feed.created", {"feed_type": "conversation"})
    _dispatch_n8n_event_async(N8N_FEED_EVENT_WEBHOOK, "feed.conversation.created", snapshot)
    return feed_task


def extract_issue_tags(*texts):
    """Infer issue tags from task text so the agent can report learned labels."""
    joined = " ".join(text for text in texts if text).lower()
    detected_tags = []
    for tag, keywords in ISSUE_TAG_RULES.items():
        if any(keyword.lower() in joined for keyword in keywords):
            detected_tags.append(tag)

    if not detected_tags and joined:
        detected_tags.append("general")
    return detected_tags


def infer_agent_label(task_data: dict) -> str:
    explicit_label = (task_data.get('agent_label') or '').strip()
    if explicit_label:
        return explicit_label

    assigned_agent = (task_data.get('assigned_agent') or '').strip()
    if assigned_agent:
        return f"{assigned_agent}.primary"

    text = " ".join(
        str(task_data.get(field, ''))
        for field in ['title', 'description', 'goals', 'style_guidelines', 'constraints']
    ).lower()

    if any(keyword in text for keyword in ["設計", "視覺", "ui", "ux", "版面", "字體", "顏色"]):
        return "xiaobian.design_reviewer"
    if any(keyword in text for keyword in ["研究", "分析", "比較", "摘要", "整理"]):
        return "researcher.knowledge_scout"
    if any(keyword in text for keyword in ["資安", "安全", "漏洞", "風險", "威脅", "security", "hardening", "api key"]):
        return "proclaimer.security_guardian" if FUSE_WHITEHAT_TO_PROCLAIMER else "whitehat.security_guardian"
    if any(keyword in text for keyword in ["錯誤", "bug", "異常", "除錯"]):
        return "engineer.issue_resolver"
    return "general.coordinator"


def summarize_reported_issues(task_data: dict, issue_tags: list) -> list:
    text_sources = [
        task_data.get('description', ''),
        task_data.get('goals', ''),
        task_data.get('constraints', ''),
        task_data.get('style_guidelines', ''),
    ]
    combined = "\n".join(source for source in text_sources if source).strip()
    if not combined:
        return ["未提供足夠的任務描述，暫時無法判斷具體問題。"]

    segments = re.split(r'[。\n；;]+', combined)
    issues = []
    for segment in segments:
        normalized = segment.strip(" -•\t")
        if normalized:
            issues.append(normalized)
        if len(issues) >= 5:
            break

    if not issues:
        issues.append("需要補充更多上下文才能建立問題摘要。")

    if "accessibility" in issue_tags:
        issues.append("請額外檢查文字對比與互動元件的可達性。")

    return issues[:5]


def build_learning_report(task_data: dict, response_text: str, agent_label: str = None, issue_tags: list = None) -> dict:
    source_texts = [
        task_data.get('title', ''),
        task_data.get('description', ''),
        task_data.get('goals', ''),
        task_data.get('style_guidelines', ''),
        task_data.get('constraints', ''),
    ]
    resolved_issue_tags = issue_tags or extract_issue_tags(*source_texts)
    resolved_agent_label = agent_label or infer_agent_label(task_data)
    reported_issues = summarize_reported_issues(task_data, resolved_issue_tags)
    response_preview = (response_text or "").strip().replace("\n", " ")
    learned_signal_tags = infer_signal_tags(*source_texts, response_preview)

    return {
        "agent_label": resolved_agent_label,
        "issue_tags": resolved_issue_tags,
        "signal_tags": learned_signal_tags,
        "reported_issues": reported_issues,
        "learning_summary": (
            "智能體已根據任務內容整理問題標籤，後續回覆可沿用這些標籤持續學習。"
        ),
        "response_preview": response_preview[:280],
    }


def ensure_database_schema():
    """Lightweight schema patching for existing SQLite databases."""
    inspector = db.inspect(db.engine)
    statements = []

    if inspector.has_table("chat_history"):
        chat_columns = {column["name"] for column in inspector.get_columns("chat_history")}
        if "agent_type" not in chat_columns:
            statements.append("ALTER TABLE chat_history ADD COLUMN agent_type VARCHAR(50)")
        if "signal_tags" not in chat_columns:
            statements.append("ALTER TABLE chat_history ADD COLUMN signal_tags TEXT")
        if "routing_reason" not in chat_columns:
            statements.append("ALTER TABLE chat_history ADD COLUMN routing_reason TEXT")

    if inspector.has_table("agent_task"):
        task_columns = {column["name"] for column in inspector.get_columns("agent_task")}
        if "assigned_agent" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN assigned_agent VARCHAR(50)")
        if "agent_label" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN agent_label VARCHAR(100)")
        if "issue_tags" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN issue_tags TEXT")
        if "learning_report" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN learning_report TEXT")
        if "workflow_parent_id" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN workflow_parent_id INTEGER")
        if "workflow_stage" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN workflow_stage VARCHAR(80)")
        if "workflow_run_id" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN workflow_run_id VARCHAR(120)")
        if "workflow_relations" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN workflow_relations TEXT")
        if "source_channel" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN source_channel VARCHAR(80)")
        if "external_ref" not in task_columns:
            statements.append("ALTER TABLE agent_task ADD COLUMN external_ref VARCHAR(160)")

    if inspector.has_table("agent_notification"):
        notification_columns = {column["name"] for column in inspector.get_columns("agent_notification")}
        if "category" not in notification_columns:
            statements.append("ALTER TABLE agent_notification ADD COLUMN category VARCHAR(50)")
        if "related_task_id" not in notification_columns:
            statements.append("ALTER TABLE agent_notification ADD COLUMN related_task_id INTEGER")
        if "is_read" not in notification_columns:
            statements.append("ALTER TABLE agent_notification ADD COLUMN is_read BOOLEAN")

    for statement in statements:
        db.session.execute(db.text(statement))

    if statements:
        db.session.commit()

    if inspector.has_table("chat_history"):
        _ensure_chat_history_long_text_columns()


def _ensure_chat_history_long_text_columns():
    """Upgrade SQLite chat_history columns so long external conversations are not truncated."""
    with db.engine.begin() as conn:
        columns = conn.execute(db.text("PRAGMA table_info(chat_history)")).fetchall()
        if not columns:
            return

        type_map = {str(row[1]): str(row[2]).upper() for row in columns}
        user_type = type_map.get("user_message", "")
        ai_type = type_map.get("ai_response", "")
        if user_type == "TEXT" and ai_type == "TEXT":
            return

        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS chat_history__new (
                id INTEGER PRIMARY KEY,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                model_used VARCHAR(50) NOT NULL,
                timestamp DATETIME,
                agent_type VARCHAR(50),
                signal_tags TEXT,
                routing_reason TEXT
            )
        """))
        conn.execute(db.text("""
            INSERT INTO chat_history__new (
                id, user_message, ai_response, model_used, timestamp, agent_type, signal_tags, routing_reason
            )
            SELECT
                id, user_message, ai_response, model_used, timestamp, agent_type, signal_tags, routing_reason
            FROM chat_history
        """))
        conn.execute(db.text("DROP TABLE chat_history"))
        conn.execute(db.text("ALTER TABLE chat_history__new RENAME TO chat_history"))


def serialize_agent_task(task: AgentTask) -> dict:
    assigned_agent = _fuse_agent_key(task.assigned_agent) or task.assigned_agent
    return {
        'task_id': task.id,
        'title': task.title,
        'description': task.description,
        'goals': task.goals,
        'style_guidelines': task.style_guidelines,
        'constraints': task.constraints,
        'output_format': task.output_format,
        'model_hint': task.model_hint,
        'assigned_agent': assigned_agent,
        'agent_label': _normalize_agent_label_with_fusion(task.agent_label, assigned_agent=assigned_agent),
        'issue_tags': _parse_json_text(task.issue_tags, []),
        'learning_report': _parse_json_text(task.learning_report, {}),
        'workflow_parent_id': task.workflow_parent_id,
        'workflow_stage': task.workflow_stage or "",
        'workflow_run_id': task.workflow_run_id or "",
        'workflow_relations': _normalize_workflow_relations(task.workflow_relations),
        'source_channel': task.source_channel or "",
        'external_ref': task.external_ref or "",
        'status': task.status,
        'result': task.result,
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
    }


def serialize_task_progress(task: AgentTask) -> dict:
    assigned_agent = _fuse_agent_key(task.assigned_agent) or 'general'
    blocked, blocked_by = _task_is_blocked(task)
    learning_report = _parse_json_text(task.learning_report, {})
    video_result = learning_report.get("video_result", {}) if isinstance(learning_report, dict) else {}
    return {
        'task_id': task.id,
        'title': task.title,
        'status': str(task.status or 'pending'),
        'assigned_agent': assigned_agent,
        'agent_label': _normalize_agent_label_with_fusion(task.agent_label, assigned_agent=assigned_agent),
        'workflow_stage': task.workflow_stage or "",
        'workflow_run_id': task.workflow_run_id or "",
        'workflow_parent_id': task.workflow_parent_id,
        'source_channel': task.source_channel or "",
        'blocked': blocked,
        'blocked_by': blocked_by,
        'created_at': task.created_at.isoformat() if task.created_at else "",
        'updated_at': task.updated_at.isoformat() if task.updated_at else "",
        'result_preview': _bridge_string(str(task.result or ""), 180),
        'result_video_url': str(video_result.get('result_video_url', '') or ''),
        'final_composition_url': str(video_result.get('final_composition_url', '') or ''),
        'video_result': video_result if isinstance(video_result, dict) else {},
    }


def serialize_dispatcher_rule(rule: DispatcherRule) -> dict:
    return {
        'rule_id': rule.id,
        'pattern': rule.pattern,
        'target_agent': rule.target_agent,
        'source': rule.source,
        'notes': rule.notes,
        'hit_count': rule.hit_count,
        'last_matched_message': rule.last_matched_message,
        'created_at': rule.created_at.isoformat(),
        'updated_at': rule.updated_at.isoformat(),
    }


def serialize_agent_signal(signal: AgentSignal) -> dict:
    return {
        'signal_id': signal.id,
        'agent_key': signal.agent_key,
        'signal': signal.signal,
        'source': signal.source,
        'weight': signal.weight,
        'hit_count': signal.hit_count,
        'last_seen_message': signal.last_seen_message,
        'created_at': signal.created_at.isoformat(),
        'updated_at': signal.updated_at.isoformat(),
    }


def serialize_heartbeat(heartbeat: CNSHeartbeat) -> dict:
    return {
        'heartbeat_id': heartbeat.id,
        'cycle_type': heartbeat.cycle_type,
        'status': heartbeat.status,
        'summary': heartbeat.summary,
        'details': _parse_json_text(heartbeat.details, heartbeat.details),
        'created_at': heartbeat.created_at.isoformat(),
    }


def serialize_notification(notification: AgentNotification) -> dict:
    return {
        'notification_id': notification.id,
        'agent_key': notification.agent_key,
        'level': notification.level,
        'category': notification.category,
        'title': notification.title,
        'message': notification.message,
        'details': _parse_json_text(notification.details, notification.details),
        'related_task_id': notification.related_task_id,
        'is_read': bool(notification.is_read),
        'created_at': notification.created_at.isoformat(),
    }


def emit_notification(
    agent_key: str,
    title: str,
    message: str,
    level: str = 'info',
    category: str = 'runtime',
    details=None,
    related_task_id: int = None,
):
    payload = details
    if isinstance(details, (dict, list)):
        payload = json.dumps(details, ensure_ascii=False)
    elif details is None:
        payload = ""
    else:
        payload = str(details)

    notification = AgentNotification(
        agent_key=agent_key,
        level=level,
        category=category,
        title=title[:120],
        message=message[:500],
        details=payload,
        related_task_id=related_task_id,
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def describe_path(path: Path) -> dict:
    exists = path.exists()
    description = {
        'path': str(path),
        'exists': exists,
        'type': 'missing',
    }

    if not exists:
        return description

    if path.is_dir():
        description['type'] = 'directory'
        description['entries'] = len(list(path.iterdir()))
        description['size_bytes'] = sum(
            child.stat().st_size
            for child in path.rglob('*')
            if child.is_file()
        )
    else:
        description['type'] = 'file'
        description['size_bytes'] = path.stat().st_size

    return description


def describe_active_database_storage() -> dict:
    if IS_SQLITE_DB:
        payload = describe_path(DATABASE_PATH)
        payload.update({
            "backend": "sqlite",
            "uri": ACTIVE_DATABASE_URI_REDACTED,
        })
        return payload

    return {
        "path": str(DATABASE_PATH),
        "exists": bool(APP_DATABASE_URL),
        "type": "external_database",
        "backend": "postgresql",
        "uri": ACTIVE_DATABASE_URI_REDACTED,
    }


def list_mounted_volumes() -> list:
    volume_root = Path("/Volumes")
    if not volume_root.exists():
        return []

    volumes = []
    for item in sorted(volume_root.iterdir(), key=lambda candidate: candidate.name.lower()):
        is_system_alias = item.name == "Macintosh HD" and item.is_symlink()
        volumes.append({
            "name": item.name,
            "path": str(item),
            "exists": item.exists(),
            "is_symlink": item.is_symlink(),
            "is_system_alias": is_system_alias,
        })
    return volumes


def build_engineer_status_report() -> dict:
    framework = get_data_framework_summary()
    model = {
        "gpt2": get_gpt2_status(),
        "ollama_available": check_ollama_available(),
        "huggingface_key_configured": bool(HF_API_KEY),
        "together_key_configured": bool(TOGETHER_API_KEY),
    }
    cns = {
        "runtime": CNS_RUNTIME,
        "interval_seconds": PROACTIVE_INTERVAL_SECONDS,
        "enabled": ENABLE_PROACTIVE_CNS,
    }
    volumes = list_mounted_volumes()

    storage = framework["storage"]
    checks = []

    checks.append({
        "check": "data_root_exists",
        "ok": storage["data_root"]["exists"],
        "detail": storage["data_root"]["path"],
    })
    checks.append({
        "check": "instance_exists",
        "ok": storage["instance_dir"]["exists"],
        "detail": storage["instance_dir"]["path"],
    })
    checks.append({
        "check": "database_exists",
        "ok": storage["database"]["exists"],
        "detail": storage["database"]["path"],
    })
    checks.append({
        "check": "database_in_instance",
        "ok": (DATABASE_PATH.parent == INSTANCE_DIR) if IS_SQLITE_DB else True,
        "detail": f"{DATABASE_PATH.parent} vs {INSTANCE_DIR}" if IS_SQLITE_DB else "external database backend",
    })
    checks.append({
        "check": "cns_enabled",
        "ok": bool(cns.get("enabled")),
        "detail": cns.get("runtime", {}).get("last_cycle_summary", "N/A"),
    })
    checks.append({
        "check": "external_volume_connected",
        "ok": any(not entry.get("is_system_alias") for entry in volumes),
        "detail": ",".join(entry["name"] for entry in volumes),
    })

    critical_check_names = {"data_root_exists", "instance_exists", "database_exists"}
    if IS_SQLITE_DB:
        critical_check_names.add("database_in_instance")
    critical_checks = [entry for entry in checks if entry["check"] in critical_check_names]
    all_critical_ok = all(entry["ok"] for entry in critical_checks)
    warning_count = len([entry for entry in checks if not entry["ok"]])
    status = "healthy" if all_critical_ok and warning_count == 0 else "warning"

    return {
        "status": status,
        "checks": checks,
        "warning_count": warning_count,
        "framework_counts": framework["database"],
        "model_status": model,
        "mounted_volumes": volumes,
    }


def resolve_research_roots(custom_roots=None) -> list:
    roots = []
    if isinstance(custom_roots, list):
        for raw in custom_roots:
            try:
                candidate = Path(str(raw)).expanduser().resolve()
            except Exception:
                continue
            if candidate.exists():
                roots.append(candidate)

    default_roots = [DATA_ROOT, Path("/Volumes/Windsurf"), Path("/Volumes/智能體")]
    for candidate in default_roots:
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)

    return roots


def _path_depth(root: Path, child: Path) -> int:
    try:
        return len(child.relative_to(root).parts)
    except ValueError:
        return 0


def collect_local_research_data(custom_topics=None, custom_roots=None, max_results: int = 120, max_scan_files: int = 6000) -> dict:
    topic_keywords = TOPIC_KEYWORDS.copy()
    if isinstance(custom_topics, dict):
        for key, values in custom_topics.items():
            if isinstance(values, list) and values:
                topic_keywords[str(key)] = [str(value) for value in values if str(value).strip()]

    roots = resolve_research_roots(custom_roots)
    if not roots:
        return {
            "status": "no_roots",
            "topics": topic_keywords,
            "roots": [],
            "matches": [],
            "scanned_files": 0,
            "matched_count": 0,
        }

    matches = []
    scanned_files = 0
    matched_by_topic = {topic: 0 for topic in topic_keywords}

    for root in roots:
        if len(matches) >= max_results or scanned_files >= max_scan_files:
            break
        if not root.is_dir():
            continue

        for dir_path, dir_names, file_names in os.walk(root):
            current_dir = Path(dir_path)
            depth = _path_depth(root, current_dir)
            if depth > 6:
                dir_names[:] = []
                continue

            dir_names[:] = [
                name for name in dir_names
                if not name.startswith(".") and name not in SCAN_SKIP_DIRS
            ]

            for file_name in file_names:
                if scanned_files >= max_scan_files or len(matches) >= max_results:
                    break

                scanned_files += 1
                file_path = current_dir / file_name
                suffix = file_path.suffix.lower()
                if suffix not in RESEARCH_FILE_EXTENSIONS:
                    continue

                lowered_path = str(file_path).lower()
                topic_hits = []
                keyword_hits = []

                for topic, keywords in topic_keywords.items():
                    hit_terms = [keyword for keyword in keywords if keyword.lower() in lowered_path]
                    if hit_terms:
                        topic_hits.append(topic)
                        keyword_hits.extend(hit_terms)

                # For plain text files, sniff content header if filename/path does not hit keywords.
                if not topic_hits and suffix in TEXT_SNIFF_EXTENSIONS:
                    try:
                        if file_path.stat().st_size <= 1_500_000:
                            sample = file_path.read_text(errors="ignore")[:6000].lower()
                            for topic, keywords in topic_keywords.items():
                                hit_terms = [keyword for keyword in keywords if keyword.lower() in sample]
                                if hit_terms:
                                    topic_hits.append(topic)
                                    keyword_hits.extend(hit_terms)
                    except Exception:
                        continue

                if not topic_hits:
                    continue

                for topic in set(topic_hits):
                    matched_by_topic[topic] = matched_by_topic.get(topic, 0) + 1

                try:
                    size_bytes = file_path.stat().st_size
                except Exception:
                    size_bytes = 0

                matches.append({
                    "path": str(file_path),
                    "root": str(root),
                    "extension": suffix,
                    "size_bytes": size_bytes,
                    "topics": sorted(set(topic_hits)),
                    "keywords": sorted(set(keyword_hits))[:12],
                })

            if scanned_files >= max_scan_files or len(matches) >= max_results:
                break

    return {
        "status": "completed",
        "topics": topic_keywords,
        "roots": [str(root) for root in roots],
        "scanned_files": scanned_files,
        "matched_count": len(matches),
        "matched_by_topic": matched_by_topic,
        "matches": matches,
        "truncated": len(matches) >= max_results or scanned_files >= max_scan_files,
    }


def extract_dispatch_patterns(message: str, provided_patterns: list = None) -> list:
    """Build short routing patterns the dispatcher can learn from."""
    if provided_patterns:
        return [pattern.strip().lower() for pattern in provided_patterns if isinstance(pattern, str) and pattern.strip()]

    candidates = []
    lowered_message = (message or "").lower()

    for keyword_list in DEFAULT_DISPATCH_RULES.values():
        for keyword in keyword_list:
            if keyword.lower() in lowered_message:
                candidates.append(keyword.lower())

    ascii_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", lowered_message)
    candidates.extend(ascii_tokens[:4])

    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,12}", message or "")
    candidates.extend(chunk.lower() for chunk in chinese_chunks[:4])

    unique_patterns = []
    for pattern in candidates:
        normalized = pattern.strip()
        if normalized and normalized not in unique_patterns:
            unique_patterns.append(normalized)

    return unique_patterns[:6]


def infer_signal_tags(*texts, limit: int = 12) -> list:
    """Combine rule-based issue tags with common words extracted from runtime messages."""
    dynamic_terms = extract_signal_terms(*texts, limit=limit)
    issue_terms = extract_issue_tags(*texts)
    combined = []

    for term in issue_terms + dynamic_terms:
        normalized = str(term).strip().lower()
        if normalized and normalized not in combined:
            combined.append(normalized)

    return combined[:limit]


def serialize_agent_overview(agent_key: str) -> dict:
    canonical_key = _fuse_agent_key(agent_key) or str(agent_key or '').strip().lower()
    spec = get_agent_spec(canonical_key) or get_agent_spec(agent_key)
    if not spec:
        raise ValueError(f"Unknown agent: {agent_key}")

    partner_keys = [canonical_key]
    if canonical_key == 'proclaimer' and FUSE_WHITEHAT_TO_PROCLAIMER:
        partner_keys.append('whitehat')

    partner_specs = [get_agent_spec(key) for key in partner_keys]
    partner_specs = [row for row in partner_specs if row]

    merged_capabilities = []
    merged_signal_tags = []
    merged_collaborators = []
    merged_proactive_jobs = []

    for partner in partner_specs:
        for item in list(partner.capabilities or []):
            if item and item not in merged_capabilities:
                merged_capabilities.append(item)
        for item in list(partner.signal_tags or []):
            if item and item not in merged_signal_tags:
                merged_signal_tags.append(item)
        for item in list(partner.collaborators or []):
            normalized = _fuse_agent_key(item)
            if not normalized or normalized == canonical_key:
                continue
            if normalized not in merged_collaborators:
                merged_collaborators.append(normalized)
        for item in list(partner.proactive_jobs or []):
            if item and item not in merged_proactive_jobs:
                merged_proactive_jobs.append(item)

    learned_rows = AgentSignal.query.filter(AgentSignal.agent_key.in_(partner_keys)).order_by(
        AgentSignal.hit_count.desc(),
        AgentSignal.updated_at.desc(),
    ).limit(32).all()
    learned_signals = []
    seen_signal = set()
    for row in learned_rows:
        signal_key = str(getattr(row, 'signal', '') or '').strip().lower()
        if not signal_key or signal_key in seen_signal:
            continue
        seen_signal.add(signal_key)
        learned_signals.append(serialize_agent_signal(row))
        if len(learned_signals) >= 12:
            break

    description = str(spec.description or '')
    if canonical_key == 'proclaimer' and FUSE_WHITEHAT_TO_PROCLAIMER:
        description = f"{description}（已融合白帽守門能力）"

    return {
        **serialize_agent_spec(spec),
        'key': canonical_key,
        'description': description,
        'capabilities': merged_capabilities or list(spec.capabilities or []),
        'signal_tags': merged_signal_tags or list(spec.signal_tags or []),
        'collaborators': merged_collaborators or list(spec.collaborators or []),
        'proactive_jobs': merged_proactive_jobs or list(spec.proactive_jobs or []),
        'learned_signals': learned_signals,
    }


def list_agent_overviews() -> list[dict]:
    rows = []
    seen = set()
    for spec in list_agent_specs():
        canonical_key = _fuse_agent_key(spec.key) or spec.key
        if canonical_key in seen:
            continue
        seen.add(canonical_key)
        rows.append(serialize_agent_overview(canonical_key))
    return rows


def learn_agent_signals(agent_key: str, texts: list, source: str = 'runtime', message: str = '', boost: int = 1) -> list:
    terms = infer_signal_tags(*texts, limit=16)
    learned_signals = []

    for term in terms:
        signal = AgentSignal.query.filter_by(agent_key=agent_key, signal=term).first()
        if not signal:
            signal = AgentSignal(
                agent_key=agent_key,
                signal=term,
                source=source,
                weight=boost,
                hit_count=1,
                last_seen_message=message[:300],
            )
            db.session.add(signal)
        else:
            signal.source = source or signal.source
            signal.weight = max(signal.weight or 1, boost)
            signal.hit_count = (signal.hit_count or 0) + 1
            signal.last_seen_message = message[:300] or signal.last_seen_message

        learned_signals.append(signal)

    db.session.commit()
    return learned_signals


def seed_agent_signal_memory():
    seeded = 0
    existing_pairs = {
        (row.agent_key, row.signal)
        for row in db.session.query(AgentSignal.agent_key, AgentSignal.signal).all()
    }

    for spec in list_agent_specs():
        if spec.key not in DEFAULT_DISPATCH_RULES and spec.key not in {'dispatcher', 'learner'}:
            continue
        for tag in spec.signal_tags:
            normalized_tag = tag.lower().strip()
            if not normalized_tag:
                continue
            pair = (spec.key, normalized_tag)
            if pair in existing_pairs:
                continue

            db.session.add(
                AgentSignal(
                    agent_key=spec.key,
                    signal=normalized_tag,
                    source='seed',
                    weight=max(2, len(tag)),
                    hit_count=1,
                    last_seen_message=spec.description,
                )
            )
            existing_pairs.add(pair)
            seeded += 1

    if seeded:
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()


def match_agent_signals(message: str) -> dict:
    lowered = (message or '').lower()
    if not lowered:
        return {}

    matched_scores = {agent_key: 0 for agent_key in DEFAULT_DISPATCH_RULES}
    extracted_terms = infer_signal_tags(message, limit=20)

    for agent_key, keywords in DEFAULT_DISPATCH_RULES.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                matched_scores[agent_key] += max(3, len(keyword))

    for signal in AgentSignal.query.order_by(AgentSignal.hit_count.desc(), AgentSignal.updated_at.desc()).all():
        if signal.signal and signal.signal.lower() in lowered:
            signal_agent = _fuse_agent_key(signal.agent_key) or str(signal.agent_key or '').strip().lower()
            if signal_agent:
                matched_scores[signal_agent] = matched_scores.get(signal_agent, 0) + max(signal.weight or 1, signal.hit_count or 1)

    for term in extracted_terms:
        for agent_key, keywords in DEFAULT_DISPATCH_RULES.items():
            if term in [keyword.lower() for keyword in keywords]:
                matched_scores[agent_key] += 2

    return {agent_key: score for agent_key, score in matched_scores.items() if score > 0}


def upsert_dispatcher_rules(patterns: list, target_agent: str, source: str = 'user_feedback', notes: str = '', message: str = '') -> list:
    learned_rules = []
    canonical_target = _fuse_agent_key(target_agent) or str(target_agent or '').strip().lower()

    for pattern in patterns:
        rule = DispatcherRule.query.filter_by(pattern=pattern).first()
        if not rule:
            rule = DispatcherRule(
                pattern=pattern,
                target_agent=canonical_target,
                source=source,
                notes=notes,
                hit_count=1,
                last_matched_message=message[:300],
            )
            db.session.add(rule)
        else:
            rule.target_agent = canonical_target
            rule.source = source
            rule.notes = notes or rule.notes
            rule.hit_count = (rule.hit_count or 0) + 1
            rule.last_matched_message = message[:300] or rule.last_matched_message

        learned_rules.append(rule)

    db.session.commit()
    return learned_rules


def match_dispatcher_rule(message: str):
    lowered_message = (message or "").lower()
    if not lowered_message:
        return None, []

    scores = {}
    matched_rules = []
    rules = DispatcherRule.query.order_by(DispatcherRule.hit_count.desc(), DispatcherRule.updated_at.desc()).all()

    for rule in rules:
        pattern = (rule.pattern or "").lower()
        if pattern and pattern in lowered_message:
            matched_rules.append(rule)
            normalized_target = _fuse_agent_key(rule.target_agent) or str(rule.target_agent or '').strip().lower()
            if normalized_target:
                scores[normalized_target] = scores.get(normalized_target, 0) + max(rule.hit_count or 1, len(pattern))

    if not scores:
        return None, []

    selected_agent = max(scores.items(), key=lambda item: item[1])[0]
    return selected_agent, matched_rules[:5]


def get_proclaimer_detection_status(window_hours: int = 24) -> dict:
    hours = max(1, min(int(window_hours or 24), 168))
    window_start = datetime.now() - timedelta(hours=hours)

    target_agent_keys = ['proclaimer']
    if FUSE_WHITEHAT_TO_PROCLAIMER:
        target_agent_keys.append('whitehat')

    signal_count = AgentSignal.query.filter(AgentSignal.agent_key.in_(target_agent_keys)).count()
    rule_count = DispatcherRule.query.filter(DispatcherRule.target_agent.in_(target_agent_keys)).count()
    chat_total = ChatHistory.query.filter(ChatHistory.agent_type.in_(target_agent_keys)).count()
    task_total = AgentTask.query.filter(AgentTask.assigned_agent.in_(target_agent_keys)).count()

    recent_chat_hits = ChatHistory.query.filter(
        ChatHistory.agent_type.in_(target_agent_keys),
        ChatHistory.timestamp >= window_start,
    ).count()
    recent_task_hits = AgentTask.query.filter(
        AgentTask.assigned_agent.in_(target_agent_keys),
        AgentTask.updated_at >= window_start,
    ).count()

    latest_chat = ChatHistory.query.filter(ChatHistory.agent_type.in_(target_agent_keys)).order_by(ChatHistory.timestamp.desc()).first()
    latest_task = AgentTask.query.filter(AgentTask.assigned_agent.in_(target_agent_keys)).order_by(AgentTask.updated_at.desc()).first()

    if recent_chat_hits + recent_task_hits > 0:
        status = 'active'
    elif signal_count > 0 or rule_count > 0:
        status = 'ready'
    else:
        status = 'cold'

    return {
        'status': status,
        'window_hours': hours,
        'detector_online': status in {'active', 'ready'},
        'signal_count': signal_count,
        'rule_count': rule_count,
        'chat_total_hits': chat_total,
        'task_total_hits': task_total,
        'recent_chat_hits': recent_chat_hits,
        'recent_task_hits': recent_task_hits,
        'latest_chat_at': _bridge_iso(latest_chat.timestamp) if latest_chat else "",
        'latest_task_at': _bridge_iso(latest_task.updated_at) if latest_task else "",
        'aliases_merged': target_agent_keys if len(target_agent_keys) > 1 else [],
    }


def get_whitehat_detection_status(window_hours: int = 24) -> dict:
    if FUSE_WHITEHAT_TO_PROCLAIMER:
        merged = get_proclaimer_detection_status(window_hours=window_hours)
        return {
            **merged,
            'agent': 'whitehat',
            'fused_to': 'proclaimer',
            'alias_mode': 'fused_to_proclaimer',
        }

    hours = max(1, min(int(window_hours or 24), 168))
    window_start = datetime.now() - timedelta(hours=hours)

    signal_count = AgentSignal.query.filter_by(agent_key='whitehat').count()
    rule_count = DispatcherRule.query.filter_by(target_agent='whitehat').count()
    chat_total = ChatHistory.query.filter_by(agent_type='whitehat').count()
    task_total = AgentTask.query.filter_by(assigned_agent='whitehat').count()

    recent_chat_hits = ChatHistory.query.filter(
        ChatHistory.agent_type == 'whitehat',
        ChatHistory.timestamp >= window_start,
    ).count()
    recent_task_hits = AgentTask.query.filter(
        AgentTask.assigned_agent == 'whitehat',
        AgentTask.updated_at >= window_start,
    ).count()

    latest_chat = ChatHistory.query.filter_by(agent_type='whitehat').order_by(ChatHistory.timestamp.desc()).first()
    latest_task = AgentTask.query.filter_by(assigned_agent='whitehat').order_by(AgentTask.updated_at.desc()).first()

    if recent_chat_hits + recent_task_hits > 0:
        status = 'active'
    elif signal_count > 0 or rule_count > 0:
        status = 'ready'
    else:
        status = 'cold'

    return {
        'status': status,
        'window_hours': hours,
        'detector_online': status in {'active', 'ready'},
        'signal_count': signal_count,
        'rule_count': rule_count,
        'chat_total_hits': chat_total,
        'task_total_hits': task_total,
        'recent_chat_hits': recent_chat_hits,
        'recent_task_hits': recent_task_hits,
        'latest_chat_at': _bridge_iso(latest_chat.timestamp) if latest_chat else "",
        'latest_task_at': _bridge_iso(latest_task.updated_at) if latest_task else "",
    }



def get_data_framework_summary() -> dict:
    return {
        'storage': {
            'data_root': describe_path(DATA_ROOT),
            'instance_dir': describe_path(INSTANCE_DIR),
            'uploads_dir': describe_path(UPLOADS_DIR),
            'logs_dir': describe_path(LOGS_DIR),
            'database': describe_active_database_storage(),
            'monitor_log': describe_path(MONITOR_LOG_PATH),
        },
        'database': {
            'chat_history_count': ChatHistory.query.count(),
            'agent_task_count': AgentTask.query.count(),
            'xiaobian_profile_count': XiaobianProfile.query.count(),
            'dispatcher_rule_count': DispatcherRule.query.count(),
            'agent_signal_count': AgentSignal.query.count(),
            'heartbeat_enabled': CNS_HEARTBEAT_ENABLED,
            'cns_heartbeat_count': CNSHeartbeat.query.count() if CNS_HEARTBEAT_ENABLED else 0,
            'agent_notification_count': AgentNotification.query.count(),
        },
        'dispatcher': {
            'default_agents': list(DEFAULT_DISPATCH_RULES.keys()),
            'learned_rule_preview': [
                serialize_dispatcher_rule(rule)
                for rule in DispatcherRule.query.order_by(DispatcherRule.hit_count.desc(), DispatcherRule.updated_at.desc()).limit(10).all()
            ],
        },
        'proclaimer_detection': get_proclaimer_detection_status(),
        'whitehat_detection': get_whitehat_detection_status(),
        'agents': list_agent_overviews(),
        'cns_runtime': CNS_RUNTIME,
    }


def _bridge_runtime_message_from_heartbeat(cycle_type: str, heartbeat: CNSHeartbeat) -> str:
    details = _parse_json_text(getattr(heartbeat, "details", "") or "", {})
    summary = str(getattr(heartbeat, "summary", "") or "").strip()

    if cycle_type == "chatgpt_bridge_full_sync":
        rows_synced = details.get("rows_synced")
        batches_failed = details.get("batches_failed")
        if rows_synced is not None:
            failed = 0 if batches_failed is None else int(batches_failed)
            return f"rows={int(rows_synced)}, failed_batches={failed}"
        return summary or "completed"

    if cycle_type == "chatgpt_bridge_ingest":
        inserted = details.get("inserted")
        skipped = details.get("skipped")
        truncated = details.get("truncated")
        if inserted is not None:
            skip_count = 0 if skipped is None else int(skipped)
            return f"inserted={int(inserted)}, skipped={skip_count}, truncated={bool(truncated)}"
        return summary or "completed"

    if cycle_type == "chatgpt_bridge":
        preview = str(details.get("preview") or "").strip()
        if preview:
            return _bridge_string(preview, 240)
        return summary or "completed"

    return summary or "completed"


def hydrate_chatgpt_bridge_runtime_from_db():
    mapping = {
        "chatgpt_bridge": ("chatgpt_bridge_last_at", "chatgpt_bridge_last_status", "chatgpt_bridge_last_message"),
        "chatgpt_bridge_full_sync": ("chatgpt_bridge_full_last_at", "chatgpt_bridge_full_last_status", "chatgpt_bridge_full_last_message"),
        "chatgpt_bridge_ingest": ("chatgpt_bridge_ingest_last_at", "chatgpt_bridge_ingest_last_status", "chatgpt_bridge_ingest_last_message"),
    }

    for cycle_type, keys in mapping.items():
        at_key, status_key, message_key = keys
        heartbeat = CNSHeartbeat.query.filter_by(cycle_type=cycle_type).order_by(CNSHeartbeat.created_at.desc()).first()
        if not heartbeat:
            continue

        CNS_RUNTIME[at_key] = _bridge_iso(getattr(heartbeat, "created_at", None))
        CNS_RUNTIME[status_key] = str(getattr(heartbeat, "status", "") or CNS_RUNTIME.get(status_key) or "idle")
        CNS_RUNTIME[message_key] = _bridge_runtime_message_from_heartbeat(cycle_type, heartbeat)


def discover_legacy_db_candidates(extra_paths: list[str] | None = None) -> list[Path]:
    candidates: list[Path] = []
    raw_from_env = [item.strip() for item in LEGACY_DB_PATHS.split(",") if item.strip()]
    raw_extra = [item.strip() for item in (extra_paths or []) if str(item).strip()]
    default_paths = [
        BASE_DIR / "legacy" / "chat_history.db",
        BASE_DIR / "legacy" / "instance" / "chat_history.db",
        BASE_DIR / "500" / "llama32-chat" / "instance" / "chat_history.db",
        Path("/Volumes/智能體/城城城程式/instance/chat_history.db"),
    ]

    for raw in raw_from_env + raw_extra:
        try:
            candidates.append(Path(raw).expanduser().resolve())
        except Exception:
            continue
    for default_path in default_paths:
        try:
            candidates.append(default_path.expanduser().resolve())
        except Exception:
            continue

    unique_candidates = []
    target_db = DATABASE_PATH.resolve()
    seen = set()
    for item in candidates:
        if item == target_db:
            continue
        key = str(item)
        if key in seen:
            continue
        if item.exists() and item.is_file():
            unique_candidates.append(item)
            seen.add(key)
    return unique_candidates


def _sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _hash_row(*values) -> str:
    serialized = json.dumps([str(value or "") for value in values], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def merge_legacy_data_into_current(source_paths: list[str] | None = None, dry_run: bool = False, max_rows_per_table: int = 10000) -> dict:
    sources = discover_legacy_db_candidates(extra_paths=source_paths)
    summary = {
        "target_database": str(DATABASE_PATH),
        "dry_run": bool(dry_run),
        "sources_checked": [str(path) for path in sources],
        "sources_merged": [],
        "imported": {
            "chat_history": 0,
            "agent_task": 0,
            "xiaobian_profile": 0,
            "dispatcher_rule": 0,
            "agent_signal_new": 0,
            "agent_signal_enriched": 0,
        },
        "skipped": {
            "chat_history_duplicate": 0,
            "agent_task_duplicate": 0,
            "xiaobian_profile_existing": 0,
            "dispatcher_rule_existing": 0,
        },
        "errors": [],
    }

    if not sources:
        return summary

    limit = max(1, min(int(max_rows_per_table), 50000))

    existing_chat_signatures = {
        _hash_row(
            chat.user_message,
            chat.ai_response,
            chat.agent_type,
            chat.model_used,
            chat.signal_tags,
            chat.routing_reason,
        )
        for chat in ChatHistory.query.all()
    }
    existing_task_signatures = {
        _hash_row(
            task.title,
            task.description,
            task.goals,
            task.style_guidelines,
            task.constraints,
            task.output_format,
            task.assigned_agent,
            task.status,
        )
        for task in AgentTask.query.all()
    }
    existing_profile_keys = {profile.key for profile in XiaobianProfile.query.all()}
    existing_dispatch_patterns = {rule.pattern for rule in DispatcherRule.query.all()}
    existing_signal_index = {
        (signal.agent_key, signal.signal): signal
        for signal in AgentSignal.query.all()
    }

    try:
        for source_path in sources:
            source_report = {
                "path": str(source_path),
                "tables": {},
            }
            try:
                source_conn = sqlite3.connect(str(source_path))
                source_conn.row_factory = sqlite3.Row
            except Exception as exc:
                summary["errors"].append({"path": str(source_path), "error": f"open_failed: {exc}"})
                continue

            try:
                if _sqlite_table_exists(source_conn, "chat_history"):
                    rows = source_conn.execute(
                        "SELECT user_message, ai_response, agent_type, model_used, signal_tags, routing_reason FROM chat_history ORDER BY id ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    imported_in_table = 0
                    for row in rows:
                        signature = _hash_row(
                            row["user_message"],
                            row["ai_response"],
                            row["agent_type"],
                            row["model_used"],
                            row["signal_tags"],
                            row["routing_reason"],
                        )
                        if signature in existing_chat_signatures:
                            summary["skipped"]["chat_history_duplicate"] += 1
                            continue

                        imported_in_table += 1
                        summary["imported"]["chat_history"] += 1
                        existing_chat_signatures.add(signature)

                        if not dry_run:
                            original_model_used = str(row["model_used"] or "legacy").strip() or "legacy"
                            original_routing = str(row["routing_reason"] or "")
                            legacy_routing_payload = {
                                "legacy_data": True,
                                "legacy_source_db": str(source_path),
                                "legacy_source_table": "chat_history",
                                "original_routing_reason": original_routing[:1200],
                            }
                            db.session.add(ChatHistory(
                                user_message=sanitize_for_storage(row["user_message"], max_length=CHAT_STORAGE_USER_MAX_CHARS),
                                ai_response=sanitize_for_storage(row["ai_response"], max_length=CHAT_STORAGE_AI_MAX_CHARS),
                                agent_type=str(row["agent_type"] or "legacy")[:50],
                                model_used=f"legacy/{original_model_used}"[:50],
                                signal_tags=str(row["signal_tags"] or "")[:2000],
                                routing_reason=json.dumps(legacy_routing_payload, ensure_ascii=False)[:4000],
                            ))
                    source_report["tables"]["chat_history"] = {"rows": len(rows), "imported": imported_in_table}

                if _sqlite_table_exists(source_conn, "agent_task"):
                    rows = source_conn.execute(
                        "SELECT title, description, goals, style_guidelines, constraints, output_format, model_hint, assigned_agent, agent_label, issue_tags, learning_report, status, result FROM agent_task ORDER BY id ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    imported_in_table = 0
                    for row in rows:
                        signature = _hash_row(
                            row["title"],
                            row["description"],
                            row["goals"],
                            row["style_guidelines"],
                            row["constraints"],
                            row["output_format"],
                            row["assigned_agent"],
                            row["status"],
                        )
                        if signature in existing_task_signatures:
                            summary["skipped"]["agent_task_duplicate"] += 1
                            continue

                        imported_in_table += 1
                        summary["imported"]["agent_task"] += 1
                        existing_task_signatures.add(signature)

                        if not dry_run:
                            legacy_issue_tags = []
                            raw_issue_tags = str(row["issue_tags"] or "").strip()
                            if raw_issue_tags:
                                legacy_issue_tags.append(raw_issue_tags)
                            legacy_issue_tags.append("legacy_data")
                            legacy_issue_tags.append(f"legacy_source:{source_path}")
                            merged_issue_tags = "|".join(legacy_issue_tags)[:8000]

                            learning_report_parts = []
                            if row["learning_report"]:
                                learning_report_parts.append(str(row["learning_report"]))
                            learning_report_parts.append(f"[legacy_data=true source={source_path}]")
                            merged_learning_report = "\n".join(learning_report_parts)[:8000]

                            db.session.add(AgentTask(
                                title=str(row["title"] or "legacy task")[:200],
                                description=str(row["description"] or "")[:8000],
                                goals=str(row["goals"] or "")[:8000],
                                style_guidelines=str(row["style_guidelines"] or "")[:8000],
                                constraints=str(row["constraints"] or "")[:8000],
                                output_format=str(row["output_format"] or "")[:200],
                                model_hint=str(row["model_hint"] or "auto")[:50],
                                assigned_agent=(_fuse_agent_key(str(row["assigned_agent"] or "general")) or "general")[:50],
                                agent_label=str(row["agent_label"] or "")[:100],
                                issue_tags=merged_issue_tags,
                                learning_report=merged_learning_report,
                                status=str(row["status"] or "pending")[:50],
                                result=str(row["result"] or "")[:10000],
                            ))
                    source_report["tables"]["agent_task"] = {"rows": len(rows), "imported": imported_in_table}

                if _sqlite_table_exists(source_conn, "xiaobian_profile"):
                    rows = source_conn.execute(
                        "SELECT key, value FROM xiaobian_profile ORDER BY id ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    imported_in_table = 0
                    for row in rows:
                        key = str(row["key"] or "").strip()
                        if not key:
                            continue
                        if key in existing_profile_keys:
                            summary["skipped"]["xiaobian_profile_existing"] += 1
                            continue
                        imported_in_table += 1
                        summary["imported"]["xiaobian_profile"] += 1
                        existing_profile_keys.add(key)
                        if not dry_run:
                            db.session.add(XiaobianProfile(
                                key=key[:100],
                                value=str(row["value"] or "")[:12000],
                            ))
                    source_report["tables"]["xiaobian_profile"] = {"rows": len(rows), "imported": imported_in_table}

                if _sqlite_table_exists(source_conn, "dispatcher_rule"):
                    rows = source_conn.execute(
                        "SELECT pattern, target_agent, source, notes, hit_count, last_matched_message FROM dispatcher_rule ORDER BY id ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    imported_in_table = 0
                    for row in rows:
                        pattern = str(row["pattern"] or "").strip()
                        if not pattern:
                            continue
                        if pattern in existing_dispatch_patterns:
                            summary["skipped"]["dispatcher_rule_existing"] += 1
                            continue
                        imported_in_table += 1
                        summary["imported"]["dispatcher_rule"] += 1
                        existing_dispatch_patterns.add(pattern)
                        if not dry_run:
                            db.session.add(DispatcherRule(
                                pattern=pattern[:120],
                                target_agent=(_fuse_agent_key(str(row["target_agent"] or "general")) or "general")[:50],
                                source=str(row["source"] or "legacy_import")[:50],
                                notes=str(row["notes"] or "")[:4000],
                                hit_count=max(1, int(row["hit_count"] or 1)),
                                last_matched_message=str(row["last_matched_message"] or "")[:300],
                            ))
                    source_report["tables"]["dispatcher_rule"] = {"rows": len(rows), "imported": imported_in_table}

                if _sqlite_table_exists(source_conn, "agent_signal"):
                    rows = source_conn.execute(
                        "SELECT agent_key, signal, source, weight, hit_count, last_seen_message FROM agent_signal ORDER BY id ASC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    imported_new = 0
                    enriched_existing = 0
                    for row in rows:
                        agent_key = str(row["agent_key"] or "").strip()[:50]
                        signal_text = str(row["signal"] or "").strip()[:120]
                        if not agent_key or not signal_text:
                            continue
                        pair = (agent_key, signal_text)
                        existing_signal = existing_signal_index.get(pair)

                        if existing_signal:
                            enriched_existing += 1
                            summary["imported"]["agent_signal_enriched"] += 1
                            if not dry_run:
                                existing_signal.weight = max(existing_signal.weight or 1, int(row["weight"] or 1))
                                existing_signal.hit_count = max(existing_signal.hit_count or 1, int(row["hit_count"] or 1))
                                if not existing_signal.last_seen_message and row["last_seen_message"]:
                                    existing_signal.last_seen_message = str(row["last_seen_message"])[:500]
                            continue

                        imported_new += 1
                        summary["imported"]["agent_signal_new"] += 1
                        if not dry_run:
                            created_signal = AgentSignal(
                                agent_key=agent_key,
                                signal=signal_text,
                                source=str(row["source"] or "legacy_import")[:50],
                                weight=max(1, int(row["weight"] or 1)),
                                hit_count=max(1, int(row["hit_count"] or 1)),
                                last_seen_message=str(row["last_seen_message"] or "")[:500],
                            )
                            db.session.add(created_signal)
                            existing_signal_index[pair] = created_signal
                    source_report["tables"]["agent_signal"] = {
                        "rows": len(rows),
                        "imported_new": imported_new,
                        "enriched_existing": enriched_existing,
                    }

                summary["sources_merged"].append(source_report)
            except Exception as source_exc:
                summary["errors"].append({"path": str(source_path), "error": str(source_exc)})
                db.session.rollback()
            finally:
                source_conn.close()

        if not dry_run:
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        summary["errors"].append({"path": "runtime", "error": str(exc)})

    return summary


def check_ollama_available():
    """Helper to check if Ollama is running safely"""
    try:
        ollama.list()
        return True
    except Exception:
        return False


def is_gpt2_available() -> bool:
    status = get_gpt2_status()
    return bool(status.get("ml_runtime_available") or status.get("backend") == "sidecar")


def is_model_choice_available(model_choice: str) -> bool:
    if model_choice == 'auto':
        return True
    if model_choice == 'tinyllama':
        return check_ollama_available()
    if model_choice == 'gpt2':
        return is_gpt2_available()
    if model_choice == 'openai':
        return OPENAI_ENABLED
    if model_choice == 'huggingface':
        return HF_ENABLED
    if model_choice == 'together':
        return TOGETHER_ENABLED
    if model_choice == 'openrouter':
        return OPENROUTER_ENABLED
    if model_choice == 'groq':
        return GROQ_ENABLED
    if model_choice == 'gemini':
        return GEMINI_ENABLED
    if model_choice == 'nvidia':
        return NVIDIA_ENABLED
    if model_choice == 'zhizengzeng':
        return is_zzz_provider_ready()
    return False


def normalize_model_choice(model_choice: str | None) -> str:
    normalized = str(model_choice or 'auto').strip().lower()
    aliases = {
        'ollama': 'tinyllama',
        'local': 'tinyllama',
        'zzz': 'zhizengzeng',
        'zzzapi': 'zhizengzeng',
        'zzz-api': 'zhizengzeng',
        'zhizengzengapi': 'zhizengzeng',
        'gemin': 'gemini',
        'google': 'gemini',
        'google-gemini': 'gemini',
        'nvapi': 'nvidia',
        'nvidia-api': 'nvidia',
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_MODEL_CHOICES:
        return 'auto'
    return normalized


def select_execution_model_choice() -> str:
    configured = normalize_model_choice(EXECUTION_PROVIDER)
    if configured == "auto":
        configured = "nvidia"

    if configured == "nvidia" and NVIDIA_ENABLED:
        return "nvidia"

    if configured != "auto" and is_model_choice_available(configured):
        return configured

    if NVIDIA_ENABLED:
        return "nvidia"

    fallback_cloud = select_preferred_cloud_model(for_execution=False)
    if fallback_cloud:
        return fallback_cloud

    if ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available():
        return "tinyllama"

    if ALLOW_LOCAL_MODEL_FALLBACK and is_gpt2_available():
        return "gpt2"

    return "auto"


def is_non_language_processing_request(message: str) -> bool:
    message_lower = str(message or '').lower()
    keywords = [
        '分析', 'analyze', 'analysis', '資料', 'data', '報表', 'pipeline',
        '程式', 'code', 'debug', '除錯', 'workflow', '自動化', 'automation',
        '部署', 'deploy', 'api', 'json', 'sql', '批次', 'batch',
    ]
    return any(k in message_lower for k in keywords)


COMMUNICATION_ALLOWED_MODELS = {
    'auto', 'tinyllama', 'gpt2', 'openai', 'openrouter', 'groq', 'gemini', 'zhizengzeng', 'huggingface', 'together'
}


def enforce_communication_model_choice(model_choice: str) -> str:
    normalized = normalize_model_choice(model_choice)
    if normalized not in COMMUNICATION_ALLOWED_MODELS:
        return 'auto'
    return normalized


def select_direct_communication_model_choice(model_choice: str = 'auto') -> str:
    normalized = enforce_communication_model_choice(model_choice)
    if normalized != 'auto':
        return normalized

    # Direct sidebar/agent chat is conversation-first and should avoid execution routing.
    cloud_choice = select_preferred_cloud_model(for_execution=False)
    if cloud_choice:
        return cloud_choice

    if ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available():
        return 'tinyllama'
    if ALLOW_LOCAL_MODEL_FALLBACK and is_gpt2_available():
        return 'gpt2'
    return 'auto'


def _detect_terms_in_text(text: str, terms: list[str], limit: int = 12) -> list[str]:
    lowered = str(text or "").lower()
    matches = []
    for term in terms:
        normalized = str(term or "").strip().lower()
        if normalized and normalized in lowered and normalized not in matches:
            matches.append(normalized)
        if len(matches) >= limit:
            break
    return matches


def is_defensive_security_context(user_message: str) -> bool:
    lowered = str(user_message or "").lower()
    return any(term in lowered for term in SAFETY_DEFENSIVE_CONTEXT_TERMS)


def build_safety_regeneration_prompt(user_message: str, blocked_terms: list[str], model_used: str) -> str:
    blocked_text = "、".join(blocked_terms[:10]) or "黑灰產或違法詞彙"
    return (
        "你是企業安全助理。請以合法、合規、防禦導向方式回覆，"
        "不能提供任何黑灰產、詐騙、洗錢、博彩、入侵的操作內容。\n"
        f"禁用詞：{blocked_text}\n"
        f"原模型：{model_used}\n"
        f"使用者需求：{user_message}\n"
        "請輸出 3-6 點可執行的安全建議，繁體中文，避免任何違法指引。"
    )


def build_safety_fallback_response() -> str:
    return (
        "我已攔截可能涉及黑灰產或違法導向的內容。\n"
        "可改為提供合法防護建議：\n"
        "1. 建立風險詞攔截與異常告警規則\n"
        "2. 強化帳號驗證、權限與審計日誌\n"
        "3. 針對金流與 API 建立行為異常偵測\n"
        "4. 建立事件回報、證據保全與通報流程"
    )


def guard_black_gray_response(
    user_message: str,
    ai_response: str,
    model_choice: str,
    agent_key: str,
    model_used: str,
) -> tuple[str, dict]:
    metadata = {
        "enabled": RESPONSE_SAFETY_FILTER_ENABLED,
        "triggered": False,
        "defensive_context": False,
        "matched_terms": [],
        "promotion_terms": [],
        "regenerated": False,
        "regen_attempts": 0,
        "fallback_used": False,
        "regenerated_model": "",
    }

    response_text = str(ai_response or "")
    if not RESPONSE_SAFETY_FILTER_ENABLED or not response_text.strip():
        return response_text, metadata

    matched_terms = _detect_terms_in_text(response_text, SAFETY_BLACK_GRAY_TERMS)
    if not matched_terms:
        return response_text, metadata

    promotion_terms = _detect_terms_in_text(response_text, SAFETY_PROMOTION_TERMS)
    defensive_context = is_defensive_security_context(user_message)
    should_intercept = bool(promotion_terms) or not defensive_context or len(matched_terms) >= 2

    metadata.update({
        "defensive_context": defensive_context,
        "matched_terms": matched_terms,
        "promotion_terms": promotion_terms,
    })

    if not should_intercept:
        return response_text, metadata

    metadata["triggered"] = True
    current_response = response_text

    for _ in range(RESPONSE_SAFETY_REGENERATION_RETRIES):
        metadata["regen_attempts"] += 1
        regeneration_prompt = build_safety_regeneration_prompt(user_message, matched_terms, model_used)
        try:
            regenerated_response, regenerated_model = execute_prompt(
                regeneration_prompt,
                model_choice=model_choice,
                prefer_cloud=False,
            )
        except Exception as exc:
            logging.warning("Safety regeneration failed for %s: %s", agent_key, exc)
            continue

        current_response = str(regenerated_response or "")
        regen_terms = _detect_terms_in_text(current_response, SAFETY_BLACK_GRAY_TERMS)
        regen_promo_terms = _detect_terms_in_text(current_response, SAFETY_PROMOTION_TERMS)
        if not regen_terms and not regen_promo_terms:
            metadata["regenerated"] = True
            metadata["regenerated_model"] = str(regenerated_model or "")
            return current_response.strip(), metadata

    metadata["fallback_used"] = True
    return build_safety_fallback_response(), metadata


def should_ask_back(user_message: str) -> bool:
    text = str(user_message or '').strip()
    if not text:
        return False
    if len(text) <= 6:
        return True

    lowered = text.lower()
    vague_patterns = [
        '幫我看', '幫我弄', '幫我處理', '優化一下', '修一下', '看一下',
        'help me', 'fix this', 'do this', 'optimize this', 'check this',
    ]
    if any(p in lowered for p in vague_patterns) and len(text) < 20:
        return True

    return False


def build_ask_back_question(user_message: str) -> str:
    return (
        "我已開始學習這個需求。為了更精準執行，先幫我確認三點：\n"
        "1) 你要的最終結果是什麼？\n"
        "2) 優先順序（速度 / 品質 / 安全）哪個第一？\n"
        "3) 有沒有不能動的檔案或限制？"
    )


def is_bridge_summon_command(user_message: str) -> bool:
    text = str(user_message or "").strip()
    summon = str(CHATGPT_BRIDGE_SUMMON_COMMAND or "").strip()
    if not text or not summon:
        return False
    text_lower = text.lower()
    summon_lower = summon.lower()
    accepted = {
        summon_lower,
        f"/{summon_lower}",
        f"召喚{summon_lower}",
        f"召喚 {summon_lower}",
        f"bridge:{summon_lower}",
        f"chatgpt:{summon_lower}",
    }
    if text_lower in accepted:
        return True
    prefixes = (
        f"{summon_lower} ",
        f"/{summon_lower} ",
        f"召喚{summon_lower} ",
        f"召喚 {summon_lower} ",
        f"bridge:{summon_lower} ",
        f"chatgpt:{summon_lower} ",
    )
    return any(text_lower.startswith(prefix) for prefix in prefixes)


def is_bridge_full_sync_command(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    summon = str(CHATGPT_BRIDGE_SUMMON_COMMAND or "").strip().lower()
    if not text or not summon:
        return False
    full_tokens = ["全部", "全量", "full", "all", "sync-all", "完整"]
    return summon in text and any(token in text for token in full_tokens)


def _bridge_extract_text(item: dict, keys: tuple[str, ...]) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        raw = item.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def normalize_chatgpt_ingest_entries(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    normalized = []
    entries = payload.get("entries")
    if isinstance(entries, list):
        for row in entries:
            if not isinstance(row, dict):
                continue
            user_message = _bridge_extract_text(row, ("user_message", "user", "prompt", "input", "question"))
            ai_response = _bridge_extract_text(row, ("ai_response", "assistant", "response", "output", "answer"))
            if not user_message and not ai_response:
                continue
            normalized.append({
                "user_message": user_message,
                "ai_response": ai_response,
                "source": _bridge_extract_text(row, ("source", "channel", "origin")) or "chatgpt_user",
                "timestamp": _bridge_extract_text(row, ("timestamp", "time", "created_at")),
                "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
                "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
            })

    if not normalized:
        messages = payload.get("messages")
        if isinstance(messages, list):
            pending_user = ""
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role = _bridge_extract_text(msg, ("role", "sender", "author")).lower()
                content = _bridge_extract_text(msg, ("content", "text", "message"))
                if not content:
                    continue
                if role in {"user", "human", "client"}:
                    pending_user = content
                    continue
                if role in {"assistant", "ai", "model", "chatgpt", "bot"}:
                    normalized.append({
                        "user_message": pending_user or "[chatgpt_session_context]",
                        "ai_response": content,
                        "source": _bridge_extract_text(payload, ("source", "channel", "origin")) or "chatgpt_user",
                        "timestamp": _bridge_extract_text(msg, ("timestamp", "time", "created_at")),
                        "tags": [],
                        "metadata": {},
                    })
                    pending_user = ""

    if not normalized:
        single_user = _bridge_extract_text(payload, ("user_message", "user", "prompt", "input", "question"))
        single_ai = _bridge_extract_text(payload, ("ai_response", "assistant", "response", "output", "answer"))
        if single_user or single_ai:
            normalized.append({
                "user_message": single_user,
                "ai_response": single_ai,
                "source": _bridge_extract_text(payload, ("source", "channel", "origin")) or "chatgpt_user",
                "timestamp": _bridge_extract_text(payload, ("timestamp", "time", "created_at")),
                "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
                "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            })

    return normalized


def _bridge_string(value, max_chars: int = 8000) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _bridge_iso(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _sync_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _to_int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _new_full_sync_job(payload: dict, source: str, request_trace: dict) -> dict:
    data = payload if isinstance(payload, dict) else {}
    api_timeout = _to_int_or_none(data.get("api_timeout_seconds")) or CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS
    api_timeout = max(10, min(300, api_timeout))
    hard_timeout = _to_int_or_none(data.get("hard_timeout_seconds")) or CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS
    hard_timeout = max(30, min(7200, hard_timeout))
    job_id = f"fs_{uuid.uuid4().hex[:12]}"
    config = {
        "force": _coerce_bool(data.get("force", True), True),
        "batch_size": _to_int_or_none(data.get("batch_size")),
        "max_batches": _to_int_or_none(data.get("max_batches")),
        "field_max_chars": _to_int_or_none(data.get("field_max_chars")),
        "only_batch_indexes": [int(v) for v in (data.get("only_batch_indexes") or []) if str(v).strip().isdigit()],
        "auto_recover": _coerce_bool(data.get("auto_recover", SYNC_AUTO_RECOVER_ENABLED), SYNC_AUTO_RECOVER_ENABLED),
        "auto_recover_max_rounds": max(0, min(5, _to_int_or_none(data.get("auto_recover_max_rounds")) or SYNC_AUTO_RECOVER_MAX_ROUNDS)),
        "auto_recover_field_max_chars": _to_int_or_none(data.get("auto_recover_field_max_chars")) or SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS,
        "api_timeout_seconds": api_timeout,
        "hard_timeout_seconds": hard_timeout,
    }
    return {
        "id": job_id,
        "type": "full_sync",
        "status": "queued",
        "source": source,
        "created_at": _sync_now_iso(),
        "started_at": None,
        "finished_at": None,
        "request_trace": request_trace if isinstance(request_trace, dict) else {},
        "config": config,
        "progress": {
            "phase": "queued",
            "current_round": 0,
            "total_batches": 0,
            "processed_batches": 0,
            "acknowledged_batches": 0,
            "failed_batches": 0,
            "rows_synced": 0,
            "current_batch_index": 0,
            "current_table": "",
            "elapsed_seconds": 0,
            "last_update_at": _sync_now_iso(),
        },
        "result": None,
        "agent_task": None,
        "error": "",
    }


def _store_full_sync_job(job: dict) -> dict:
    with FULL_SYNC_JOB_LOCK:
        FULL_SYNC_JOBS[job["id"]] = job
        FULL_SYNC_JOB_ORDER.append(job["id"])
        overflow = len(FULL_SYNC_JOB_ORDER) - CHATGPT_BRIDGE_FULL_SYNC_JOB_RETENTION
        if overflow > 0:
            for stale_job_id in FULL_SYNC_JOB_ORDER[:overflow]:
                FULL_SYNC_JOBS.pop(stale_job_id, None)
            del FULL_SYNC_JOB_ORDER[:overflow]
    return job


def _get_full_sync_job(job_id: str) -> dict | None:
    with FULL_SYNC_JOB_LOCK:
        job = FULL_SYNC_JOBS.get(str(job_id or "").strip())
        return dict(job) if isinstance(job, dict) else None


def _list_full_sync_jobs(limit: int = 20) -> list[dict]:
    cap = max(1, min(200, int(limit or 20)))
    with FULL_SYNC_JOB_LOCK:
        selected = FULL_SYNC_JOB_ORDER[-cap:]
        return [dict(FULL_SYNC_JOBS[job_id]) for job_id in reversed(selected) if job_id in FULL_SYNC_JOBS]


def _count_active_full_sync_jobs() -> int:
    with FULL_SYNC_JOB_LOCK:
        return sum(1 for row in FULL_SYNC_JOBS.values() if str((row or {}).get("status", "")).lower() in {"queued", "running"})


def _update_full_sync_job(job_id: str, patch: dict):
    if not patch:
        return
    with FULL_SYNC_JOB_LOCK:
        if job_id not in FULL_SYNC_JOBS:
            return
        current = FULL_SYNC_JOBS[job_id]
        for key, value in patch.items():
            if key == "progress" and isinstance(value, dict):
                base_progress = current.get("progress") if isinstance(current.get("progress"), dict) else {}
                base_progress.update(value)
                base_progress["last_update_at"] = _sync_now_iso()
                current["progress"] = base_progress
            else:
                current[key] = value
        FULL_SYNC_JOBS[job_id] = current


def _run_full_sync_job_async(job_id: str):
    with app.app_context():
        job = _get_full_sync_job(job_id)
        if not job:
            return

        config = job.get("config") if isinstance(job.get("config"), dict) else {}
        payload = {
            "force": config.get("force", True),
            "batch_size": config.get("batch_size"),
            "max_batches": config.get("max_batches"),
            "field_max_chars": config.get("field_max_chars"),
            "only_batch_indexes": config.get("only_batch_indexes"),
            "auto_recover": config.get("auto_recover", SYNC_AUTO_RECOVER_ENABLED),
            "auto_recover_max_rounds": config.get("auto_recover_max_rounds", SYNC_AUTO_RECOVER_MAX_ROUNDS),
            "auto_recover_field_max_chars": config.get("auto_recover_field_max_chars", SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS),
            "api_timeout_seconds": config.get("api_timeout_seconds", CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS),
            "hard_timeout_seconds": config.get("hard_timeout_seconds", CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS),
        }

        _update_full_sync_job(
            job_id,
            {
                "status": "running",
                "started_at": _sync_now_iso(),
                "progress": {"phase": "initial_sync"},
            },
        )

        def _on_progress(event: dict):
            if not isinstance(event, dict):
                return
            progress_patch = {}
            for key in [
                "phase",
                "current_round",
                "total_batches",
                "processed_batches",
                "acknowledged_batches",
                "failed_batches",
                "rows_synced",
                "current_batch_index",
                "current_table",
                "elapsed_seconds",
            ]:
                if key in event:
                    progress_patch[key] = event.get(key)
            if progress_patch:
                _update_full_sync_job(job_id, {"progress": progress_patch})

        try:
            result = run_full_sync_with_recovery(
                payload=payload,
                source=str(job.get("source", "external_sync_full")).strip() or "external_sync_full",
                progress_callback=_on_progress,
                hard_timeout_seconds=config.get("hard_timeout_seconds"),
                api_timeout_seconds=config.get("api_timeout_seconds"),
            )
            status = str((result or {}).get("status") or "failed").lower()
            heartbeat_status = "completed" if status == "completed" else ("failed" if status in {"failed", "timeout"} else status)
            task = create_sync_agent_task("full_sync_async", payload, result)
            _update_full_sync_job(
                job_id,
                {
                    "status": status,
                    "finished_at": _sync_now_iso(),
                    "result": result,
                    "agent_task": task,
                    "progress": {"phase": "finished"},
                },
            )
            record_cns_heartbeat(
                "external_sync_request",
                heartbeat_status,
                f"/sync async full_sync {status}",
                {
                    "sync_mode": "full_sync_async",
                    "result_status": status,
                    "rows_synced": (result or {}).get("rows_synced"),
                    "batches_failed": (result or {}).get("batches_failed"),
                    "source": (result or {}).get("source"),
                    "job_id": job_id,
                    "request_trace": job.get("request_trace", {}),
                },
            )
        except Exception as exc:
            error_text = str(exc)
            _update_full_sync_job(
                job_id,
                {
                    "status": "failed",
                    "finished_at": _sync_now_iso(),
                    "error": error_text[:400],
                    "progress": {"phase": "failed"},
                },
            )
            record_cns_heartbeat(
                "external_sync_request",
                "failed",
                "/sync async full_sync worker exception",
                {
                    "sync_mode": "full_sync_async",
                    "result_status": "failed",
                    "source": str(job.get("source", "external_sync_full")),
                    "job_id": job_id,
                    "error": error_text[:600],
                    "request_trace": job.get("request_trace", {}),
                },
            )

def _chunk_list(items: list, chunk_size: int):
    size = max(1, int(chunk_size))
    for idx in range(0, len(items), size):
        yield items[idx: idx + size]


def build_chatgpt_bridge_full_sync_batches(
    batch_size: int | None = None,
    field_max_chars: int | None = None,
) -> tuple[list[dict], dict]:
    size = max(5, min(200, int(batch_size or CHATGPT_BRIDGE_FULL_SYNC_BATCH_SIZE)))
    max_chars = max(200, min(50000, int(field_max_chars or CHATGPT_BRIDGE_FULL_SYNC_FIELD_MAX_CHARS)))

    tables = {
        "chat_history": [
            {
                "id": row.id,
                "user_message": _bridge_string(row.user_message, max_chars),
                "ai_response": _bridge_string(row.ai_response, max_chars),
                "agent_type": _bridge_string(row.agent_type, 120),
                "model_used": _bridge_string(row.model_used, 120),
                "signal_tags": _bridge_string(row.signal_tags, max_chars),
                "routing_reason": _bridge_string(row.routing_reason, max_chars),
                "timestamp": _bridge_iso(row.timestamp),
            }
            for row in ChatHistory.query.order_by(ChatHistory.id.asc()).all()
        ],
        "agent_task": [
            {
                "id": row.id,
                "title": _bridge_string(row.title, 300),
                "description": _bridge_string(row.description, max_chars),
                "goals": _bridge_string(row.goals, max_chars),
                "constraints": _bridge_string(row.constraints, max_chars),
                "output_format": _bridge_string(row.output_format, 200),
                "model_hint": _bridge_string(row.model_hint, 120),
                "assigned_agent": _bridge_string(row.assigned_agent, 120),
                "status": _bridge_string(row.status, 120),
                "result": _bridge_string(row.result, max_chars),
                "updated_at": _bridge_iso(row.updated_at),
            }
            for row in AgentTask.query.order_by(AgentTask.id.asc()).all()
        ],
        "dispatcher_rule": [
            {
                "id": row.id,
                "pattern": _bridge_string(row.pattern, 200),
                "target_agent": _bridge_string(row.target_agent, 120),
                "source": _bridge_string(row.source, 120),
                "hit_count": int(row.hit_count or 0),
                "last_matched_message": _bridge_string(row.last_matched_message, max_chars),
                "updated_at": _bridge_iso(row.updated_at),
            }
            for row in DispatcherRule.query.order_by(DispatcherRule.id.asc()).all()
        ],
        "agent_signal": [
            {
                "id": row.id,
                "agent_key": _bridge_string(row.agent_key, 120),
                "signal": _bridge_string(row.signal, 200),
                "source": _bridge_string(row.source, 120),
                "weight": int(row.weight or 0),
                "hit_count": int(row.hit_count or 0),
                "last_seen_message": _bridge_string(row.last_seen_message, max_chars),
                "updated_at": _bridge_iso(row.updated_at),
            }
            for row in AgentSignal.query.order_by(AgentSignal.id.asc()).all()
        ],
        "cns_heartbeat": [
            {
                "id": row.id,
                "cycle_type": _bridge_string(row.cycle_type, 120),
                "status": _bridge_string(row.status, 120),
                "summary": _bridge_string(row.summary, 300),
                "details": _bridge_string(row.details, max_chars),
                "created_at": _bridge_iso(row.created_at),
            }
            for row in CNSHeartbeat.query.order_by(CNSHeartbeat.id.asc()).all()
        ],
        "agent_notification": [
            {
                "id": row.id,
                "agent_key": _bridge_string(row.agent_key, 120),
                "level": _bridge_string(row.level, 60),
                "category": _bridge_string(row.category, 120),
                "title": _bridge_string(row.title, 300),
                "message": _bridge_string(row.message, max_chars),
                "details": _bridge_string(row.details, max_chars),
                "related_task_id": row.related_task_id,
                "is_read": bool(row.is_read),
                "created_at": _bridge_iso(row.created_at),
            }
            for row in AgentNotification.query.order_by(AgentNotification.id.asc()).all()
        ],
    }

    batches = []
    table_counts = {name: len(items) for name, items in tables.items()}
    for table_name, items in tables.items():
        if not items:
            continue
        chunks = list(_chunk_list(items, size))
        for chunk_index, chunk in enumerate(chunks, start=1):
            batches.append({
                "table": table_name,
                "table_total_rows": len(items),
                "table_chunk_index": chunk_index,
                "table_chunk_total": len(chunks),
                "rows": chunk,
            })

    summary = {
        "table_counts": table_counts,
        "total_rows": sum(table_counts.values()),
        "total_batches": len(batches),
        "batch_size": size,
        "field_max_chars": max_chars,
    }
    return batches, summary


def build_chatgpt_bridge_payload(max_items: int = 20) -> dict:
    limit = max(5, min(60, int(max_items)))
    top_signals = AgentSignal.query.order_by(AgentSignal.hit_count.desc(), AgentSignal.updated_at.desc()).limit(limit).all()
    top_rules = DispatcherRule.query.order_by(DispatcherRule.hit_count.desc(), DispatcherRule.updated_at.desc()).limit(limit).all()
    recent_cycles = CNSHeartbeat.query.order_by(CNSHeartbeat.created_at.desc()).limit(6).all()

    return {
        "privacy_mode": PRIVACY_MODE,
        "learning_mode": LEARNING_MODE,
        "ask_back_mode": ASK_BACK_MODE,
        "execution_provider": EXECUTION_PROVIDER,
        "cloud_preferred": PREFER_CLOUD_MODELS,
        "agent_signal_snapshot": [
            {
                "agent_key": signal.agent_key,
                "signal": signal.signal,
                "hit_count": signal.hit_count or 0,
                "weight": signal.weight or 0,
            }
            for signal in top_signals
        ],
        "dispatcher_rule_snapshot": [
            {
                "pattern": rule.pattern,
                "target_agent": rule.target_agent,
                "hit_count": rule.hit_count or 0,
                "source": rule.source,
            }
            for rule in top_rules
        ],
        "recent_cns_cycles": [
            {
                "cycle_type": cycle.cycle_type,
                "status": cycle.status,
                "summary": cycle.summary,
                "created_at": cycle.created_at.isoformat() if cycle.created_at else "",
            }
            for cycle in recent_cycles
        ],
    }


def run_chatgpt_bridge_ingest(payload: dict, source: str = "chatgpt_manual_ingest") -> dict:
    if not CHATGPT_BRIDGE_INGEST_ENABLED:
        return {"status": "disabled", "reason": "CHATGPT_BRIDGE_INGEST_ENABLED=false"}

    entries = normalize_chatgpt_ingest_entries(payload)
    total_received = len(entries)
    if total_received == 0:
        CNS_RUNTIME["chatgpt_bridge_ingest_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        CNS_RUNTIME["chatgpt_bridge_ingest_last_status"] = "skipped"
        CNS_RUNTIME["chatgpt_bridge_ingest_last_message"] = "no_data"
        return {"status": "skipped", "reason": "no_valid_entries"}

    accepted_entries = entries[:CHATGPT_BRIDGE_INGEST_MAX_ITEMS]
    skipped = 0
    inserted = 0
    signal_terms = set()
    started_at = time.time()

    for row in accepted_entries:
        user_message = str(row.get("user_message") or "").strip()
        ai_response = str(row.get("ai_response") or "").strip()
        if not user_message and not ai_response:
            skipped += 1
            continue

        user_for_route = user_message or ai_response
        dispatch = dispatch_task(user_for_route)
        agent_type = dispatch.get("agent", "learner")
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        tags_text = " ".join(str(tag) for tag in tags if str(tag).strip())
        signal_tags = infer_signal_tags(user_message, ai_response, tags_text)
        signal_terms.update(signal_tags)

        routing_reason = {
            "reason": "chatgpt_external_ingest",
            "source": str(row.get("source") or source),
            "timestamp": str(row.get("timestamp") or ""),
            "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
            "dispatch": dispatch,
        }

        chat_entry = ChatHistory(
            user_message=sanitize_for_storage(user_message or "[chatgpt_session_context]", max_length=CHAT_STORAGE_USER_MAX_CHARS),
            ai_response=sanitize_for_storage(ai_response or "[empty_assistant_response]", max_length=CHAT_STORAGE_AI_MAX_CHARS),
            agent_type=agent_type,
            model_used="chatgpt_external_ingest",
            signal_tags=json.dumps(signal_tags, ensure_ascii=False),
            routing_reason=json.dumps(routing_reason, ensure_ascii=False),
        )
        db.session.add(chat_entry)
        learn_agent_signals(
            "learner",
            [user_message, ai_response, tags_text],
            source="chatgpt_external_ingest",
            message=user_for_route,
        )
        inserted += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        error_text = str(exc)
        CNS_RUNTIME["chatgpt_bridge_ingest_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        CNS_RUNTIME["chatgpt_bridge_ingest_last_status"] = "failed"
        CNS_RUNTIME["chatgpt_bridge_ingest_last_message"] = error_text[:240]
        return {"status": "failed", "error": error_text}

    elapsed = round(time.time() - started_at, 3)
    truncated = total_received > len(accepted_entries)
    status = "completed" if inserted > 0 else "skipped"
    result = {
        "status": status,
        "source": source,
        "total_received": total_received,
        "accepted": len(accepted_entries),
        "inserted": inserted,
        "skipped": skipped,
        "truncated": truncated,
        "max_items": CHATGPT_BRIDGE_INGEST_MAX_ITEMS,
        "elapsed_seconds": elapsed,
        "signal_terms": sorted(signal_terms)[:40],
    }

    summary_text = f"inserted={inserted}, skipped={skipped}, truncated={truncated}"
    CNS_RUNTIME["chatgpt_bridge_ingest_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    CNS_RUNTIME["chatgpt_bridge_ingest_last_status"] = status
    CNS_RUNTIME["chatgpt_bridge_ingest_last_message"] = summary_text

    emit_notification(
        "learner",
        "ChatGPT 對話回寫完成",
        f"已回寫 {inserted} 筆外部對話資料",
        level="info" if status == "completed" else "warning",
        category="learning",
        details={
            "inserted": inserted,
            "skipped": skipped,
            "truncated": truncated,
            "source": source,
        },
    )
    record_cns_heartbeat(
        "chatgpt_bridge_ingest",
        "completed" if status == "completed" else "failed",
        "ChatGPT 對話資料回寫資料庫完成",
        {
            "source": source,
            "inserted": inserted,
            "skipped": skipped,
            "truncated": truncated,
        },
    )
    return result


def run_chatgpt_bidirectional_sync(source: str = "chat_runtime", force: bool = False) -> dict:
    global CHATGPT_BRIDGE_LAST_TS

    if not CHATGPT_BRIDGE_ENABLED:
        return {"status": "disabled", "reason": "CHATGPT_BRIDGE_ENABLED=false"}
    if not OPENAI_ENABLED:
        return {"status": "skipped", "reason": "OPENAI_API_KEY unavailable"}

    now_ts = time.time()
    with CHATGPT_BRIDGE_LOCK:
        elapsed = now_ts - CHATGPT_BRIDGE_LAST_TS
        if not force and CHATGPT_BRIDGE_LAST_TS > 0 and elapsed < CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS:
            remaining = int(CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS - elapsed)
            return {"status": "throttled", "reason": f"cooldown {remaining}s"}
        CHATGPT_BRIDGE_LAST_TS = now_ts

    payload = build_chatgpt_bridge_payload(max_items=CHATGPT_BRIDGE_MAX_ITEMS)
    bridge_prompt = (
        "你是多智能體系統的雲端學習協調器。"
        "請根據提供的結構化快照，回傳 5 點以內的『可執行』優化建議，"
        "只聚焦於路由品質、學習效率與安全守門，禁止產出黑灰產內容。"
        "請使用繁體中文、條列格式。\n\n"
        f"來源：{source}\n"
        f"快照：{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        bridge_response = query_openai_compatible(
            bridge_prompt,
            api_key=OPENAI_API_KEY,
            api_base=OPENAI_API_BASE,
            model_name=CHATGPT_BRIDGE_MODEL,
            provider_name="ChatGPT Bridge",
        )
        summary = str(bridge_response or "").strip()
        learn_agent_signals(
            "learner",
            [summary, json.dumps(payload, ensure_ascii=False)],
            source="chatgpt_bridge",
            message=f"bridge:{source}",
        )
        emit_notification(
            "learner",
            "ChatGPT 雙向學習同步完成",
            "已完成雲端學習回饋並回寫本地訊號記憶",
            level="info",
            category="learning",
            details={
                "source": source,
                "model": CHATGPT_BRIDGE_MODEL,
                "preview": summary[:240],
            },
        )
        record_cns_heartbeat(
            "chatgpt_bridge",
            "completed",
            "雲端雙向學習同步完成",
            {
                "source": source,
                "model": CHATGPT_BRIDGE_MODEL,
                "preview": summary[:240],
            },
        )
        CNS_RUNTIME["chatgpt_bridge_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        CNS_RUNTIME["chatgpt_bridge_last_status"] = "completed"
        CNS_RUNTIME["chatgpt_bridge_last_message"] = summary[:240] or "completed"
        return {"status": "completed", "model": CHATGPT_BRIDGE_MODEL, "preview": summary[:240]}
    except Exception as exc:
        error_text = str(exc)
        record_cns_heartbeat(
            "chatgpt_bridge",
            "failed",
            "雲端雙向學習同步失敗",
            {"source": source, "error": error_text},
        )
        CNS_RUNTIME["chatgpt_bridge_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        CNS_RUNTIME["chatgpt_bridge_last_status"] = "failed"
        CNS_RUNTIME["chatgpt_bridge_last_message"] = error_text[:240]
        return {"status": "failed", "error": error_text}


def run_chatgpt_bidirectional_full_sync(
    source: str = "manual_full_sync",
    force: bool = True,
    batch_size: int | None = None,
    max_batches: int | None = None,
    field_max_chars: int | None = None,
    only_batch_indexes: list[int] | None = None,
    progress_callback=None,
    hard_deadline_ts: float | None = None,
    api_timeout_seconds: int | None = None,
) -> dict:
    if not CHATGPT_BRIDGE_ENABLED:
        return {"status": "disabled", "reason": "CHATGPT_BRIDGE_ENABLED=false"}
    if not CHATGPT_BRIDGE_FULL_SYNC_ENABLED:
        return {"status": "disabled", "reason": "CHATGPT_BRIDGE_FULL_SYNC_ENABLED=false"}
    if not OPENAI_ENABLED:
        return {"status": "skipped", "reason": "OPENAI_API_KEY unavailable"}

    batches, sync_summary = build_chatgpt_bridge_full_sync_batches(
        batch_size=batch_size,
        field_max_chars=field_max_chars,
    )
    if not batches:
        result = {"status": "completed", "message": "no_data", "summary": sync_summary}
        CNS_RUNTIME["chatgpt_bridge_full_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        CNS_RUNTIME["chatgpt_bridge_full_last_status"] = "completed"
        CNS_RUNTIME["chatgpt_bridge_full_last_message"] = "no_data"
        return result

    cap = max(1, min(int(max_batches or CHATGPT_BRIDGE_FULL_SYNC_MAX_BATCHES), len(batches)))
    selected_batches = []
    only_set = set()
    if isinstance(only_batch_indexes, list):
        for item in only_batch_indexes:
            try:
                index_num = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= index_num <= len(batches):
                only_set.add(index_num)

    if only_set:
        for index_num in sorted(only_set):
            batch_copy = dict(batches[index_num - 1])
            batch_copy["_global_batch_index"] = index_num
            selected_batches.append(batch_copy)
    else:
        for index_num, batch in enumerate(batches[:cap], start=1):
            batch_copy = dict(batch)
            batch_copy["_global_batch_index"] = index_num
            selected_batches.append(batch_copy)
    acknowledgements = []
    failed = []
    rows_synced = 0
    started_at = time.time()
    timed_out = False
    call_timeout = max(10, min(300, int(api_timeout_seconds or CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS)))

    if callable(progress_callback):
        progress_callback(
            {
                "phase": "initial_sync",
                "current_round": 0,
                "total_batches": len(selected_batches),
                "processed_batches": 0,
                "acknowledged_batches": 0,
                "failed_batches": 0,
                "rows_synced": 0,
                "current_batch_index": 0,
                "current_table": "",
                "elapsed_seconds": 0,
            }
        )

    for batch_index, batch in enumerate(selected_batches, start=1):
        if hard_deadline_ts and time.time() >= float(hard_deadline_ts):
            timed_out = True
            failed.append(
                {
                    "batch_index": int(batch.get("_global_batch_index") or batch_index),
                    "table": batch.get("table", ""),
                    "rows": len(batch.get("rows") or []),
                    "attempts": 0,
                    "error": "hard_timeout_exceeded_before_batch",
                }
            )
            break
        global_batch_index = int(batch.get("_global_batch_index") or batch_index)
        table_name = batch["table"]
        rows = batch["rows"]
        prompt_payload = {
            "source": source,
            "mode": "full_sync",
            "batch_index": global_batch_index,
            "batch_total": len(selected_batches),
            "table": table_name,
            "table_chunk_index": batch["table_chunk_index"],
            "table_chunk_total": batch["table_chunk_total"],
            "rows_in_batch": len(rows),
            "rows": rows,
        }
        prompt = (
            "你正在接收多智能體雙向學習的全量資料同步批次。"
            "請完成資料吸收並回傳精簡 JSON，格式為："
            "{\"ack\":true,\"table\":\"...\",\"rows_received\":N,\"insights\":[...],\"risks\":[...]}。"
            "僅提供摘要，不要回吐完整敏感內容。\n\n"
            f"批次資料：{json.dumps(prompt_payload, ensure_ascii=False)}"
        )

        attempts = 0
        last_error = ""
        for attempt in range(CHATGPT_BRIDGE_FULL_SYNC_RETRY + 1):
            if hard_deadline_ts and time.time() >= float(hard_deadline_ts):
                timed_out = True
                last_error = "hard_timeout_exceeded_during_batch"
                break
            attempts = attempt + 1
            try:
                response_text = query_openai_compatible(
                    prompt,
                    api_key=OPENAI_API_KEY,
                    api_base=OPENAI_API_BASE,
                    model_name=CHATGPT_BRIDGE_MODEL,
                    provider_name="ChatGPT Bridge Full Sync",
                    request_timeout=call_timeout,
                )
                response_preview = _bridge_string(response_text, 500)
                acknowledgements.append({
                    "batch_index": global_batch_index,
                    "table": table_name,
                    "rows_received": len(rows),
                    "ack_preview": response_preview,
                    "attempts": attempts,
                })
                rows_synced += len(rows)
                learn_agent_signals(
                    "learner",
                    [table_name, response_preview, json.dumps({"rows": len(rows)}, ensure_ascii=False)],
                    source="chatgpt_bridge_full_sync",
                    message=f"full_sync:{table_name}:{global_batch_index}",
                )
                if callable(progress_callback):
                    progress_callback(
                        {
                            "phase": "initial_sync",
                            "current_round": 0,
                            "total_batches": len(selected_batches),
                            "processed_batches": batch_index,
                            "acknowledged_batches": len(acknowledgements),
                            "failed_batches": len(failed),
                            "rows_synced": rows_synced,
                            "current_batch_index": global_batch_index,
                            "current_table": table_name,
                            "elapsed_seconds": round(time.time() - started_at, 3),
                        }
                    )
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < CHATGPT_BRIDGE_FULL_SYNC_RETRY and CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS > 0:
                    if hard_deadline_ts and time.time() >= float(hard_deadline_ts):
                        timed_out = True
                        last_error = "hard_timeout_exceeded_before_retry_backoff"
                        break
                    time.sleep(CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS * (attempt + 1))
        else:
            failed.append({
                "batch_index": global_batch_index,
                "table": table_name,
                "rows": len(rows),
                "attempts": attempts,
                "error": last_error,
            })

        if timed_out:
            break
        if callable(progress_callback):
            progress_callback(
                {
                    "phase": "initial_sync",
                    "current_round": 0,
                    "total_batches": len(selected_batches),
                    "processed_batches": batch_index,
                    "acknowledged_batches": len(acknowledgements),
                    "failed_batches": len(failed),
                    "rows_synced": rows_synced,
                    "current_batch_index": global_batch_index,
                    "current_table": table_name,
                    "elapsed_seconds": round(time.time() - started_at, 3),
                }
            )

    elapsed = round(time.time() - started_at, 3)
    if timed_out:
        status = "timeout"
    else:
        status = "completed" if not failed else ("partial_failed" if acknowledgements else "failed")
    result = {
        "status": status,
        "model": CHATGPT_BRIDGE_MODEL,
        "source": source,
        "force": bool(force),
        "elapsed_seconds": elapsed,
        "api_timeout_seconds": call_timeout,
        "hard_timeout_seconds": int(max(0, hard_deadline_ts - started_at)) if hard_deadline_ts else None,
        "hard_timeout_triggered": timed_out,
        "retry_per_batch": CHATGPT_BRIDGE_FULL_SYNC_RETRY,
        "retry_backoff_seconds": CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS,
        "rows_synced": rows_synced,
        "batches_total_available": len(batches),
        "batches_processed": len(selected_batches),
        "batches_acknowledged": len(acknowledgements),
        "batches_failed": len(failed),
        "summary": sync_summary,
        "only_batch_indexes": sorted(only_set),
        "acknowledgements": acknowledgements[-20:],
        "failed": failed,
    }

    heartbeat_level = "completed" if status == "completed" else "failed"
    heartbeat_summary = "全量雙向學習同步完成" if status == "completed" else "全量雙向學習同步部分/全部失敗"
    record_cns_heartbeat(
        "chatgpt_bridge_full_sync",
        heartbeat_level,
        heartbeat_summary,
        {
            "status": status,
            "rows_synced": rows_synced,
            "batches_processed": len(selected_batches),
            "batches_failed": len(failed),
            "hard_timeout_triggered": timed_out,
            "source": source,
        },
    )
    emit_notification(
        "learner",
        "ChatGPT 全量雙向學習同步",
        f"狀態 {status}，同步 {rows_synced} 筆資料",
        level="info" if status == "completed" else "warning",
        category="learning",
        details={
            "status": status,
            "rows_synced": rows_synced,
            "batches_processed": len(selected_batches),
            "batches_failed": len(failed),
        },
    )
    CNS_RUNTIME["chatgpt_bridge_full_last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    CNS_RUNTIME["chatgpt_bridge_full_last_status"] = status
    CNS_RUNTIME["chatgpt_bridge_full_last_message"] = f"rows={rows_synced}, failed_batches={len(failed)}"
    if callable(progress_callback):
        progress_callback(
            {
                "phase": "finished",
                "current_round": 0,
                "total_batches": len(selected_batches),
                "processed_batches": len(selected_batches),
                "acknowledged_batches": len(acknowledgements),
                "failed_batches": len(failed),
                "rows_synced": rows_synced,
                "current_batch_index": 0,
                "current_table": "",
                "elapsed_seconds": elapsed,
            }
        )
    return result


def run_full_sync_with_recovery(
    payload: dict,
    source: str = "external_sync_full",
    progress_callback=None,
    hard_timeout_seconds: int | None = None,
    api_timeout_seconds: int | None = None,
) -> dict:
    data = payload if isinstance(payload, dict) else {}
    force = _coerce_bool(data.get("force", True), True)
    batch_size = data.get("batch_size")
    max_batches = data.get("max_batches")
    field_max_chars = data.get("field_max_chars")
    only_batch_indexes = data.get("only_batch_indexes") if isinstance(data.get("only_batch_indexes"), list) else None
    auto_recover = _coerce_bool(data.get("auto_recover", SYNC_AUTO_RECOVER_ENABLED), SYNC_AUTO_RECOVER_ENABLED)
    max_rounds = max(0, min(int(data.get("auto_recover_max_rounds", SYNC_AUTO_RECOVER_MAX_ROUNDS)), 5))
    fallback_field_max_chars = data.get("auto_recover_field_max_chars", SYNC_AUTO_RECOVER_REDUCE_FIELD_MAX_CHARS)
    api_timeout = _to_int_or_none(data.get("api_timeout_seconds"))
    if api_timeout is None:
        api_timeout = _to_int_or_none(api_timeout_seconds)
    api_timeout = max(10, min(300, int(api_timeout or CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS)))
    hard_timeout = _to_int_or_none(data.get("hard_timeout_seconds"))
    if hard_timeout is None:
        hard_timeout = _to_int_or_none(hard_timeout_seconds)
    hard_timeout = max(30, min(7200, int(hard_timeout or CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS)))
    hard_deadline_ts = time.time() + hard_timeout

    if callable(progress_callback):
        progress_callback(
            {
                "phase": "initial_sync",
                "current_round": 0,
                "total_batches": 0,
                "processed_batches": 0,
                "acknowledged_batches": 0,
                "failed_batches": 0,
                "rows_synced": 0,
                "current_batch_index": 0,
                "current_table": "",
                "elapsed_seconds": 0,
            }
        )

    result = run_chatgpt_bidirectional_full_sync(
        source=source,
        force=force,
        batch_size=batch_size,
        max_batches=max_batches,
        field_max_chars=field_max_chars,
        only_batch_indexes=only_batch_indexes,
        progress_callback=progress_callback,
        hard_deadline_ts=hard_deadline_ts,
        api_timeout_seconds=api_timeout,
    )

    recovery_rounds = []
    if auto_recover and str(result.get("status", "")).lower() == "partial_failed":
        remaining_failed = list(result.get("failed") or [])
        for round_index in range(1, max_rounds + 1):
            if time.time() >= hard_deadline_ts:
                result["status"] = "timeout"
                result["hard_timeout_triggered"] = True
                break
            failed_indexes = []
            for row in remaining_failed:
                try:
                    idx = int(row.get("batch_index"))
                except Exception:
                    continue
                if idx > 0 and idx not in failed_indexes:
                    failed_indexes.append(idx)
            if not failed_indexes:
                break

            if callable(progress_callback):
                progress_callback(
                    {
                        "phase": "recovery_sync",
                        "current_round": round_index,
                        "total_batches": len(failed_indexes),
                        "processed_batches": 0,
                        "acknowledged_batches": 0,
                        "failed_batches": 0,
                        "rows_synced": int(result.get("rows_synced") or 0),
                        "current_batch_index": 0,
                        "current_table": "",
                        "elapsed_seconds": round(max(0.0, time.time() - (hard_deadline_ts - hard_timeout)), 3),
                    }
                )
            recovery_result = run_chatgpt_bidirectional_full_sync(
                source=f"{source}:recovery_round_{round_index}",
                force=True,
                batch_size=batch_size,
                max_batches=max_batches,
                field_max_chars=fallback_field_max_chars,
                only_batch_indexes=failed_indexes,
                progress_callback=progress_callback,
                hard_deadline_ts=hard_deadline_ts,
                api_timeout_seconds=api_timeout,
            )

            recovery_rounds.append({
                "round": round_index,
                "requested_batches": failed_indexes,
                "status": recovery_result.get("status"),
                "rows_synced": recovery_result.get("rows_synced"),
                "batches_failed": recovery_result.get("batches_failed"),
                "failed": recovery_result.get("failed") or [],
            })
            remaining_failed = list(recovery_result.get("failed") or [])
            if str(recovery_result.get("status", "")).lower() == "timeout":
                result["status"] = "timeout"
                result["hard_timeout_triggered"] = True
                break
            if not remaining_failed:
                break

        total_recovered_rows = sum(int(item.get("rows_synced") or 0) for item in recovery_rounds)
        final_failed = recovery_rounds[-1].get("failed", []) if recovery_rounds else remaining_failed
        if recovery_rounds:
            result["rows_synced"] = int(result.get("rows_synced") or 0) + total_recovered_rows
            result["batches_failed"] = len(final_failed)
            result["failed"] = final_failed
            result["status"] = "completed" if len(final_failed) == 0 else "partial_failed"
            result["recovery_rounds"] = recovery_rounds
            result["auto_recover"] = {
                "enabled": True,
                "max_rounds": max_rounds,
                "fallback_field_max_chars": fallback_field_max_chars,
            }
    result["api_timeout_seconds"] = api_timeout
    result["hard_timeout_seconds"] = hard_timeout

    return result


def create_sync_agent_task(sync_mode: str, request_payload: dict, sync_result: dict) -> dict:
    status = str((sync_result or {}).get("status") or "").strip().lower()
    failed_count = int((sync_result or {}).get("batches_failed") or 0)
    rows_synced = int((sync_result or {}).get("rows_synced") or 0)
    level = "completed" if status == "completed" else ("failed" if status in {"failed", "partial_failed", "timeout", "disabled"} or failed_count > 0 else "running")

    task = AgentTask(
        title=f"外部同步任務（{sync_mode}）",
        description=f"來源 /sync，模式 {sync_mode}",
        goals="驗證 API 請求、確保資料同步、產生可追蹤學習紀錄",
        style_guidelines="回報精簡、可核對、可追蹤",
        constraints="不可暴露敏感 token；僅輸出必要狀態",
        output_format="json_status",
        model_hint="auto",
        assigned_agent="learner",
        agent_label="sync.coordinator",
        issue_tags=json.dumps(
            infer_signal_tags(
                "sync",
                sync_mode,
                str(request_payload or ""),
                str(sync_result or ""),
            ),
            ensure_ascii=False,
        ),
        workflow_stage="external_sync",
        workflow_run_id=f"sync_{uuid.uuid4().hex[:12]}",
        source_channel="sync_api",
        status=level,
        result=json.dumps(
            {
                "sync_mode": sync_mode,
                "status": status,
                "rows_synced": rows_synced,
                "batches_failed": failed_count,
                "source": (sync_result or {}).get("source"),
            },
            ensure_ascii=False,
        ),
        learning_report=json.dumps(
            build_learning_report(
                {
                    "title": f"外部同步任務（{sync_mode}）",
                    "description": "API 驗證與雙向學習同步",
                    "assigned_agent": "learner",
                },
                json.dumps(sync_result or {}, ensure_ascii=False)[:1800],
                agent_label="sync.coordinator",
                issue_tags=infer_signal_tags("sync", sync_mode, status),
            ),
            ensure_ascii=False,
        ),
    )
    db.session.add(task)
    db.session.commit()
    emit_task_lifecycle_event(task, "task.sync.recorded", {"sync_mode": sync_mode})
    learn_agent_signals(
        "learner",
        [sync_mode, json.dumps(sync_result or {}, ensure_ascii=False)],
        source="external_sync_agent_task",
        message=f"sync:{sync_mode}:{status}",
    )
    return serialize_agent_task(task)


def trigger_autonomous_learning_async(source: str = 'chat_runtime'):
    if not LEARNING_MODE:
        return

    def _worker():
        try:
            with app.app_context():
                autonomous_learning()
                run_cns_cycle(cycle_type=source)
                run_chatgpt_bidirectional_sync(source=source)
        except Exception as exc:
            logging.warning('Async learning failed: %s', exc)
        finally:
            _remove_db_session_safely()

    threading.Thread(target=_worker, name='chat-learning-worker', daemon=True).start()

def auto_select_model(message):
    """Dynamically select model based on message content and system status"""
    local_available = ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available()
    if ALLOW_LOCAL_MODEL_FALLBACK and not local_available:
        logging.warning("Ollama not available, switching to cloud models if needed")

    non_language = is_non_language_processing_request(message)

    if non_language:
        execution_choice = select_execution_model_choice()
        if execution_choice != "auto":
            return execution_choice

    if PREFER_CLOUD_MODELS:
        cloud_choice = select_preferred_cloud_model(for_execution=False)
        if cloud_choice:
            return cloud_choice
        if local_available:
            return 'tinyllama'

    message_lower = str(message or '').lower()
    if len(message) > 200 or any(keyword in message_lower for keyword in ['explain', 'analyze', 'code', 'research']):
        if GEMINI_ENABLED:
            return 'gemini'
        if OPENROUTER_ENABLED:
            return 'openrouter'
        if GROQ_ENABLED:
            return 'groq'
        if OPENAI_ENABLED:
            return 'openai'
        if is_zzz_provider_ready():
            return 'zhizengzeng'
        if TOGETHER_ENABLED:
            return 'together'
        if HF_ENABLED:
            return 'huggingface'
        return 'gpt2'

    if local_available and not non_language:
        return 'tinyllama'
    if OPENROUTER_ENABLED:
        return 'openrouter'
    if GROQ_ENABLED:
        return 'groq'
    if GEMINI_ENABLED:
        return 'gemini'
    if OPENAI_ENABLED:
        return 'openai'
    if is_zzz_provider_ready():
        return 'zhizengzeng'
    if get_gpt2_generator():
        return 'gpt2'
    return 'huggingface'


def query_openai_compatible(
    prompt,
    api_key: str,
    api_base: str,
    model_name: str,
    provider_name: str,
    extra_headers: dict | None = None,
    request_timeout: int | float = 30,
):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }
    try:
        response = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=request_timeout,
        )
        if response.status_code == 200:
            logging.info("%s API call successful", provider_name)
            data = response.json()
            return data["choices"][0]["message"]["content"]

        error_text = response.text[:500]
        logging.error("%s API error: %s %s", provider_name, response.status_code, error_text)
        raise Exception(f"{provider_name} API error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error("%s request failed: %s", provider_name, e)
        raise


def query_openai(prompt):
    if not OPENAI_ENABLED:
        raise Exception("OpenAI API key required")
    return query_openai_compatible(
        prompt,
        api_key=OPENAI_API_KEY,
        api_base=OPENAI_API_BASE,
        model_name=OPENAI_MODEL,
        provider_name="OpenAI",
    )


def query_openrouter(prompt):
    if not OPENROUTER_ENABLED:
        raise Exception("OpenRouter API key required")
    return query_openai_compatible(
        prompt,
        api_key=OPENROUTER_API_KEY,
        api_base=OPENROUTER_API_BASE,
        model_name=OPENROUTER_MODEL,
        provider_name="OpenRouter",
        extra_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        },
    )


def query_groq(prompt):
    if not GROQ_ENABLED:
        raise Exception("Groq API key required")
    return query_openai_compatible(
        prompt,
        api_key=GROQ_API_KEY,
        api_base=GROQ_API_BASE,
        model_name=GROQ_MODEL,
        provider_name="Groq",
    )


def query_zhizengzeng(prompt):
    zzz_guard = get_zzz_runtime_guard()
    if not zzz_guard.get("ready"):
        reasons = ", ".join(zzz_guard.get("reasons", []))
        raise Exception(f"ZZZ provider blocked by fail-closed policy: {reasons}")
    protocol_headers = _build_zzz_security_headers(prompt)
    return query_openai_compatible(
        prompt,
        api_key=ZZZ_API_KEY,
        api_base=ZZZ_API_BASE,
        model_name=ZZZ_MODEL,
        provider_name="Zhizengzeng ZZZ API",
        extra_headers=protocol_headers,
    )



def query_gemini(prompt):
    if not GEMINI_ENABLED:
        raise Exception("Gemini API key required")

    endpoint = f"{GEMINI_API_BASE.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7},
    }
    try:
        response = requests.post(
            endpoint,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            candidates = data.get('candidates') or []
            if candidates:
                parts = (((candidates[0] or {}).get('content') or {}).get('parts') or [])
                texts = [str(p.get('text', '')) for p in parts if isinstance(p, dict)]
                result = ''.join(texts).strip()
                if result:
                    return result
            raise Exception('Gemini API response parse failed')

        logging.error("Gemini API error: %s %s", response.status_code, response.text[:500])
        raise Exception(f"Gemini API error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error("Gemini request failed: %s", e)
        raise


def query_nvidia(prompt):
    if not NVIDIA_ENABLED:
        raise Exception("NVIDIA API key required")
    return query_openai_compatible(
        prompt,
        api_key=NVIDIA_API_KEY,
        api_base=NVIDIA_API_BASE,
        model_name=NVIDIA_MODEL,
        provider_name="NVIDIA",
    )


def query_huggingface(prompt):
    headers = {"Authorization": f"Bearer {HF_API_KEY}"} if HF_API_KEY else {}
    payload = {"inputs": prompt, "parameters": {"max_length": 100, "temperature": 0.7}}
    try:
        response = requests.post(f"https://api-inference.huggingface.co/models/{HF_MODEL}", 
                               headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            logging.info("Hugging Face API call successful")
            return response.json()[0]['generated_text']
        else:
            logging.error(f"Hugging Face API error: {response.status_code}")
            raise Exception(f"Hugging Face API error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Hugging Face request failed: {e}")
        raise

def query_together(prompt):
    if not TOGETHER_ENABLED:
        raise Exception("Together API key required for data security")
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": TOGETHER_MODEL,
        "prompt": prompt,
        "max_tokens": 100,
        "temperature": 0.7
    }
    try:
        response = requests.post("https://api.together.xyz/inference", headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            logging.info("Together AI API call successful")
            return response.json()['output']['choices'][0]['text']
        else:
            logging.error(f"Together AI API error: {response.status_code}")
            raise Exception(f"Together AI API error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Together AI request failed: {e}")
        raise

def get_xiaobian_profile() -> dict:
    """Return the stored 小編 user profile (preferences/context)."""
    profile = XiaobianProfile.query.filter_by(key='user_profile').first()
    if not profile:
        return {}
    try:
        return json.loads(profile.value)
    except Exception:
        return {}


def set_xiaobian_profile(profile_data: dict):
    """Store/update the 小編 user profile."""
    profile = XiaobianProfile.query.filter_by(key='user_profile').first()
    if not profile:
        profile = XiaobianProfile(key='user_profile', value=json.dumps(profile_data))
        db.session.add(profile)
    else:
        profile.value = json.dumps(profile_data)
    db.session.commit()


def create_specialist_prompt(agent_key: str, task_data: dict, conversation: list = None) -> str:
    signal_tags = infer_signal_tags(
        task_data.get('title', ''),
        task_data.get('description', ''),
        task_data.get('goals', ''),
        task_data.get('style_guidelines', ''),
        task_data.get('constraints', ''),
    )
    profile = get_xiaobian_profile() if agent_key == 'xiaobian' else None
    return build_agent_prompt(
        agent_key,
        task_data,
        conversation=conversation,
        profile=profile,
        signal_tags=signal_tags,
    )


def infer_task_domain(task_data: dict, signal_tags: list | None = None) -> str:
    title = str(task_data.get('title', '') or '')
    description = str(task_data.get('description', '') or '')
    goals = str(task_data.get('goals', '') or '')
    style_guidelines = str(task_data.get('style_guidelines', '') or '')
    constraints = str(task_data.get('constraints', '') or '')
    output_format = str(task_data.get('output_format', '') or '')
    interaction_mode = str(task_data.get('interaction_mode', '') or '')
    creative_submode = str(task_data.get('creative_submode', '') or '')
    video_workflow_engine = str(task_data.get('video_workflow_engine', '') or '')

    signal_tags = signal_tags or infer_signal_tags(title, description, goals, style_guidelines, constraints)
    intent_source = " ".join(
        [
            title,
            description,
            goals,
            style_guidelines,
            constraints,
            output_format,
            interaction_mode,
            creative_submode,
            video_workflow_engine,
            " ".join(signal_tags or []),
        ]
    ).lower()

    def has_any(*keywords: str) -> bool:
        return any(keyword.lower() in intent_source for keyword in keywords if keyword)

    if has_any(
        "短影片", "長影片", "影片", "影像", "分鏡", "鏡位", "旁白", "字幕",
        "reels", "shorts", "tiktok", "video", "storyboard", "shot list",
        "image_to_video", "text_to_video", "image to video", "text to video",
        "creative_submode", "video_workflow", "comfyui", "cogvideox", "wan",
        "hunyuanvideo", "open_sora", "open-sora",
    ):
        return "video"
    if has_any("投資", "估值", "dcf", "bear case", "bull case", "thesis breaker", "盡職調查"):
        return "investment"
    if has_any("稅", "稅務", "etr", "transfer pricing", "asc 740", "tax", "節稅"):
        return "tax"
    if has_any("預算", "forecast", "variance", "fp&a", "aop", "unit economics", "滾動預測"):
        return "fpa"
    if has_any("月結", "對帳", "內控", "審計", "gaap", "reconciliation", "controller", "bookkeeper"):
        return "accounting"
    if has_any("章節", "草稿", "第一人稱", "book", "chapter", "editorial", "proof gaps"):
        return "writing"
    if has_any("品牌", "定位", "brand", "message architecture", "tone of voice", "商標"):
        return "brand"
    if has_any("prompt", "midjourney", "dall-e", "stable diffusion", "flux", "攝影提示詞", "negative prompt"):
        return "image_prompt"
    return "design"


def build_runtime_task_context(data: dict | None = None) -> dict:
    payload = data or {}
    interaction_mode = str(payload.get('interaction_mode', '') or '').strip().lower()
    creative_submode = str(payload.get('creative_submode', '') or '').strip().lower()
    video_workflow_engine = str(payload.get('video_workflow_engine', '') or '').strip().lower()
    parts = []
    if interaction_mode:
        parts.append(f"互動模式={interaction_mode}")
    if creative_submode:
        parts.append(f"創意子模式={creative_submode}")
    if video_workflow_engine:
        parts.append(f"影片工作流引擎={video_workflow_engine}")
    return {
        'interaction_mode': interaction_mode,
        'creative_submode': creative_submode,
        'video_workflow_engine': video_workflow_engine,
        'context_text': "；".join(parts),
    }


def create_xiaobian_prompt(task_data: dict, profile: dict = None, conversation: list = None) -> str:
    """Generate a structured prompt for 小編 (design assistant)."""
    title = task_data.get('title', '未提供任務標題')
    description = task_data.get('description', '')
    goals = task_data.get('goals', '')
    style_guidelines = task_data.get('style_guidelines', '')
    constraints = task_data.get('constraints', '')
    output_format = task_data.get('output_format', '')
    signal_tags = infer_signal_tags(title, description, goals, style_guidelines, constraints)
    domain = infer_task_domain(task_data, signal_tags=signal_tags)

    instructions = [
        "你是小編設計師，能同時處理品牌、視覺、影片企劃、敘事、寫作、財務、投研與稅務相關任務。",
        "你必須先判斷使用者目前真正要的是哪一種任務，再用對應專業框架回覆，不能把所有問題都硬套成 UI / 配色 / 版面建議。",
        "若使用者是在問『你有沒有某種能力』或『你能不能做某件事』，先直接回答能力邊界，再補充可提供的內容與限制。",
        "請以清晰、結構化、可直接執行的方式回覆；若沒有必要，不要強行提供 2~3 個方案。",
        "只有在任務真的涉及視覺設計、版型、色彩、字體、介面時，才提供配色、字體、版面與無障礙建議。",
        "若任務包含問題診斷，請明確指出問題標籤、觀察到的風險，以及可供後續學習追蹤的重點。"
    ]

    domain_instruction_map = {
        "video": [
            "本次任務判定為 AI 影片/短影音/長影音相關。",
            "你要優先回答：是否具備影片能力、支援哪些流程、目前系統內是『企劃/分鏡/工作流設計』能力，還是『已實際安裝可直接生成』能力。",
            "若是能力詢問，先直接回答『有，且目前偏向企劃、分鏡、提示詞與開源工作流選型』，再列出短影片、長影片、文字轉影片、圖片轉影片、字幕/旁白、工作流規劃。",
            "若使用者要求影片方案，輸出優先順序為：1) 能力判斷 2) 可做範圍 3) 建議工作流 4) 下一步。",
            "不要回成 UI 設計建議，除非使用者明確在問影片頁面介面或品牌視覺。"
        ],
        "brand": [
            "本次任務判定為品牌/定位相關。",
            "請優先使用品牌定位、訊息架構、語調、資產一致性與保護策略框架。"
        ],
        "image_prompt": [
            "本次任務判定為影像提示詞/生成相關。",
            "請以 Subject / Environment / Lighting / Technical / Style 結構輸出，必要時補上 negative prompt 與平台參數。"
        ],
        "writing": [
            "本次任務判定為章節/寫作相關。",
            "請優先輸出章節目標、草稿、編輯註記、修訂問題，而不是設計建議。"
        ],
        "accounting": [
            "本次任務判定為會計/內控/月結相關。",
            "請優先提供流程、對帳、差異、風險與稽核就緒建議。"
        ],
        "fpa": [
            "本次任務判定為 FP&A / 預算 / 預測相關。",
            "請優先提供 driver、variance、forecast、scenario 與 trade-off。"
        ],
        "investment": [
            "本次任務判定為投資研究相關。",
            "請優先提供 thesis、bull/bear case、valuation、catalyst、risk 與 thesis breakers。"
        ],
        "tax": [
            "本次任務判定為稅務策略相關。",
            "請優先提供 tax memo、合規邊界、風險曝險、文件需求與實作步驟。"
        ],
        "design": [
            "本次任務判定為視覺/介面設計相關。",
            "請提供設計建議、必要時可選方案、以及無障礙/一致性風險。"
        ],
    }

    prompt_parts = ["-----", "【系統指令】", "\n".join(instructions), ""]
    prompt_parts.extend(["【任務領域判定】", domain, ""])
    prompt_parts.extend(["【領域補充指令】", "\n".join(domain_instruction_map.get(domain, domain_instruction_map["design"])), ""])

    if profile:
        prompt_parts.extend(["【已知使用者喜好 / 風格】", json.dumps(profile, ensure_ascii=False, indent=2), ""])  # include existing profile

    prompt_parts.extend([
        "【任務標題】",
        title,
        "",
        "【任務描述】",
        description,
        "",
        "【目標 / KPI】",
        goals,
        "",
        "【風格指引】",
        style_guidelines,
        "",
        "【限制條件】",
        constraints,
        "",
        "【輸出格式需求】",
        output_format,
        "",
        "【訊號標籤】",
        "、".join(signal_tags),
    ])

    if conversation:
        prompt_parts.extend(["", "【對話紀錄】"])
        for item in conversation:
            role = item.get('role', 'user')
            text = item.get('text', '')
            prompt_parts.append(f"[{role.upper()}] {text}")

    prompt_parts.extend([
        "",
        "請依據上述內容，提供：",
        "1) 先直接回答使用者真正的問題，不要答非所問。",
        "2) 依任務領域輸出最合適的專業內容；只有 design 任務才固定輸出配色/字體/版面。",
        "3) 若適合，再補充可選方案、注意事項、風險與下一步。",
        "-----",
    ])

    return "\n".join([p for p in prompt_parts if p is not None and str(p).strip() != ""]) 


def generate_gpt2(prompt):
    """Generate text using the local GPT-2 model."""
    if GPT2_BACKEND in {"sidecar", "auto"} and GPT2_SIDECAR_URL:
        try:
            response = requests.post(
                GPT2_SIDECAR_URL,
                json={
                    "prompt": prompt,
                    "max_new_tokens": 150,
                    "temperature": 0.7,
                },
                timeout=GPT2_SIDECAR_TIMEOUT,
            )
            if response.status_code == 200:
                payload = response.json()
                if payload.get("generated_text"):
                    return payload["generated_text"]
        except requests.exceptions.RequestException as exc:
            logging.warning("GPT-2 sidecar unavailable: %s", exc)

    generator = get_gpt2_generator()
    if generator:
        try:
            # Generate text with controlled length and sampling
            outputs = generator(
                prompt,
                max_new_tokens=150,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True
            )
            return outputs[0]['generated_text']
        except Exception as e:
            logging.error(f"GPT-2 generation failed: {e}")
            return "本地 GPT-2 模型生成失敗"
    else:
        status = get_gpt2_status()
        if not status["ml_runtime_available"]:
            return "GPT-2 目前不可用：此 Python 3.14 環境沒有可用的 torch/tensorflow/flax。可改用 GPT2 sidecar。"
        return "本地 GPT-2 模型未初始化"


def xiaobian_generate(task_data: dict, conversation: list = None):
    """Generate response from 小編 agent using existing model pipeline."""
    # Include stored user profile in prompt if exists
    profile = get_xiaobian_profile()
    prompt = create_xiaobian_prompt(task_data, profile=profile, conversation=conversation)

    # Prefer cloud models for design-quality responses, but fall back to local
    model_choice = normalize_model_choice(task_data.get('model_hint', 'auto'))
    if model_choice != 'auto' and not is_model_choice_available(model_choice):
        logging.warning("Model %s unavailable for xiaobian, fallback to auto", model_choice)
        model_choice = 'auto'
    if model_choice == 'auto':
        if PREFER_CLOUD_MODELS:
            model_choice = select_preferred_cloud_model(for_execution=False)
            if not model_choice:
                if ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available():
                    model_choice = 'tinyllama'
                else:
                    model_choice = 'gpt2'
        elif ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available():
            model_choice = 'tinyllama'
        elif NVIDIA_ENABLED:
            model_choice = 'nvidia'
        elif OPENROUTER_ENABLED:
            model_choice = 'openrouter'
        elif GROQ_ENABLED:
            model_choice = 'groq'
        elif GEMINI_ENABLED:
            model_choice = 'gemini'
        elif OPENAI_ENABLED:
            model_choice = 'openai'
        elif is_zzz_provider_ready():
            model_choice = 'zhizengzeng'
        elif HF_ENABLED:
            model_choice = 'huggingface'
        elif TOGETHER_ENABLED:
            model_choice = 'together'
        else:
            model_choice = 'gpt2'

    if model_choice == 'openrouter':
        response = query_openrouter(prompt)
        model_used = f'OpenRouter ({OPENROUTER_MODEL})'
    elif model_choice == 'groq':
        response = query_groq(prompt)
        model_used = f'Groq ({GROQ_MODEL})'
    elif model_choice == 'openai':
        response = query_openai(prompt)
        model_used = f'OpenAI ({OPENAI_MODEL})'
    elif model_choice == 'gemini':
        response = query_gemini(prompt)
        model_used = f'Gemini ({GEMINI_MODEL})'
    elif model_choice == 'nvidia':
        response = query_nvidia(prompt)
        model_used = f'NVIDIA ({NVIDIA_MODEL})'
    elif model_choice == 'zhizengzeng':
        response = query_zhizengzeng(prompt)
        model_used = f'Zhizengzeng/智增增 ({ZZZ_MODEL})'
    elif model_choice == 'huggingface':
        response = query_huggingface(prompt)
        model_used = 'Free Cloud (Hugging Face)'
    elif model_choice == 'together':
        response = query_together(prompt)
        model_used = 'Free Cloud (Together AI)'
    elif model_choice == 'tinyllama':
        response = ollama.generate(model=LOCAL_OLLAMA_MODEL, prompt=prompt)['response']
        model_used = f'Local ({LOCAL_OLLAMA_MODEL})'
    elif model_choice == 'gpt2':
        response = generate_gpt2(prompt)
        model_used = 'Local (GPT-2)'
    else:
        response = "無法識別的模型選擇，請確認 model_hint。"
        model_used = 'Unknown'

    return response, model_used


def execute_prompt(prompt: str, model_choice: str = 'auto', prefer_cloud: bool = False):
    model_choice = normalize_model_choice(model_choice)
    if model_choice != 'auto' and not is_model_choice_available(model_choice):
        logging.warning("Model %s unavailable, fallback to auto", model_choice)
        model_choice = 'auto'

    if model_choice == 'auto':
        if is_non_language_processing_request(prompt):
            model_choice = select_execution_model_choice()

        if model_choice == 'auto' and (prefer_cloud or PREFER_CLOUD_MODELS):
            cloud_choice = select_preferred_cloud_model(for_execution=False)
            if cloud_choice:
                model_choice = cloud_choice

        if model_choice == 'auto' and ALLOW_LOCAL_MODEL_FALLBACK and check_ollama_available():
            model_choice = 'tinyllama'

        if model_choice == 'auto' and ALLOW_LOCAL_MODEL_FALLBACK and is_gpt2_available():
            model_choice = 'gpt2'

        if model_choice == 'auto':
            model_choice = auto_select_model(prompt)

    if model_choice == 'tinyllama':
        return ollama.generate(model=LOCAL_OLLAMA_MODEL, prompt=prompt)['response'], f"Local ({LOCAL_OLLAMA_MODEL})"
    if model_choice == 'gpt2':
        return generate_gpt2(prompt), "Local (GPT-2)"
    if model_choice == 'openai':
        return query_openai(prompt), f"OpenAI ({OPENAI_MODEL})"
    if model_choice == 'gemini':
        return query_gemini(prompt), f"Gemini ({GEMINI_MODEL})"
    if model_choice == 'nvidia':
        return query_nvidia(prompt), f"NVIDIA ({NVIDIA_MODEL})"
    if model_choice == 'openrouter':
        return query_openrouter(prompt), f"OpenRouter ({OPENROUTER_MODEL})"
    if model_choice == 'groq':
        return query_groq(prompt), f"Groq ({GROQ_MODEL})"
    if model_choice == 'zhizengzeng':
        return query_zhizengzeng(prompt), f"Zhizengzeng/智增增 ({ZZZ_MODEL})"
    if model_choice == 'huggingface':
        return query_huggingface(prompt), "Free Cloud (Hugging Face)"
    if model_choice == 'together':
        return query_together(prompt), "Free Cloud (Together AI)"
    return "未知模型選擇", "Unknown"


def generate_specialist_response(agent_key: str, task_data: dict, conversation: list = None):
    if agent_key == 'xiaobian':
        return xiaobian_generate(task_data, conversation=conversation)

    spec = get_agent_spec(agent_key)
    if not spec:
        raise ValueError(f"Unknown agent: {agent_key}")

    prompt = create_specialist_prompt(agent_key, task_data, conversation=conversation)
    prefer_cloud = PREFER_CLOUD_MODELS
    model_choice = task_data.get('model_hint', spec.preferred_model or 'auto')
    return execute_prompt(prompt, model_choice=model_choice, prefer_cloud=prefer_cloud)


def execute_task_for_agent(agent_key: str, user_message: str, task_data: dict = None, conversation: list = None):
    payload = dict(task_data or {})
    payload.setdefault('title', f'{agent_key} 任務')
    payload.setdefault('description', user_message)
    payload.setdefault('assigned_agent', agent_key)
    payload.setdefault('model_hint', 'auto')
    payload.setdefault('domain', infer_task_domain(payload))
    return generate_specialist_response(agent_key, payload, conversation=conversation)


def _is_provider_failure(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(marker in text for marker in [
        "api error",
        "timeout",
        "timed out",
        "connection",
        "service unavailable",
        "bad gateway",
        "rate limit",
        "too many requests",
        "model unavailable",
        " 410",
        " 429",
        " 500",
        " 502",
        " 503",
        " 504",
    ])


def _fallback_model_candidates(current_model: str = "auto") -> list[str]:
    ordered = ["groq", "openai", "openrouter", "together", "huggingface", "tinyllama", "gpt2"]
    normalized_current = normalize_model_choice(current_model or "auto")
    candidates = []
    for key in ordered:
        if key == normalized_current:
            continue
        if is_model_choice_available(key):
            candidates.append(key)
    return candidates


def execute_task_with_fallback(agent_key: str, user_message: str, task_data: dict = None, conversation: list = None):
    payload = dict(task_data or {})
    attempted = []
    primary_model = payload.get("model_hint", "auto")
    try:
        response, model_used = execute_task_for_agent(agent_key, user_message, task_data=payload, conversation=conversation)
        return response, model_used, attempted
    except Exception as exc:
        attempted.append({
            "model_hint": normalize_model_choice(primary_model),
            "error": str(exc),
        })
        if not _is_provider_failure(exc):
            raise

    for fallback_model in _fallback_model_candidates(primary_model):
        fallback_payload = dict(payload)
        fallback_payload["model_hint"] = fallback_model
        try:
            response, model_used = execute_task_for_agent(agent_key, user_message, task_data=fallback_payload, conversation=conversation)
            attempted.append({
                "model_hint": fallback_model,
                "status": "recovered",
            })
            return response, model_used, attempted
        except Exception as exc:
            attempted.append({
                "model_hint": fallback_model,
                "error": str(exc),
            })
            if not _is_provider_failure(exc):
                raise

    last_error = attempted[-1]["error"] if attempted else "unknown task execution failure"
    raise RuntimeError(f"All provider fallbacks failed: {last_error}")


def dispatch_task(user_message):
    """
    總管 (Central Dispatcher)
    分析使用者訊息，判斷要分派給哪個智能體。
    """
    lowered_message = str(user_message or '').lower()
    security_keywords = ['資安', '安全', '漏洞', 'api key', 'security', 'hardening', 'threat', 'audit', '白帽']
    if any(keyword in lowered_message for keyword in security_keywords):
        security_agent = _fuse_agent_key('whitehat') or 'whitehat'
        dispatch_payload = {
            'agent': security_agent,
            'reason': 'security_keyword_priority',
            'signal_tags': infer_signal_tags(user_message),
        }
        emit_notification(
            'dispatcher',
            '總管已分派任務',
            f"偵測到安全守門需求，優先分派給 {security_agent}",
            level='info',
            category='dispatch',
            details=dispatch_payload,
        )
        return dispatch_payload

    learned_agent, matched_rules = match_dispatcher_rule(user_message)
    if learned_agent:
        learned_agent = _fuse_agent_key(learned_agent) or learned_agent
        matched_patterns = [rule.pattern for rule in matched_rules]
        logging.info("總管使用已學習規則 %s，任務分派給：%s", matched_patterns, learned_agent)
        dispatch_payload = {
            'agent': learned_agent,
            'reason': 'learned_rules',
            'matched_patterns': matched_patterns,
            'signal_tags': infer_signal_tags(user_message),
        }
        emit_notification(
            'dispatcher',
            '總管已分派任務',
            f"依學習規則分派給 {learned_agent}",
            level='info',
            category='dispatch',
            details=dispatch_payload,
        )
        return dispatch_payload

    scored_agents = match_agent_signals(user_message)
    if scored_agents:
        selected_agent_raw = max(scored_agents.items(), key=lambda item: item[1])[0]
        selected_agent = _fuse_agent_key(selected_agent_raw) or selected_agent_raw
        logging.info("總管依訊號分數 %s 分派給：%s", scored_agents, selected_agent)
        dispatch_payload = {
            'agent': selected_agent,
            'reason': 'signal_scores',
            'scores': scored_agents,
            'signal_tags': infer_signal_tags(user_message),
        }
        emit_notification(
            'dispatcher',
            '總管已分派任務',
            f"依訊號分數分派給 {selected_agent}",
            level='info',
            category='dispatch',
            details=dispatch_payload,
        )
        return dispatch_payload

    logging.info("未偵測到特定關鍵字，任務分派給：通用聊天模型")
    dispatch_payload = {
        'agent': 'general',
        'reason': 'fallback',
        'signal_tags': infer_signal_tags(user_message),
    }
    emit_notification(
        'dispatcher',
        '總管分派預設路徑',
        '未命中特定訊號，交由 general 處理',
        level='warning',
        category='dispatch',
        details=dispatch_payload,
    )
    return dispatch_payload

def handle_general_chat(user_message, model_choice='auto'):
    """
    處理通用聊天請求
    """
    return execute_prompt(user_message, model_choice=model_choice, prefer_cloud=PREFER_CLOUD_MODELS)


def record_cns_heartbeat(cycle_type: str, status: str, summary: str, details=None):
    runtime_ts = datetime.now().isoformat()
    CNS_RUNTIME["last_cycle_at"] = runtime_ts
    CNS_RUNTIME["last_cycle_summary"] = summary
    if not CNS_HEARTBEAT_ENABLED:
        return None

    heartbeat = CNSHeartbeat(
        cycle_type=cycle_type,
        status=status,
        summary=summary[:255],
        details=json.dumps(details, ensure_ascii=False) if isinstance(details, (dict, list)) else str(details or ""),
    )
    db.session.add(heartbeat)
    db.session.commit()
    CNS_RUNTIME["last_cycle_at"] = heartbeat.created_at.isoformat()
    return heartbeat


def refresh_signal_memory_from_recent_activity(limit: int = 20) -> dict:
    learned_counts = {}

    recent_chats = ChatHistory.query.order_by(ChatHistory.timestamp.desc()).limit(limit).all()
    for chat in recent_chats:
        agent_key = _fuse_agent_key(chat.agent_type) or 'general'
        learned = learn_agent_signals(
            agent_key,
            [chat.user_message, chat.ai_response or '', chat.routing_reason or ''],
            source='chat_history',
            message=chat.user_message,
        )
        learned_counts[agent_key] = learned_counts.get(agent_key, 0) + len(learned)

    recent_tasks = AgentTask.query.order_by(AgentTask.updated_at.desc()).limit(limit).all()
    for task in recent_tasks:
        agent_key = _fuse_agent_key(task.assigned_agent) or 'xiaobian'
        learned = learn_agent_signals(
            agent_key,
            [task.title or '', task.description or '', task.result or '', task.constraints or ''],
            source='agent_task',
            message=task.description or task.title or '',
        )
        learned_counts[agent_key] = learned_counts.get(agent_key, 0) + len(learned)

    return learned_counts


def run_pending_agent_tasks(limit: int = 5) -> list:
    processed_tasks = []
    pending_tasks = AgentTask.query.filter_by(status='pending').order_by(AgentTask.created_at.asc()).limit(limit).all()

    for task in pending_tasks:
        blocked, blocked_by = _task_is_blocked(task)
        if blocked:
            blocker_details = _task_blocker_statuses(task)
            failed_blockers = [item for item in blocker_details if item["status"] in {"failed", "cancelled", "missing"}]
            if failed_blockers:
                task.status = 'failed'
                task.result = f"Blocked by failed dependencies: {json.dumps(failed_blockers, ensure_ascii=False)}"
                task.learning_report = json.dumps(
                    build_learning_report(
                        {
                            'title': task.title,
                            'description': task.description,
                            'assigned_agent': task.assigned_agent,
                        },
                        task.result,
                        agent_label=_normalize_agent_label_with_fusion(task.agent_label, assigned_agent=task.assigned_agent),
                    ),
                    ensure_ascii=False,
                )
                db.session.commit()
                emit_task_lifecycle_event(task, "task.failed_blocked", {"failed_blockers": failed_blockers})
                emit_notification(
                    'dispatcher',
                    '任務因前置失敗而終止',
                    f"Task #{task.id} 依賴失敗，已停止等待",
                    level='warning',
                    category='task',
                    details={'failed_blockers': failed_blockers},
                    related_task_id=task.id,
                )
                processed_tasks.append({
                    'task_id': task.id,
                    'assigned_agent': _fuse_agent_key(task.assigned_agent) or task.assigned_agent,
                    'status': task.status,
                    'failed_blockers': failed_blockers,
                })
                continue
            emit_notification(
                'dispatcher',
                '任務等待前置依賴',
                f"Task #{task.id} 等待 {blocked_by}",
                level='info',
                category='task',
                related_task_id=task.id,
            )
            continue
        agent_key = _fuse_agent_key(task.assigned_agent) or 'general'
        task.status = 'running'
        db.session.commit()
        emit_task_lifecycle_event(task, "task.running", {"assigned_agent": agent_key})
        emit_notification(
            agent_key,
            f'{agent_key} 開始處理任務',
            f"Task #{task.id} {task.title}",
            level='info',
            category='task',
            related_task_id=task.id,
        )

        task_payload = {
            'title': task.title,
            'description': task.description,
            'goals': task.goals,
            'style_guidelines': task.style_guidelines,
            'constraints': task.constraints,
            'output_format': task.output_format,
            'model_hint': task.model_hint or 'auto',
            'assigned_agent': agent_key,
            'agent_label': _normalize_agent_label_with_fusion(task.agent_label or infer_agent_label({'assigned_agent': agent_key, 'description': task.description}), assigned_agent=agent_key),
        }

        try:
            response, model_used, fallback_attempts = execute_task_with_fallback(
                _fuse_agent_key(agent_key) or agent_key,
                task.description,
                task_data=task_payload,
            )
            learning_report = build_learning_report(task_payload, response, agent_label=task_payload['agent_label'])
            task.result = response
            task.status = 'completed'
            task.learning_report = json.dumps(learning_report, ensure_ascii=False)
            task.issue_tags = json.dumps(learning_report['issue_tags'], ensure_ascii=False)
            learn_agent_signals(agent_key, [task.title, task.description, response], source='task_runner', message=task.description)
            processed_tasks.append({
                'task_id': task.id,
                'assigned_agent': agent_key,
                'model_used': model_used,
                'status': task.status,
            })
            emit_task_lifecycle_event(task, "task.completed", {"model_used": model_used})
            emit_notification(
                agent_key,
                f'{agent_key} 任務完成',
                f"Task #{task.id} 已完成",
                level='info',
                category='task',
                details={'model_used': model_used, 'fallback_attempts': fallback_attempts},
                related_task_id=task.id,
            )
        except Exception as exc:
            task.status = 'failed'
            task.result = str(exc)
            task.learning_report = json.dumps(build_learning_report(task_payload, str(exc), agent_label=task_payload['agent_label']), ensure_ascii=False)
            processed_tasks.append({
                'task_id': task.id,
                'assigned_agent': agent_key,
                'status': task.status,
                'error': str(exc),
            })
            emit_task_lifecycle_event(task, "task.failed", {"error": str(exc)})
            emit_notification(
                agent_key,
                f'{agent_key} 任務失敗',
                f"Task #{task.id} 失敗：{str(exc)[:120]}",
                level='error',
                category='task',
                related_task_id=task.id,
            )

        db.session.commit()

    return processed_tasks


def run_cns_cycle(cycle_type: str = 'manual') -> dict:
    learned_counts = refresh_signal_memory_from_recent_activity(limit=20)
    processed_tasks = run_pending_agent_tasks(limit=5)
    security_info = get_api_security_status()
    security_snapshot = {
        'security_index': security_info.get('security_index'),
        'risk_level': security_info.get('risk_level'),
        'finding_count': security_info.get('summary', {}).get('finding_count', 0),
        'high_severity_count': security_info.get('summary', {}).get('high_severity_count', 0),
    }
    summary = {
        'cycle_type': cycle_type,
        'learned_signal_counts': learned_counts,
        'processed_tasks': processed_tasks,
        'api_security': security_snapshot,
        'agents': list_agent_overviews(),
    }
    record_cns_heartbeat(cycle_type, 'completed', 'CNS 已完成一輪主動巡檢與學習', summary)
    signature = f"{security_snapshot['security_index']}|{security_snapshot['high_severity_count']}|{security_snapshot['finding_count']}"
    if signature != CNS_RUNTIME.get("last_security_signature"):
        CNS_RUNTIME["last_security_signature"] = signature
        CNS_RUNTIME["last_security_index"] = security_snapshot['security_index']
        if security_snapshot['high_severity_count'] > 0:
            emit_notification(
                _fused_safety_agent_key(),
                '申言者安全監測',
                f"偵測到 {security_snapshot['high_severity_count']} 項高風險 API 設定問題",
                level='warning',
                category='security',
                details=security_info.get('findings', [])[:6],
            )
        else:
            emit_notification(
                _fused_safety_agent_key(),
                '申言者安全巡檢完成',
                f"API 安全指數 {security_snapshot['security_index']}，目前無高風險項目",
                level='info',
                category='security',
                details=security_snapshot,
            )
    emit_notification(
        'dispatcher',
        'CNS 巡檢完成',
        f"{cycle_type} 巡檢完成，處理任務 {len(processed_tasks)} 個",
        level='info',
        category='cns',
        details={'cycle_type': cycle_type, 'processed_task_count': len(processed_tasks)},
    )
    return summary


def persist_agent_report_task(agent_key: str, title: str, description: str, report_payload: dict, issue_tags: list) -> AgentTask:
    serialized_report = json.dumps(report_payload, ensure_ascii=False, indent=2)
    task = AgentTask(
        title=title,
        description=description,
        goals='系統自動巡檢任務',
        constraints='以本地資料為準，不寫入外部來源',
        output_format='json_report',
        model_hint='system',
        assigned_agent=agent_key,
        agent_label=f'{agent_key}.system_audit',
        issue_tags=json.dumps(issue_tags, ensure_ascii=False),
        workflow_stage="system_audit",
        workflow_run_id=f"audit_{uuid.uuid4().hex[:12]}",
        source_channel="cns_audit",
        status='completed',
        result=serialized_report,
    )
    learning_report = build_learning_report(
        {'title': title, 'description': description, 'assigned_agent': agent_key},
        serialized_report,
        agent_label=task.agent_label,
        issue_tags=issue_tags,
    )
    task.learning_report = json.dumps(learning_report, ensure_ascii=False)
    db.session.add(task)
    db.session.commit()
    emit_task_lifecycle_event(task, "task.audit.recorded", {"agent": agent_key})
    learn_agent_signals(agent_key, [title, description, serialized_report], source='system_audit', message=description, boost=2)
    return task


def run_engineer_research_audit(custom_topics=None, custom_roots=None, max_results: int = 120, max_scan_files: int = 6000) -> dict:
    engineer_report = build_engineer_status_report()
    emit_notification(
        'engineer',
        '工程師完成系統評估',
        f"系統狀態：{engineer_report.get('status')}",
        level='info' if engineer_report.get('status') == 'healthy' else 'warning',
        category='health',
        details={'warning_count': engineer_report.get('warning_count', 0)},
    )
    engineer_task = persist_agent_report_task(
        'engineer',
        '工程師狀態判斷任務',
        '確認外接硬碟掛載、資料框架一致性、CNS 與模型狀態，並檢查是否有架構衝突。',
        engineer_report,
        issue_tags=['ops', 'database', 'api', 'performance'],
    )

    research_report = collect_local_research_data(
        custom_topics=custom_topics,
        custom_roots=custom_roots,
        max_results=max_results,
        max_scan_files=max_scan_files,
    )
    emit_notification(
        'researcher',
        '研究員收到工程師狀態後開始蒐集',
        f"依工程師評估 {engineer_report.get('status')}，完成本地資料掃描 {research_report.get('scanned_files', 0)} 檔案",
        level='info',
        category='research',
        details={'matched_count': research_report.get('matched_count', 0)},
    )
    researcher_task = persist_agent_report_task(
        'researcher',
        '研究員本地資料收集任務',
        '收集本地資料中與精神、心理學、精神疾病求生指南、腦神經科學、聖經相關內容。',
        research_report,
        issue_tags=['research', 'mental_health', 'neuroscience', 'bible'],
    )

    audit_summary = {
        'engineer_status': engineer_report.get('status'),
        'research_matches': research_report.get('matched_count', 0),
        'scanned_files': research_report.get('scanned_files', 0),
    }
    record_cns_heartbeat(
        'engineer_research_audit',
        'completed',
        '工程師檢查與研究員本地資料收集完成',
        audit_summary,
    )

    return {
        'message': '已完成工程師優先判斷與研究員本地資料收集',
        'engineer_report': engineer_report,
        'research_report': research_report,
        'tasks': {
            'engineer': serialize_agent_task(engineer_task),
            'researcher': serialize_agent_task(researcher_task),
        },
        'summary': audit_summary,
    }


def should_run_daily_job(now_local: time.struct_time = None) -> bool:
    if not ENABLE_DAILY_AUTONOMOUS_JOBS:
        return False

    current = now_local or time.localtime()
    today = time.strftime("%Y-%m-%d", current)
    if CNS_RUNTIME.get("last_daily_job_date") == today:
        return False
    if current.tm_hour < DAILY_JOB_HOUR:
        return False
    if current.tm_hour == DAILY_JOB_HOUR and current.tm_min < DAILY_JOB_MINUTE:
        return False
    return True


def run_daily_autonomous_jobs(trigger: str = 'scheduled') -> dict:
    result = run_engineer_research_audit(
        max_results=DAILY_JOB_MAX_RESULTS,
        max_scan_files=DAILY_JOB_MAX_SCAN_FILES,
    )
    now_struct = time.localtime()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S", now_struct)
    CNS_RUNTIME["last_daily_job_date"] = time.strftime("%Y-%m-%d", now_struct)
    CNS_RUNTIME["last_daily_job_at"] = now_iso
    CNS_RUNTIME["last_daily_job_summary"] = (
        f"{trigger}: engineer={result['summary']['engineer_status']}, "
        f"matches={result['summary']['research_matches']}"
    )
    record_cns_heartbeat(
        'daily_autonomous_jobs',
        'completed',
        '每日自主任務執行完成',
        {
            'trigger': trigger,
            'executed_at': now_iso,
            'summary': result['summary'],
        },
    )
    emit_notification(
        'dispatcher',
        '每日自主任務完成',
        CNS_RUNTIME["last_daily_job_summary"],
        level='info',
        category='daily_jobs',
        details=result.get('summary', {}),
    )
    return result


def cns_background_loop():
    while True:
        try:
            with app.app_context():
                run_cns_cycle(cycle_type='scheduled')
                if should_run_daily_job():
                    run_daily_autonomous_jobs(trigger='scheduled')
        except Exception as exc:
            with app.app_context():
                record_cns_heartbeat('scheduled', 'failed', 'CNS 巡檢失敗', {'error': str(exc)})
                logging.error("CNS background cycle failed: %s", exc)
        finally:
            _remove_db_session_safely()
        time.sleep(PROACTIVE_INTERVAL_SECONDS)


def start_cns_background_worker():
    if not ENABLE_PROACTIVE_CNS or CNS_RUNTIME["thread_started"]:
        return

    worker = threading.Thread(target=cns_background_loop, name='cns-background-worker', daemon=True)
    worker.start()
    CNS_RUNTIME["thread_started"] = True


def run_startup_bootstrap():
    CNS_RUNTIME["startup_bootstrap_status"] = "running"
    try:
        with app.app_context():
            db.create_all()
            ensure_database_schema()
            hydrate_chatgpt_bridge_runtime_from_db()
            if AUTO_MERGE_LEGACY_DATA:
                try:
                    merge_report = merge_legacy_data_into_current(dry_run=False, max_rows_per_table=12000)
                    merged_sources = len(merge_report.get("sources_merged", []))
                    imported_total = sum(int(v) for v in (merge_report.get("imported", {}) or {}).values())
                    if merged_sources > 0 or imported_total > 0:
                        record_cns_heartbeat(
                            'data_merge',
                            'completed',
                            '舊資料併入完成（目前資料為主）',
                            {
                                'sources_merged': merged_sources,
                                'imported_total': imported_total,
                            },
                        )
                except Exception as merge_exc:
                    record_cns_heartbeat(
                        'data_merge',
                        'failed',
                        '舊資料併入失敗',
                        {'error': str(merge_exc)},
                    )
                    logging.error("Legacy data merge failed: %s", merge_exc)
            seed_agent_signal_memory()
            run_cns_cycle(cycle_type='startup')
            try:
                run_chatgpt_bidirectional_sync(source='startup')
            except Exception as bridge_exc:
                logging.warning("Startup ChatGPT bridge sync skipped/failed: %s", bridge_exc)
            if ENABLE_STARTUP_AUDIT:
                try:
                    run_daily_autonomous_jobs(trigger='startup')
                except Exception as startup_exc:
                    record_cns_heartbeat(
                        'startup_audit',
                        'failed',
                        '開機自動巡檢失敗',
                        {'error': str(startup_exc)},
                    )
                    logging.error("Startup audit failed: %s", startup_exc)
        CNS_RUNTIME["startup_bootstrap_status"] = "completed"
    except Exception as startup_exc:
        CNS_RUNTIME["startup_bootstrap_status"] = "failed"
        logging.exception("Startup bootstrap failed: %s", startup_exc)
    finally:
        CNS_RUNTIME["startup_bootstrap_completed"] = True
        if ENABLE_PROACTIVE_CNS and not CNS_RUNTIME["thread_started"]:
            start_cns_background_worker()


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_startup_bootstrap_lock() -> bool:
    """
    Ensure bootstrap/background worker starts only once under multi-process SMP.
    Uses a simple lock file with stale-PID recovery.
    """
    if not STARTUP_LEADER_ONLY:
        return True

    lock_path = STARTUP_BOOTSTRAP_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            existing = int(lock_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing = 0
        if existing and _pid_is_running(existing):
            return False
        # stale lock
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            return False

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def start_startup_bootstrap_worker():
    if not STARTUP_BOOTSTRAP_ENABLED:
        CNS_RUNTIME["startup_bootstrap_completed"] = True
        CNS_RUNTIME["startup_bootstrap_status"] = "disabled"
        if ENABLE_PROACTIVE_CNS and not CNS_RUNTIME["thread_started"]:
            start_cns_background_worker()
        return
    if CNS_RUNTIME["startup_bootstrap_started"]:
        return
    if not _acquire_startup_bootstrap_lock():
        CNS_RUNTIME["startup_bootstrap_completed"] = True
        CNS_RUNTIME["startup_bootstrap_status"] = "skipped_non_leader"
        return

    worker = threading.Thread(target=run_startup_bootstrap, name='startup-bootstrap-worker', daemon=True)
    worker.start()
    CNS_RUNTIME["startup_bootstrap_started"] = True


def autonomous_learning():
    """自主學習功能：與遠端AI聊天來獲取新知識"""
    if not TOGETHER_API_KEY:
        logging.warning("沒有Together AI API密鑰，無法進行自主學習")
        refresh_signal_memory_from_recent_activity(limit=20)
        record_cns_heartbeat('learner', 'completed', '學習器已改為本地訊號學習模式', {'mode': 'local_signal_learning'})
        return "未配置 Together API，已改以本地訊號詞與歷史任務進行學習"

    learning_url = "https://raw.githubusercontent.com/ollama/ollama/main/README.md"
    try:
        response = requests.get(learning_url, timeout=10)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        content = response.text
        
        # Summarize the content
        summary_prompt = f"請總結以下關於Ollama的內容：\n\n{content}"
        summary = query_together(summary_prompt)
        
        # Log the learning
        learning_summary = f"自主學習摘要：\n{summary}"
        logging.info(learning_summary)
        learn_agent_signals('learner', [content[:1500], summary], source='remote_learning', message='ollama_readme')
        record_cns_heartbeat('learner', 'completed', '學習器已完成遠端知識摘要', {'summary_preview': summary[:300]})
        
        # Optionally, save the summary to the database or a file
        # For now, we just log it.
        
        return "已成功學習Ollama的最新資訊！"

    except requests.exceptions.RequestException as e:
        logging.error(f"自主學習失敗，無法獲取內容: {e}")
        record_cns_heartbeat('learner', 'failed', '遠端學習抓取失敗', {'error': str(e)})
        return f"自主學習失敗，無法獲取內容: {e}"
    except Exception as e:
        logging.error(f"自主學習失敗，處理內容時出錯: {e}")
        record_cns_heartbeat('learner', 'failed', '遠端學習處理失敗', {'error': str(e)})
        return f"自主學習失敗，處理內容時出錯: {e}"
@app.route('/')
@app.route('/Perob')
@app.route('/Perob/')
def index():
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
@limiter.limit("10 per minute")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '')
    runtime_ctx = build_runtime_task_context(data)
    route_message = user_message
    if runtime_ctx.get('context_text'):
        route_message = f"{user_message}\n\n[系統上下文] {runtime_ctx['context_text']}"

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    if is_bridge_summon_command(user_message):
        full_sync_mode = is_bridge_full_sync_command(user_message)
        if full_sync_mode:
            bridge_result = run_chatgpt_bidirectional_full_sync(
                source=f"summon_full:{CHATGPT_BRIDGE_SUMMON_COMMAND}",
                force=True,
            )
        else:
            bridge_result = run_chatgpt_bidirectional_sync(
                source=f"summon:{CHATGPT_BRIDGE_SUMMON_COMMAND}",
                force=True,
            )
        summon_response = (
            f"已收到召喚指令「{CHATGPT_BRIDGE_SUMMON_COMMAND}」，"
            f"雙向學習狀態：{bridge_result.get('status', 'unknown')}。"
        )
        if full_sync_mode:
            summon_response += "\n模式：全量同步（sync-all）"
        if bridge_result.get("reason"):
            summon_response += f"\n原因：{bridge_result.get('reason')}"
        if bridge_result.get("error"):
            summon_response += f"\n錯誤：{bridge_result.get('error')}"
        if bridge_result.get("preview"):
            summon_response += f"\n摘要：{bridge_result.get('preview')}"
        if bridge_result.get("rows_synced") is not None:
            summon_response += (
                f"\n同步筆數：{bridge_result.get('rows_synced')}"
                f"（批次 {bridge_result.get('batches_processed')}/{bridge_result.get('batches_total_available')}）"
            )

        signal_tags = infer_signal_tags(user_message, "chatgpt_bridge", "summon")
        chat_entry = ChatHistory(
            user_message=sanitize_for_storage(user_message, max_length=CHAT_STORAGE_USER_MAX_CHARS),
            ai_response=sanitize_for_storage(summon_response, max_length=CHAT_STORAGE_AI_MAX_CHARS),
            agent_type='learner',
            model_used='chatgpt_bridge',
            signal_tags=json.dumps(signal_tags, ensure_ascii=False),
            routing_reason=json.dumps({'reason': 'chatgpt_bridge_summon', 'bridge': bridge_result}, ensure_ascii=False),
        )
        db.session.add(chat_entry)
        db.session.commit()
        return jsonify({
            'response': summon_response,
            'model': 'ChatGPT Bridge',
            'agent': 'learner',
            'signal_tags': signal_tags,
            'bridge': bridge_result,
            'summon_command': CHATGPT_BRIDGE_SUMMON_COMMAND,
        })

    if ASK_BACK_MODE and should_ask_back(user_message):
        ask_back_response = build_ask_back_question(user_message)
        signal_tags = infer_signal_tags(user_message, 'ask_back')
        chat_entry = ChatHistory(
            user_message=sanitize_for_storage(user_message, max_length=CHAT_STORAGE_USER_MAX_CHARS),
            ai_response=sanitize_for_storage(ask_back_response, max_length=CHAT_STORAGE_AI_MAX_CHARS),
            agent_type='dispatcher',
            model_used='ask_back',
            signal_tags=json.dumps(signal_tags, ensure_ascii=False),
            routing_reason=json.dumps({'reason': 'ask_back_mode'}, ensure_ascii=False),
        )
        db.session.add(chat_entry)
        db.session.commit()
        learn_agent_signals('dispatcher', [user_message, ask_back_response], source='ask_back_mode', message=user_message)
        trigger_autonomous_learning_async(source='chat_learning')
        return jsonify({
            'response': ask_back_response,
            'model': 'ask_back',
            'agent': 'dispatcher',
            'ask_back': True,
            'requires_user_clarification': True,
            'signal_tags': signal_tags,
            'routing': {'reason': 'ask_back_mode'},
        })

    # 1. 由總管分派任務
    dispatch_result = dispatch_task(route_message)
    agent_type = _fuse_agent_key(dispatch_result['agent']) or dispatch_result['agent']
    dispatch_result['agent'] = agent_type
    signal_tags = dispatch_result.get('signal_tags', infer_signal_tags(route_message))
    routing_reason = json.dumps(dispatch_result, ensure_ascii=False)
    emit_chat_lifecycle_event(
        "chat.dispatched",
        {
            "message": _bridge_string(user_message, 1200),
            "agent": agent_type,
            "routing": dispatch_result,
            "runtime_context": runtime_ctx,
        },
    )

    # 記錄到資料庫
    chat_entry = ChatHistory(
        user_message=sanitize_for_storage(user_message, max_length=CHAT_STORAGE_USER_MAX_CHARS),
        ai_response=sanitize_for_storage("Processing...", max_length=CHAT_STORAGE_AI_MAX_CHARS),
        agent_type=agent_type,
        model_used="routing",
        signal_tags=json.dumps(signal_tags, ensure_ascii=False),
        routing_reason=routing_reason,
    )
    db.session.add(chat_entry)
    db.session.commit()

    try:
        start_time = time.time()
        selected_model = select_direct_communication_model_choice(data.get('model', 'auto'))
        emit_notification(
            'engineer',
            '對話請求進入',
            f"使用者訊息已進入流程，分派給 {agent_type}",
            level='info',
            category='chat',
            details={'agent_type': agent_type, 'signal_tags': signal_tags},
        )
        
        # 2. 根據分派結果，執行對應的智能體
        if agent_type == 'xiaobian':
            task_data = {
                'title': '即時任務（小編）',
                'description': user_message,
                'assigned_agent': 'xiaobian',
                'model_hint': selected_model,
                'interaction_mode': runtime_ctx.get('interaction_mode', ''),
                'creative_submode': runtime_ctx.get('creative_submode', ''),
                'video_workflow_engine': runtime_ctx.get('video_workflow_engine', ''),
                'constraints': runtime_ctx.get('context_text', ''),
            }
            task_data['domain'] = infer_task_domain(task_data)
            ai_response, model_used = xiaobian_generate(task_data)
        elif agent_type != 'general' and get_agent_spec(agent_type):
            ai_response, model_used = execute_task_for_agent(
                agent_type,
                user_message,
                task_data={
                    'title': f'{agent_type} 即時任務',
                    'description': user_message,
                    'assigned_agent': agent_type,
                    'model_hint': selected_model,
                    'interaction_mode': runtime_ctx.get('interaction_mode', ''),
                    'creative_submode': runtime_ctx.get('creative_submode', ''),
                    'video_workflow_engine': runtime_ctx.get('video_workflow_engine', ''),
                    'constraints': runtime_ctx.get('context_text', ''),
                },
            )
        else: # 'general'
            ai_response, model_used = handle_general_chat(user_message, selected_model)

        ai_response, safety_guard = guard_black_gray_response(
            user_message=user_message,
            ai_response=ai_response,
            model_choice=selected_model,
            agent_key=agent_type,
            model_used=model_used,
        )
        if safety_guard.get('triggered'):
            emit_notification(
                _fused_safety_agent_key(),
                '內容安全攔截',
                f"已攔截疑似黑灰產導向內容，來源 agent={agent_type}",
                level='warning',
                category='safety',
                details={
                    'agent': agent_type,
                    'model_used': model_used,
                    'matched_terms': safety_guard.get('matched_terms', []),
                    'promotion_terms': safety_guard.get('promotion_terms', []),
                    'regenerated': bool(safety_guard.get('regenerated')),
                    'fallback_used': bool(safety_guard.get('fallback_used')),
                    'regen_attempts': int(safety_guard.get('regen_attempts', 0)),
                },
            )

        response_time = time.time() - start_time
        zzz_obfuscation_applied = model_used.startswith('Zhizengzeng/智增增') and ZZZ_OBFUSCATE_RESPONSE
        deliver_response = obfuscate_transport_text(ai_response) if zzz_obfuscation_applied else ai_response

        logging.info(f"Response generated in {response_time:.2f}s using {model_used} (Agent: {agent_type})")
        signal_texts = [user_message, ai_response]
        signal_message = user_message
        if zzz_obfuscation_applied:
            signal_texts = [agent_type, 'zzz_response_obfuscated', routing_reason]
            signal_message = 'zzz_response_obfuscated'
        if PRIVACY_MODE:
            signal_texts = [agent_type, "privacy_mode_enabled", routing_reason]
            signal_message = "privacy_mode_enabled"
        learn_agent_signals(agent_type, signal_texts, source='chat_runtime', message=signal_message)
        emit_notification(
            agent_type,
            f'{agent_type} 回覆完成',
            f"模型 {model_used}，耗時 {response_time:.2f}s",
            level='info',
            category='chat',
            details={
                'model_used': model_used,
                'response_time': response_time,
                'response_obfuscated': zzz_obfuscation_applied,
            },
        )

        # 更新資料庫
        chat_entry.ai_response = sanitize_for_storage(deliver_response, max_length=CHAT_STORAGE_AI_MAX_CHARS)
        chat_entry.model_used = model_used
        chat_entry.signal_tags = json.dumps(signal_tags, ensure_ascii=False)
        db.session.commit()
        create_conversation_feed_task(
            user_message=user_message,
            ai_response=deliver_response,
            agent_key=agent_type,
            model_used=model_used,
            routing=dispatch_result,
            source_channel="chat",
        )
        emit_chat_lifecycle_event(
            "chat.completed",
            {
                "chat_id": chat_entry.id,
                "agent": agent_type,
                "model_used": model_used,
                "response_time": response_time,
                "routing": dispatch_result,
            },
        )
        trigger_autonomous_learning_async(source='chat_learning')

        return jsonify({
            'response': deliver_response,
            'model': model_used,
            'agent': agent_type,
            'response_time': response_time,
            'signal_tags': signal_tags,
            'routing': dispatch_result,
            'response_obfuscated': zzz_obfuscation_applied,
            'security_protocol': 'zzz-obf-v1' if zzz_obfuscation_applied else 'plain',
            'safety_guard': {
                'triggered': bool(safety_guard.get('triggered')),
                'regenerated': bool(safety_guard.get('regenerated')),
                'fallback_used': bool(safety_guard.get('fallback_used')),
            },
        })

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logging.error(f"Chat error: {error_msg}")
        emit_notification(
            'engineer',
            '對話流程異常',
            error_msg[:500],
            level='error',
            category='chat',
        )
        chat_entry.ai_response = error_msg
        db.session.commit()
        emit_chat_lifecycle_event(
            "chat.failed",
            {
                "chat_id": chat_entry.id,
                "agent": agent_type,
                "error": error_msg,
            },
        )
        return jsonify({'error': error_msg}), 500

@app.route('/chat/agent', methods=['POST'])
@app.route('/chat/agent/', methods=['POST'])
@app.route('/Perob/chat/agent', methods=['POST'])
@app.route('/Perob/chat/agent/', methods=['POST'])
@app.route('/api/send_message', methods=['POST'])
@app.route('/api/send_message/', methods=['POST'])
@app.route('/Perob/api/send_message', methods=['POST'])
@app.route('/Perob/api/send_message/', methods=['POST'])
@limiter.limit("20 per minute")
def chat_direct_agent():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get('message', '') or '').strip()
    target_agent = _fuse_agent_key(str(data.get('agent', 'general') or 'general').strip().lower()) or 'general'
    selected_model = select_direct_communication_model_choice(data.get('model', 'auto'))
    runtime_ctx = build_runtime_task_context(data)

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    valid_agents = {_fuse_agent_key(spec.key) or spec.key for spec in list_agent_specs()}
    if target_agent not in valid_agents:
        return jsonify({'error': f'Unknown agent: {target_agent}'}), 400

    start_time = time.time()
    signal_tags = infer_signal_tags(user_message, target_agent, 'direct_agent')
    routing_reason = {
        'reason': 'direct_agent_chat',
        'target_agent': target_agent,
        'selected_model': selected_model,
    }

    try:
        if target_agent == 'xiaobian':
            task_data = {
                'title': '智能體直連對話',
                'description': user_message,
                'assigned_agent': 'xiaobian',
                'model_hint': selected_model,
                'interaction_mode': runtime_ctx.get('interaction_mode', ''),
                'creative_submode': runtime_ctx.get('creative_submode', ''),
                'video_workflow_engine': runtime_ctx.get('video_workflow_engine', ''),
                'constraints': runtime_ctx.get('context_text', ''),
            }
            task_data['domain'] = infer_task_domain(task_data)
            ai_response, model_used = xiaobian_generate(task_data)
        elif target_agent != 'general' and get_agent_spec(target_agent):
            ai_response, model_used = execute_task_for_agent(
                target_agent,
                user_message,
                task_data={
                    'title': f'{target_agent} 直連對話',
                    'description': user_message,
                    'assigned_agent': target_agent,
                    'model_hint': selected_model,
                    'interaction_mode': runtime_ctx.get('interaction_mode', ''),
                    'creative_submode': runtime_ctx.get('creative_submode', ''),
                    'video_workflow_engine': runtime_ctx.get('video_workflow_engine', ''),
                    'constraints': runtime_ctx.get('context_text', ''),
                },
            )
        else:
            ai_response, model_used = handle_general_chat(user_message, selected_model)

        ai_response, safety_guard = guard_black_gray_response(
            user_message=user_message,
            ai_response=ai_response,
            model_choice=selected_model,
            agent_key=target_agent,
            model_used=model_used,
        )
        zzz_obfuscation_applied = model_used.startswith('Zhizengzeng/智增增') and ZZZ_OBFUSCATE_RESPONSE
        deliver_response = obfuscate_transport_text(ai_response) if zzz_obfuscation_applied else ai_response

        signal_texts = [user_message, ai_response]
        signal_message = user_message
        if zzz_obfuscation_applied:
            signal_texts = [target_agent, 'zzz_response_obfuscated', json.dumps(routing_reason, ensure_ascii=False)]
            signal_message = 'zzz_response_obfuscated'
        if PRIVACY_MODE:
            signal_texts = [target_agent, "privacy_mode_enabled", json.dumps(routing_reason, ensure_ascii=False)]
            signal_message = "privacy_mode_enabled"
        learn_agent_signals(target_agent, signal_texts, source='chat_direct_agent', message=signal_message)

        chat_entry = ChatHistory(
            user_message=sanitize_for_storage(user_message, max_length=CHAT_STORAGE_USER_MAX_CHARS),
            ai_response=sanitize_for_storage(deliver_response, max_length=CHAT_STORAGE_AI_MAX_CHARS),
            agent_type=target_agent,
            model_used=model_used,
            signal_tags=json.dumps(signal_tags, ensure_ascii=False),
            routing_reason=json.dumps(routing_reason, ensure_ascii=False),
        )
        db.session.add(chat_entry)
        db.session.commit()
        create_conversation_feed_task(
            user_message=user_message,
            ai_response=deliver_response,
            agent_key=target_agent,
            model_used=model_used,
            routing=routing_reason,
            source_channel="chat_direct_agent",
        )
        emit_chat_lifecycle_event(
            "chat.direct.completed",
            {
                "chat_id": chat_entry.id,
                "agent": target_agent,
                "model_used": model_used,
                "response_time": round(time.time() - start_time, 3),
            },
        )
        trigger_autonomous_learning_async(source='chat_direct_agent')

        response_time = round(time.time() - start_time, 3)
        return jsonify({
            'response': deliver_response,
            'model': model_used,
            'agent': target_agent,
            'response_time': response_time,
            'signal_tags': signal_tags,
            'direct': True,
            'response_obfuscated': zzz_obfuscation_applied,
            'safety_guard': {
                'triggered': bool(safety_guard.get('triggered')),
                'regenerated': bool(safety_guard.get('regenerated')),
                'fallback_used': bool(safety_guard.get('fallback_used')),
            },
        })
    except Exception as exc:
        logging.error("Direct agent chat error (%s): %s", target_agent, exc)
        return jsonify({'error': str(exc), 'agent': target_agent, 'direct': True}), 500


@app.route('/history')
@limiter.exempt
def history():
    agent = str(request.args.get('agent', '') or '').strip().lower()
    if agent == 'learner':
        agent = 'researcher'
    try:
        limit = int(request.args.get('limit', 120))
    except (TypeError, ValueError):
        limit = 120
    limit = max(1, min(limit, 10000))

    query = ChatHistory.query
    if agent:
        query = query.filter_by(agent_type=agent)
        chats = query.order_by(ChatHistory.timestamp.asc()).limit(limit).all()
    else:
        chats = query.order_by(ChatHistory.timestamp.desc()).limit(limit).all()

    return jsonify([{
        'user': chat.user_message,
        'ai': chat.ai_response,
        'agent': _fuse_agent_key(chat.agent_type) or chat.agent_type,
        'model': chat.model_used,
        'signal_tags': _parse_json_text(chat.signal_tags, []),
        'time': chat.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    } for chat in chats])

@app.route('/learn', methods=['POST'])
@limiter.limit("1 per hour")  # 限制學習頻率
def learn():
    """觸發自主學習"""
    try:
        result = autonomous_learning()
        cycle_summary = run_cns_cycle(cycle_type='manual_learning')
        return jsonify({
            'message': result,
            'dispatcher_learning': get_data_framework_summary()['dispatcher'],
            'cns_cycle': cycle_summary,
        })
    except Exception as e:
        logging.error(f"學習錯誤: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/system/data-framework', methods=['GET'])
def data_framework():
    """Inspect current storage paths, DB counts, and learned dispatcher rules."""
    return jsonify(get_data_framework_summary())


@app.route('/system/data-framework/merge-legacy', methods=['POST'])
@require_server_api_token
@limiter.limit("6 per hour")
def merge_legacy_data_framework():
    payload = request.get_json(silent=True) or {}
    source_paths = payload.get('source_paths') if isinstance(payload.get('source_paths'), list) else []
    dry_run = bool(payload.get('dry_run', False))
    max_rows_per_table = int(payload.get('max_rows_per_table', 10000))
    report = merge_legacy_data_into_current(
        source_paths=source_paths,
        dry_run=dry_run,
        max_rows_per_table=max_rows_per_table,
    )
    return jsonify(report)


@app.route('/system/runtime-strategy', methods=['GET'])
def runtime_strategy():
    execution_choice = select_execution_model_choice()
    zzz_guard = get_zzz_runtime_guard()
    proclaimer_detection = get_proclaimer_detection_status()
    whitehat_detection = get_whitehat_detection_status()
    server_api_auth = get_server_api_auth_status()
    return jsonify({
        'cloud_preferred': PREFER_CLOUD_MODELS,
        'allow_local_model_fallback': ALLOW_LOCAL_MODEL_FALLBACK,
        'execution_provider': EXECUTION_PROVIDER,
        'execution_model_selected': execution_choice,
        'chat_preferred_provider': CHAT_PREFERRED_PROVIDER,
        'privacy_mode': PRIVACY_MODE,
        'learning_mode': LEARNING_MODE,
        'ask_back_mode': ASK_BACK_MODE,
        'server_api_auth': server_api_auth,
        'fail_closed': {
            'key_fail_closed': KEY_FAIL_CLOSED,
            'require_encrypted_keys': REQUIRE_ENCRYPTED_KEYS,
            'gemini_require_encrypted_key': GEMINI_REQUIRE_ENCRYPTED_KEY,
            'nvidia_require_encrypted_key': NVIDIA_REQUIRE_ENCRYPTED_KEY,
            'zzz_require_encrypted_key': ZZZ_REQUIRE_ENCRYPTED_KEY,
            'zzz_fail_closed': ZZZ_FAIL_CLOSED,
        },
        'key_resolution_audit': {
            'gemini': KEY_RESOLUTION_AUDIT.get('GEMINI_API_KEY', {}),
            'nvidia': KEY_RESOLUTION_AUDIT.get('NVIDIA_API_KEY', {}),
            'zzz': KEY_RESOLUTION_AUDIT.get('ZZZ_API_KEY', {}),
        },
        'zzz_runtime_guard': zzz_guard,
        'proclaimer_detection': proclaimer_detection,
        'whitehat_detection': whitehat_detection,
        'chatgpt_bridge': {
            'enabled': CHATGPT_BRIDGE_ENABLED,
            'model': CHATGPT_BRIDGE_MODEL,
            'summon_command': CHATGPT_BRIDGE_SUMMON_COMMAND,
            'min_interval_seconds': CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS,
            'last_status': CNS_RUNTIME.get('chatgpt_bridge_last_status'),
            'last_at': CNS_RUNTIME.get('chatgpt_bridge_last_at'),
            'last_message': CNS_RUNTIME.get('chatgpt_bridge_last_message'),
            'full_sync_enabled': CHATGPT_BRIDGE_FULL_SYNC_ENABLED,
            'full_sync_batch_size': CHATGPT_BRIDGE_FULL_SYNC_BATCH_SIZE,
            'full_sync_max_batches': CHATGPT_BRIDGE_FULL_SYNC_MAX_BATCHES,
            'full_sync_field_max_chars': CHATGPT_BRIDGE_FULL_SYNC_FIELD_MAX_CHARS,
            'full_sync_retry': CHATGPT_BRIDGE_FULL_SYNC_RETRY,
            'full_sync_retry_backoff_seconds': CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS,
            'full_sync_api_timeout_seconds': CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS,
            'full_sync_hard_timeout_seconds': CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS,
            'full_sync_async_default': CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT,
            'full_sync_active_jobs': _count_active_full_sync_jobs(),
            'full_sync_last_status': CNS_RUNTIME.get('chatgpt_bridge_full_last_status'),
            'full_sync_last_at': CNS_RUNTIME.get('chatgpt_bridge_full_last_at'),
            'full_sync_last_message': CNS_RUNTIME.get('chatgpt_bridge_full_last_message'),
            'ingest_enabled': CHATGPT_BRIDGE_INGEST_ENABLED,
            'ingest_require_token': CHATGPT_BRIDGE_INGEST_REQUIRE_TOKEN,
            'ingest_max_items': CHATGPT_BRIDGE_INGEST_MAX_ITEMS,
            'ingest_last_status': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_status'),
            'ingest_last_at': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_at'),
            'ingest_last_message': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_message'),
        },
        'rate_limit_storage': {
            'configured': app.config.get('RATELIMIT_STORAGE_URI_CONFIGURED', ''),
            'effective': app.config.get('RATELIMIT_STORAGE_URI', ''),
        },
    })


@app.route('/system/server-api-auth-status', methods=['GET'])
def server_api_auth_status():
    return jsonify(get_server_api_auth_status())


@app.route('/system/proclaimer-detection-status', methods=['GET'])
def proclaimer_detection_status():
    window_hours = request.args.get('window_hours', default=24, type=int) or 24
    return jsonify(get_proclaimer_detection_status(window_hours=window_hours))


@app.route('/system/whitehat-detection-status', methods=['GET'])
def whitehat_detection_status():
    window_hours = request.args.get('window_hours', default=24, type=int) or 24
    return jsonify(get_whitehat_detection_status(window_hours=window_hours))


@app.route('/system/chatgpt-bridge/status', methods=['GET'])
def chatgpt_bridge_status():
    full_sync_history_count = CNSHeartbeat.query.filter_by(cycle_type='chatgpt_bridge_full_sync').count()
    ingest_history_count = CNSHeartbeat.query.filter_by(cycle_type='chatgpt_bridge_ingest').count()
    return jsonify({
        'enabled': CHATGPT_BRIDGE_ENABLED,
        'openai_configured': OPENAI_ENABLED,
        'model': CHATGPT_BRIDGE_MODEL,
        'summon_command': CHATGPT_BRIDGE_SUMMON_COMMAND,
        'min_interval_seconds': CHATGPT_BRIDGE_MIN_INTERVAL_SECONDS,
        'max_items': CHATGPT_BRIDGE_MAX_ITEMS,
        'last_status': CNS_RUNTIME.get('chatgpt_bridge_last_status'),
        'last_at': CNS_RUNTIME.get('chatgpt_bridge_last_at'),
        'last_message': CNS_RUNTIME.get('chatgpt_bridge_last_message'),
        'full_sync_enabled': CHATGPT_BRIDGE_FULL_SYNC_ENABLED,
        'full_sync_batch_size': CHATGPT_BRIDGE_FULL_SYNC_BATCH_SIZE,
        'full_sync_max_batches': CHATGPT_BRIDGE_FULL_SYNC_MAX_BATCHES,
        'full_sync_field_max_chars': CHATGPT_BRIDGE_FULL_SYNC_FIELD_MAX_CHARS,
        'full_sync_retry': CHATGPT_BRIDGE_FULL_SYNC_RETRY,
        'full_sync_retry_backoff_seconds': CHATGPT_BRIDGE_FULL_SYNC_RETRY_BACKOFF_SECONDS,
        'full_sync_api_timeout_seconds': CHATGPT_BRIDGE_FULL_SYNC_API_TIMEOUT_SECONDS,
        'full_sync_hard_timeout_seconds': CHATGPT_BRIDGE_FULL_SYNC_HARD_TIMEOUT_SECONDS,
        'full_sync_async_default': CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT,
        'full_sync_active_jobs': _count_active_full_sync_jobs(),
        'full_sync_last_status': CNS_RUNTIME.get('chatgpt_bridge_full_last_status'),
        'full_sync_last_at': CNS_RUNTIME.get('chatgpt_bridge_full_last_at'),
        'full_sync_last_message': CNS_RUNTIME.get('chatgpt_bridge_full_last_message'),
        'ingest_enabled': CHATGPT_BRIDGE_INGEST_ENABLED,
        'ingest_require_token': CHATGPT_BRIDGE_INGEST_REQUIRE_TOKEN,
        'ingest_max_items': CHATGPT_BRIDGE_INGEST_MAX_ITEMS,
        'ingest_last_status': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_status'),
        'ingest_last_at': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_at'),
        'ingest_last_message': CNS_RUNTIME.get('chatgpt_bridge_ingest_last_message'),
        'full_sync_history_count': full_sync_history_count,
        'ingest_history_count': ingest_history_count,
    })


@app.route('/system/chatgpt-bridge/run', methods=['POST'])
@require_server_api_token
@limiter.limit("12 per hour")
def chatgpt_bridge_run():
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get('force', False))
    source = str(payload.get('source', 'manual')).strip() or 'manual'
    result = run_chatgpt_bidirectional_sync(source=source, force=force)
    return jsonify(result)


@app.route('/system/chatgpt-bridge/full-sync-history', methods=['GET'])
def chatgpt_bridge_full_sync_history():
    limit = request.args.get('limit', default=20, type=int) or 20
    limit = max(1, min(limit, 200))
    rows = CNSHeartbeat.query.filter_by(cycle_type='chatgpt_bridge_full_sync').order_by(CNSHeartbeat.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        details = _parse_json_text(row.details, {})
        items.append({
            'id': row.id,
            'status': row.status,
            'summary': row.summary,
            'created_at': _bridge_iso(row.created_at),
            'rows_synced': details.get('rows_synced'),
            'batches_processed': details.get('batches_processed'),
            'batches_failed': details.get('batches_failed'),
            'source': details.get('source'),
        })
    return jsonify({'count': len(items), 'items': items})


@app.route('/system/sync-request-history', methods=['GET'])
@require_server_api_token
def sync_request_history():
    limit = request.args.get('limit', default=20, type=int) or 20
    limit = max(1, min(limit, 200))
    rows = CNSHeartbeat.query.filter_by(cycle_type='external_sync_request').order_by(CNSHeartbeat.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        details = _parse_json_text(row.details, {})
        items.append({
            'id': row.id,
            'status': row.status,
            'summary': row.summary,
            'created_at': _bridge_iso(row.created_at),
            'sync_mode': details.get('sync_mode'),
            'result_status': details.get('result_status'),
            'rows_synced': details.get('rows_synced'),
            'batches_failed': details.get('batches_failed'),
            'client_ip': details.get('request_trace', {}).get('client_ip'),
            'auth_header_present': details.get('request_trace', {}).get('auth_header_present'),
            'source': details.get('source'),
        })
    return jsonify({'count': len(items), 'items': items})


@app.route('/sync/full-sync/jobs', methods=['GET'])
@require_server_api_token
def full_sync_jobs():
    limit = request.args.get('limit', default=20, type=int) or 20
    jobs = _list_full_sync_jobs(limit=limit)
    return jsonify({
        'count': len(jobs),
        'active_count': _count_active_full_sync_jobs(),
        'items': jobs,
    })


@app.route('/sync/full-sync/jobs/<job_id>', methods=['GET'])
@require_server_api_token
def full_sync_job_detail(job_id: str):
    job = _get_full_sync_job(job_id)
    if not job:
        return jsonify({'status': 'not_found', 'message': 'full sync job not found', 'job_id': job_id}), 404
    return jsonify(job)


@app.route('/system/chatgpt-bridge/sync-all', methods=['POST'])
@require_server_api_token
@limiter.limit("6 per hour")
def chatgpt_bridge_sync_all():
    payload = request.get_json(silent=True) or {}
    source = str(payload.get('source', 'manual_full_sync')).strip() or 'manual_full_sync'
    result = run_full_sync_with_recovery(
        payload=payload,
        source=source,
    )
    status = str(result.get('status') or '').lower()
    if status == 'timeout':
        return jsonify(result), 504
    if status in {'failed'}:
        return jsonify(result), 500
    if status == 'disabled':
        return jsonify(result), 503
    if status == 'skipped':
        return jsonify(result), 400
    return jsonify(result), (207 if status == 'partial_failed' else 200)


@app.route('/system/chatgpt-bridge/ingest', methods=['POST'])
@require_server_api_token
@limiter.limit("60 per hour")
def chatgpt_bridge_ingest():
    payload = request.get_json(silent=True) or {}
    source = str(payload.get('source', 'chatgpt_manual_ingest')).strip() or 'chatgpt_manual_ingest'

    if CHATGPT_BRIDGE_INGEST_REQUIRE_TOKEN:
        expected = str(CHATGPT_BRIDGE_INGEST_TOKEN or '').strip()
        if not expected:
            return jsonify({
                'status': 'failed',
                'reason': 'ingest_token_not_configured',
                'message': 'CHATGPT_BRIDGE_INGEST_TOKEN 未設定，系統採 fail-closed 拒絕回寫',
            }), 503

        provided = (
            request.headers.get('X-Bridge-Token')
            or request.headers.get('X-ChatGPT-Bridge-Token')
            or payload.get('bridge_token')
            or payload.get('token')
            or ''
        )
        provided = str(provided).strip()
        if not provided or not hmac.compare_digest(provided, expected):
            return jsonify({
                'status': 'forbidden',
                'reason': 'invalid_ingest_token',
                'message': 'ingest token 驗證失敗',
            }), 403

    result = run_chatgpt_bridge_ingest(payload=payload, source=source)
    status = str(result.get('status') or '').lower()
    if status == 'failed':
        return jsonify(result), 500
    if status == 'disabled':
        return jsonify(result), 503
    if status == 'skipped':
        return jsonify(result), 400
    return jsonify(result)


@app.route('/sync', methods=['POST'])
@require_server_api_token
@limiter.limit("30 per hour")
def external_sync():
    payload = request.get_json(silent=True) or {}
    sync_type = str(payload.get('type', 'ingest')).strip().lower()
    request_trace = {
        'received_at': time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        'client_ip': _resolve_server_request_ip(),
        'auth_header_present': bool(str(request.headers.get('Authorization', '') or '').strip()),
        'x_server_token_present': bool(str(request.headers.get('X-Server-Token', '') or '').strip()),
        'x_api_token_present': bool(str(request.headers.get('X-API-Token', '') or '').strip()),
        'content_type': str(request.headers.get('Content-Type', '') or '').strip(),
        'sync_type': sync_type,
    }

    if sync_type in {'full_sync', 'sync_all', 'sync-all', 'full'}:
        source = str(payload.get('source', 'external_sync_full')).strip() or 'external_sync_full'
        async_mode = _coerce_bool(
            payload.get('async', payload.get('non_blocking', CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT)),
            CHATGPT_BRIDGE_FULL_SYNC_ASYNC_DEFAULT,
        )
        if async_mode:
            job = _new_full_sync_job(payload=payload, source=source, request_trace=request_trace)
            _store_full_sync_job(job)
            worker = threading.Thread(
                target=_run_full_sync_job_async,
                args=(job['id'],),
                name=f"full-sync-job-{job['id']}",
                daemon=True,
            )
            worker.start()
            record_cns_heartbeat(
                'external_sync_request',
                'queued',
                '/sync full_sync async accepted',
                {
                    'sync_mode': 'full_sync_async',
                    'result_status': 'queued',
                    'source': source,
                    'job_id': job['id'],
                    'request_trace': request_trace,
                },
            )
            return jsonify({
                'status': 'accepted',
                'mode': 'full_sync_async',
                'job_id': job['id'],
                'job': _get_full_sync_job(job['id']),
                'request_trace': request_trace,
                'progress_query': {
                    'list': '/sync/full-sync/jobs',
                    'detail': f"/sync/full-sync/jobs/{job['id']}",
                },
            }), 202

        response_mode = 'full_sync'
        result = run_full_sync_with_recovery(
            payload=payload,
            source=source,
        )
        status = str(result.get('status') or '').lower()
        http_status = 200
        if status == 'failed':
            http_status = 500
        elif status == 'disabled':
            http_status = 503
        elif status == 'skipped':
            http_status = 400
        elif status == 'timeout':
            http_status = 504
        elif status == 'partial_failed':
            http_status = 207

        agent_task = create_sync_agent_task(response_mode, payload, result)
        heartbeat_status = 'completed' if status == 'completed' else ('failed' if status in {'failed', 'disabled', 'timeout'} else status)
        record_cns_heartbeat(
            'external_sync_request',
            heartbeat_status,
            f"/sync {response_mode} request {status}",
            {
                'sync_mode': response_mode,
                'result_status': status,
                'rows_synced': result.get('rows_synced'),
                'batches_failed': result.get('batches_failed'),
                'source': result.get('source'),
                'request_trace': request_trace,
            },
        )
        envelope_status = 'synced' if status == 'completed' else status
        return jsonify({
            'status': envelope_status,
            'mode': response_mode,
            'result': result,
            'request_trace': request_trace,
            'agent_task': agent_task,
        }), http_status

    response_mode = 'ingest'
    result = {}
    http_status = 200
    if sync_type in {'bridge', 'light_sync', 'summary'}:
        response_mode = 'bridge'
        result = run_chatgpt_bidirectional_sync(
            source=str(payload.get('source', 'external_sync_bridge')).strip() or 'external_sync_bridge',
            force=True,
        )
    else:
        response_mode = 'ingest'
        result = run_chatgpt_bridge_ingest(
            payload=payload,
            source=str(payload.get('source', 'external_sync_ingest')).strip() or 'external_sync_ingest',
        )

    status = str(result.get('status') or '').lower()
    if status == 'failed':
        http_status = 500
    elif status == 'disabled':
        http_status = 503
    elif status == 'skipped':
        http_status = 400
    elif status == 'timeout':
        http_status = 504
    elif status == 'partial_failed':
        http_status = 207

    agent_task = create_sync_agent_task(response_mode, payload, result)
    heartbeat_status = 'completed' if status == 'completed' else ('failed' if status in {'failed', 'disabled', 'timeout'} else status)
    record_cns_heartbeat(
        'external_sync_request',
        heartbeat_status,
        f"/sync {response_mode} request {status}",
        {
            'sync_mode': response_mode,
            'result_status': status,
            'rows_synced': result.get('rows_synced'),
            'batches_failed': result.get('batches_failed'),
            'source': result.get('source'),
            'request_trace': request_trace,
        },
    )

    envelope_status = 'synced' if status == 'completed' else status
    return jsonify({
        'status': envelope_status,
        'mode': response_mode,
        'result': result,
        'request_trace': request_trace,
        'agent_task': agent_task,
    }), http_status


@app.route('/agents', methods=['GET'])
def agents_catalog():
    """List all agents, their capabilities, signal tags, and collaborators."""
    return jsonify(list_agent_overviews())


@app.route('/agent/signals', methods=['GET'])
def agent_signals():
    signals = AgentSignal.query.order_by(AgentSignal.hit_count.desc(), AgentSignal.updated_at.desc()).limit(200).all()
    return jsonify([serialize_agent_signal(signal) for signal in signals])


@app.route('/agent/notifications', methods=['GET'])
def agent_notifications():
    limit = request.args.get('limit', default=40, type=int) or 40
    since_id = request.args.get('since_id', default=0, type=int) or 0
    unread_only = str(request.args.get('unread_only', 'false')).lower() == 'true'
    limit = max(1, min(limit, 200))

    query = AgentNotification.query
    if since_id > 0:
        query = query.filter(AgentNotification.id > since_id)
    if unread_only:
        query = query.filter_by(is_read=False)

    notifications = query.order_by(AgentNotification.id.desc()).limit(limit).all()
    notifications.reverse()
    return jsonify([serialize_notification(item) for item in notifications])


@app.route('/agent/notifications/read', methods=['POST'])
@limiter.limit("60 per hour")
def mark_notifications_read():
    data = request.get_json(silent=True) or {}
    notification_ids = data.get('notification_ids') or []
    mark_all = bool(data.get('mark_all', False))

    updated = 0
    if mark_all:
        updated = AgentNotification.query.filter_by(is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify({'updated': updated, 'mark_all': True})

    if not isinstance(notification_ids, list):
        return jsonify({'error': 'notification_ids 必須是陣列'}), 400

    numeric_ids = [int(item) for item in notification_ids if str(item).isdigit()]
    if not numeric_ids:
        return jsonify({'updated': 0, 'mark_all': False})

    updated = AgentNotification.query.filter(AgentNotification.id.in_(numeric_ids)).update(
        {'is_read': True},
        synchronize_session=False,
    )
    db.session.commit()
    return jsonify({'updated': updated, 'mark_all': False})


@app.route('/system/cns/status', methods=['GET'])
def cns_status():
    latest_heartbeats = (
        CNSHeartbeat.query.order_by(CNSHeartbeat.created_at.desc()).limit(10).all()
        if CNS_HEARTBEAT_ENABLED
        else []
    )
    latest_tasks = AgentTask.query.order_by(AgentTask.updated_at.desc()).limit(12).all()
    latest_task_notifications = (
        AgentNotification.query
        .filter(AgentNotification.category.in_(['task', 'sync']))
        .order_by(AgentNotification.id.desc())
        .limit(12)
        .all()
    )
    latest_task_notifications.reverse()
    return jsonify({
        'runtime': CNS_RUNTIME,
        'interval_seconds': PROACTIVE_INTERVAL_SECONDS,
        'enabled': ENABLE_PROACTIVE_CNS,
        'heartbeat_enabled': CNS_HEARTBEAT_ENABLED,
        'recent_heartbeats': [serialize_heartbeat(heartbeat) for heartbeat in latest_heartbeats],
        'recent_tasks': [serialize_task_progress(task) for task in latest_tasks],
        'recent_task_notifications': [serialize_notification(item) for item in latest_task_notifications],
    })


@app.route('/api/orchestrator/status', methods=['GET'])
@limiter.exempt
def orchestrator_status_compat():
    """Compatibility endpoint for the frontend KAL/orchestrator monitor."""
    pending_count = AgentTask.query.filter(AgentTask.status.in_(['pending', 'running'])).count()
    cycle_count = CNSHeartbeat.query.count() if CNS_HEARTBEAT_ENABLED else 0
    brave_key = (os.getenv("BRAVE_API_KEY", "") or "").strip()

    return jsonify({
        'running': bool(ENABLE_PROACTIVE_CNS and CNS_RUNTIME.get('thread_started')),
        'pending_goals': pending_count,
        'cycle_count': cycle_count,
        'last_cycle_at': CNS_RUNTIME.get('last_cycle_at', ''),
        'last_cycle_summary': CNS_RUNTIME.get('last_cycle_summary', ''),
        'kal_loop': {
            'distiller_active': bool(LEARNING_MODE),
            'validator_active': bool(ASK_BACK_MODE),
            'brave_api': bool(brave_key),
            'max_rounds_per_goal': max(1, int(SYNC_AUTO_RECOVER_MAX_ROUNDS or 0)),
        },
        'runtime': CNS_RUNTIME,
    })


@app.route('/trace/learning-status', methods=['GET'])
@limiter.exempt
def learning_status_compat():
    """Compatibility endpoint for the frontend learning/trace panel."""
    pending_tasks = (
        AgentTask.query
        .filter(AgentTask.status.in_(['pending', 'running']))
        .order_by(AgentTask.updated_at.desc())
        .limit(5)
        .all()
    )
    recent_notifications = (
        AgentNotification.query
        .filter(AgentNotification.category.in_(['learning', 'task', 'sync']))
        .order_by(AgentNotification.id.desc())
        .limit(6)
        .all()
    )

    pending_items = [{
        'id': f"task-{task.id}",
        'query': task.title or task.description or f"Task #{task.id}",
        'type': task.status or 'pending',
        'priority': 1 if str(task.status or '') == 'running' else 0,
    } for task in pending_tasks]

    recent_logs = [{
        'task': notification.title or notification.message or f"通知 #{notification.id}",
        'type': notification.category or notification.level or 'runtime',
        'timestamp': notification.created_at.isoformat() if notification.created_at else '',
    } for notification in recent_notifications]

    return jsonify({
        'pending_items': pending_items,
        'recent_logs': recent_logs,
        'learning_mode': bool(LEARNING_MODE),
        'ask_back_mode': bool(ASK_BACK_MODE),
        'last_cycle_at': CNS_RUNTIME.get('last_cycle_at', ''),
    })


@app.route('/agent/tasks', methods=['GET'])
@limiter.exempt
def agent_tasks_list():
    """Compatibility list endpoint for the task monitor panel."""
    limit = request.args.get('limit', default=30, type=int) or 30
    status_filter = (request.args.get('status') or '').strip().lower()
    limit = max(1, min(limit, 100))

    query = AgentTask.query.order_by(AgentTask.updated_at.desc())
    if status_filter:
        query = query.filter(AgentTask.status == status_filter)

    tasks = query.limit(limit).all()
    return jsonify({
        'items': [serialize_task_progress(task) for task in tasks],
        'count': len(tasks),
        'status': status_filter or 'all',
    })


@app.route('/agent/tasks/summary', methods=['GET'])
@limiter.exempt
def agent_tasks_summary():
    """Compatibility summary endpoint for the task monitor panel."""
    all_tasks = AgentTask.query.all()
    counts = {'pending': 0, 'running': 0, 'completed': 0, 'failed': 0}
    blocked_count = 0
    source_counts = {}
    stage_counts = {}
    for task in all_tasks:
        status = str(task.status or 'pending').lower()
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
        blocked, _blocked_by = _task_is_blocked(task)
        if blocked:
            blocked_count += 1
        source_key = str(task.source_channel or 'unknown')
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        stage_key = str(task.workflow_stage or 'unspecified')
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1

    return jsonify({
        'total': len(all_tasks),
        'status_counts': counts,
        'blocked_count': blocked_count,
        'source_counts': source_counts,
        'stage_counts': stage_counts,
    })


@app.route('/system/communication/status', methods=['GET'])
@limiter.exempt
def communication_status():
    latest_notifications = (
        AgentNotification.query
        .order_by(AgentNotification.id.desc())
        .limit(12)
        .all()
    )
    latest_notifications.reverse()

    recent_tasks = AgentTask.query.order_by(AgentTask.updated_at.desc()).limit(20).all()
    blocked_tasks = []
    source_counts = {}
    for task in recent_tasks:
        source_key = str(task.source_channel or 'unknown')
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        blocked, blocked_by = _task_is_blocked(task)
        if blocked:
            blocked_tasks.append({
                'task_id': task.id,
                'title': task.title,
                'assigned_agent': _fuse_agent_key(task.assigned_agent) or task.assigned_agent,
                'blocked_by': blocked_by,
                'workflow_stage': task.workflow_stage or "",
            })

    unread_count = AgentNotification.query.filter_by(is_read=False).count()
    n8n_snapshot = n8n_status().get_json()
    cns_snapshot = cns_status().get_json()

    return jsonify({
        'unread_notifications': unread_count,
        'latest_notifications': [serialize_notification(item) for item in latest_notifications],
        'blocked_tasks': blocked_tasks[:6],
        'source_counts': source_counts,
        'n8n': n8n_snapshot,
        'cns': {
            'enabled': cns_snapshot.get('enabled', False),
            'interval_seconds': cns_snapshot.get('interval_seconds', 0),
            'recent_task_notifications': cns_snapshot.get('recent_task_notifications', [])[:6],
        },
    })


@app.route('/api/n8n/status', methods=['GET'])
def n8n_status():
    return jsonify({
        'enabled': N8N_ENABLED,
        'base_url': N8N_BASE_URL,
        'chat_event_webhook_configured': bool(N8N_CHAT_EVENT_WEBHOOK),
        'task_event_webhook_configured': bool(N8N_TASK_EVENT_WEBHOOK),
        'feed_event_webhook_configured': bool(N8N_FEED_EVENT_WEBHOOK),
        'ingest_enabled': N8N_INGEST_ENABLED,
        'timeout_seconds': N8N_TIMEOUT_SECONDS,
        'music_api_configured': has_configured_key(MUSIC_API_KEY),
    })


@app.route('/api/n8n/task-ingest', methods=['POST'])
@limiter.limit("120 per hour")
def n8n_task_ingest():
    if not N8N_INGEST_ENABLED:
        return jsonify({'error': 'n8n ingest disabled'}), 403
    if not _n8n_request_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '') or '').strip()
    description = str(data.get('description', '') or '').strip()
    assigned_agent = _fuse_agent_key(str(data.get('assigned_agent', 'general') or 'general').strip()) or 'general'
    if not title or not description:
        return jsonify({'error': 'title 和 description 為必填欄位'}), 400
    if assigned_agent not in DEFAULT_DISPATCH_RULES:
        assigned_agent = 'general'

    task = AgentTask(
        title=title[:200],
        description=description[:8000],
        goals=str(data.get('goals', '') or '')[:8000],
        style_guidelines=str(data.get('style_guidelines', '') or '')[:8000],
        constraints=str(data.get('constraints', '') or '')[:8000],
        output_format=str(data.get('output_format', '') or '')[:200],
        model_hint=str(data.get('model_hint', 'auto') or 'auto')[:50],
        assigned_agent=assigned_agent,
        agent_label=_normalize_agent_label_with_fusion(str(data.get('agent_label', '') or ''), assigned_agent=assigned_agent) or f"{assigned_agent}.n8n",
        issue_tags=_json_text(data.get('issue_tags') or infer_signal_tags(title, description, 'n8n')),
        workflow_parent_id=_to_int_or_none(data.get('workflow_parent_id')),
        workflow_stage=str(data.get('workflow_stage', 'n8n_ingest') or 'n8n_ingest')[:80],
        workflow_run_id=str(data.get('workflow_run_id', '') or f"n8n_{uuid.uuid4().hex[:12]}")[:120],
        workflow_relations=_json_text(_normalize_workflow_relations(data.get('workflow_relations'))),
        source_channel='n8n',
        external_ref=str(data.get('external_ref', '') or '')[:160],
        status='pending',
    )
    db.session.add(task)
    db.session.commit()
    emit_task_lifecycle_event(task, "task.ingested_from_n8n", {"source": "n8n"})
    return jsonify({'message': 'task ingested', 'task': serialize_agent_task(task)})


@app.route('/system/model-status', methods=['GET'])
def model_status():
    gpt2_status = get_gpt2_status()
    ollama_available = check_ollama_available()
    zzz_guard = get_zzz_runtime_guard()
    notebooklm_runtime = get_notebooklm_runtime_status(resolve_token=False)
    key_diagnostics = {
        'gemini': inspect_key_format('gemini', GEMINI_API_KEY),
        'nvidia': inspect_key_format('nvidia', NVIDIA_API_KEY),
        'zhizengzeng': inspect_key_format('zhizengzeng', ZZZ_API_KEY),
    }
    model_choices = {
        'auto': True,
        'tinyllama': ollama_available,
        'gpt2': bool(gpt2_status.get('ml_runtime_available') or gpt2_status.get('backend') == 'sidecar'),
        'openai': OPENAI_ENABLED,
        'openrouter': OPENROUTER_ENABLED,
        'groq': GROQ_ENABLED,
        'gemini': GEMINI_ENABLED,
        'nvidia': NVIDIA_ENABLED,
        'zhizengzeng': bool(zzz_guard.get('ready')),
        'huggingface': HF_ENABLED,
        'together': TOGETHER_ENABLED,
        'notebooklm': bool(notebooklm_runtime.get('configured')),
    }
    model_unavailable_reasons = {
        'tinyllama': '' if model_choices['tinyllama'] else '本地 Ollama 服務未啟動或不可連線',
        'gpt2': '' if model_choices['gpt2'] else 'GPT-2 runtime 不可用（且 sidecar 未啟用）',
        'openai': '' if model_choices['openai'] else '未設定有效 OPENAI_API_KEY',
        'openrouter': '' if model_choices['openrouter'] else '未設定有效 OPENROUTER_API_KEY',
        'groq': '' if model_choices['groq'] else '未設定有效 GROQ_API_KEY',
        'gemini': '' if model_choices['gemini'] else '未設定有效 GEMINI_API_KEY',
        'nvidia': '' if model_choices['nvidia'] else '未設定有效 NVIDIA_API_KEY / NVAPI_API_KEY',
        'zhizengzeng': '' if model_choices['zhizengzeng'] else f"ZZZ fail-closed: {', '.join(zzz_guard.get('reasons', [])) or 'not ready'}",
        'huggingface': '' if model_choices['huggingface'] else '未設定有效 HF_API_KEY',
        'together': '' if model_choices['together'] else '未設定有效 TOGETHER_API_KEY',
        'notebooklm': '' if model_choices['notebooklm'] else '; '.join(notebooklm_runtime.get('missing_config', [])),
    }
    return jsonify({
        'gpt2': gpt2_status,
        'ollama_available': ollama_available,
        'local_ollama_model': LOCAL_OLLAMA_MODEL,
        'openai_key_configured': OPENAI_ENABLED,
        'openai_model': OPENAI_MODEL,
        'openrouter_key_configured': OPENROUTER_ENABLED,
        'openrouter_key_slot': OPENROUTER_KEY_SLOT if OPENROUTER_ENABLED else 0,
        'openrouter_model': OPENROUTER_MODEL,
        'groq_key_configured': GROQ_ENABLED,
        'groq_model': GROQ_MODEL,
        'gemini_key_configured': GEMINI_ENABLED,
        'gemini_model': GEMINI_MODEL,
        'gemini_key_diagnostic': key_diagnostics['gemini'],
        'gemini_key_resolution': KEY_RESOLUTION_AUDIT.get('GEMINI_API_KEY', {}),
        'nvidia_key_configured': NVIDIA_ENABLED,
        'nvidia_model': NVIDIA_MODEL,
        'nvidia_key_diagnostic': key_diagnostics['nvidia'],
        'nvidia_key_resolution': KEY_RESOLUTION_AUDIT.get('NVIDIA_API_KEY', {}),
        'zhizengzeng_key_configured': has_configured_key(ZZZ_API_KEY),
        'zhizengzeng_model': ZZZ_MODEL,
        'zhizengzeng_key_diagnostic': key_diagnostics['zhizengzeng'],
        'zhizengzeng_key_resolution': KEY_RESOLUTION_AUDIT.get('ZZZ_API_KEY', {}),
        'zhizengzeng_runtime_ready': bool(zzz_guard.get('ready')),
        'zhizengzeng_runtime_guard_reasons': zzz_guard.get('reasons', []),
        'huggingface_key_configured': HF_ENABLED,
        'together_key_configured': TOGETHER_ENABLED,
        'music_api_configured': has_configured_key(MUSIC_API_KEY),
        'notebooklm_enabled': bool(notebooklm_runtime.get('enabled')),
        'notebooklm_configured': bool(notebooklm_runtime.get('configured')),
        'notebooklm_project_number': notebooklm_runtime.get('project_number', ''),
        'notebooklm_project_number_configured': bool(notebooklm_runtime.get('project_number_configured')),
        'notebooklm_location': notebooklm_runtime.get('location', 'global'),
        'notebooklm_api_base': notebooklm_runtime.get('api_base', ''),
        'notebooklm_api_version': notebooklm_runtime.get('api_version', ''),
        'notebooklm_token_available': bool(notebooklm_runtime.get('token_available')),
        'notebooklm_token_source': notebooklm_runtime.get('token_source', ''),
        'notebooklm_missing_config': notebooklm_runtime.get('missing_config', []),
        'cloud_preferred': PREFER_CLOUD_MODELS,
        'allow_local_model_fallback': ALLOW_LOCAL_MODEL_FALLBACK,
        'execution_provider': EXECUTION_PROVIDER,
        'n8n': {
            'enabled': N8N_ENABLED,
            'base_url': N8N_BASE_URL,
            'chat_event_webhook_configured': bool(N8N_CHAT_EVENT_WEBHOOK),
            'task_event_webhook_configured': bool(N8N_TASK_EVENT_WEBHOOK),
            'feed_event_webhook_configured': bool(N8N_FEED_EVENT_WEBHOOK),
            'ingest_enabled': N8N_INGEST_ENABLED,
            'timeout_seconds': N8N_TIMEOUT_SECONDS,
        },
        'model_choices': model_choices,
        'model_unavailable_reasons': model_unavailable_reasons,
    })


def _is_local_host(hostname: str) -> bool:
    normalized = (hostname or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"} or normalized.endswith(".local")


def _inspect_base_url(base_url: str) -> dict:
    raw = str(base_url or "").strip()
    if not raw:
        return {
            "ok": False,
            "scheme": "",
            "host": "",
            "secure_transport": False,
            "error": "base_url 空白",
        }
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        return {
            "ok": False,
            "scheme": "",
            "host": "",
            "secure_transport": False,
            "error": f"base_url 解析失敗: {exc}",
        }

    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    is_secure = scheme == "https" or (scheme == "http" and _is_local_host(host))
    return {
        "ok": bool(scheme and host),
        "scheme": scheme,
        "host": host,
        "secure_transport": is_secure,
        "error": "" if (scheme and host) else "base_url 缺少協定或主機",
    }


def _severity_score(severity: str) -> int:
    return {
        "critical": 35,
        "high": 25,
        "medium": 12,
        "low": 5,
    }.get((severity or "").lower(), 0)


def get_api_security_status() -> dict:
    zzz_guard = get_zzz_runtime_guard()
    providers = [
        {"key": "openai", "label": "OpenAI", "enabled": OPENAI_ENABLED, "base_url": OPENAI_API_BASE, "model": OPENAI_MODEL},
        {"key": "openrouter", "label": "OpenRouter", "enabled": OPENROUTER_ENABLED, "base_url": OPENROUTER_API_BASE, "model": OPENROUTER_MODEL},
        {"key": "groq", "label": "Groq", "enabled": GROQ_ENABLED, "base_url": GROQ_API_BASE, "model": GROQ_MODEL},
        {"key": "gemini", "label": "Gemini", "enabled": GEMINI_ENABLED, "base_url": GEMINI_API_BASE, "model": GEMINI_MODEL},
        {"key": "nvidia", "label": "NVIDIA", "enabled": NVIDIA_ENABLED, "base_url": NVIDIA_API_BASE, "model": NVIDIA_MODEL},
        {"key": "zhizengzeng", "label": "智增增 ZZZ API", "enabled": bool(zzz_guard.get("ready")), "base_url": ZZZ_API_BASE, "model": ZZZ_MODEL},
        {"key": "huggingface", "label": "Hugging Face", "enabled": HF_ENABLED, "base_url": "https://api-inference.huggingface.co", "model": HF_MODEL},
        {"key": "together", "label": "Together AI", "enabled": TOGETHER_ENABLED, "base_url": "https://api.together.xyz/inference", "model": TOGETHER_MODEL},
    ]
    expected_hosts = {
        "openai": {"api.openai.com"},
        "openrouter": {"openrouter.ai"},
        "groq": {"api.groq.com"},
        "gemini": {"generativelanguage.googleapis.com"},
        "nvidia": {"integrate.api.nvidia.com", "api.nvcf.nvidia.com"},
        "zhizengzeng": {"api.zhizengzeng.com"},
        "huggingface": {"api-inference.huggingface.co"},
        "together": {"api.together.xyz"},
    }

    findings = []
    provider_checks = []
    configured_provider_count = 0

    for provider in providers:
        inspected = _inspect_base_url(provider["base_url"])
        provider_key = provider["key"]
        host = inspected["host"]
        domain_match = True
        if host and expected_hosts.get(provider_key):
            domain_match = host in expected_hosts[provider_key]

        if provider["enabled"]:
            configured_provider_count += 1

            if not inspected["ok"]:
                findings.append({
                    "severity": "high",
                    "type": "invalid_base_url",
                    "provider": provider_key,
                    "message": f"{provider['label']} base_url 格式異常",
                    "action": "請修正 API_BASE 設定，確保含正確協定與主機",
                })
            elif not inspected["secure_transport"]:
                findings.append({
                    "severity": "high",
                    "type": "insecure_transport",
                    "provider": provider_key,
                    "message": f"{provider['label']} 使用非安全傳輸 ({inspected['scheme']})",
                    "action": "改用 HTTPS，僅本機 localhost 測試可保留 HTTP",
                })

            if inspected["ok"] and host and not _is_local_host(host) and not domain_match:
                findings.append({
                    "severity": "medium",
                    "type": "domain_mismatch",
                    "provider": provider_key,
                    "message": f"{provider['label']} 目前指向非預期網域 {host}",
                    "action": "確認是否為受信任代理服務與官方網域",
                })

        provider_checks.append({
            "key": provider_key,
            "label": provider["label"],
            "enabled": bool(provider["enabled"]),
            "base_url": provider["base_url"],
            "model": provider["model"],
            "scheme": inspected["scheme"],
            "host": inspected["host"],
            "secure_transport": bool(inspected["secure_transport"]),
            "domain_match": domain_match,
            "error": inspected["error"],
        })

    if has_configured_key(ZZZ_API_KEY) and not zzz_guard.get("ready"):
        findings.append({
            "severity": "medium",
            "type": "zzz_fail_closed_blocked",
            "provider": "zhizengzeng",
            "message": f"ZZZ 目前被 fail-closed 政策阻擋：{', '.join(zzz_guard.get('reasons', []))}",
            "action": "修正 ZZZ 加密金鑰與安全協議條件後才會啟用",
        })

    debug_mode = bool(globals().get("DEBUG_MODE", True))
    if debug_mode:
        findings.append({
            "severity": "medium",
            "type": "debug_mode_enabled",
            "provider": "system",
            "message": "伺服器目前以 DEBUG 模式執行",
            "action": "正式環境請關閉 DEBUG_MODE",
        })

    rate_limit_storage = str(app.config.get("RATELIMIT_STORAGE_URI", "")).strip().lower()
    rate_limit_storage_configured = str(app.config.get("RATELIMIT_STORAGE_URI_CONFIGURED", "")).strip().lower()
    if rate_limit_storage_configured.startswith(("redis://", "rediss://")) and rate_limit_storage.startswith("memory://"):
        findings.append({
            "severity": "medium",
            "type": "rate_limit_redis_fallback",
            "provider": "system",
            "message": "Rate limit 設定為 Redis，但目前已降級為 memory://",
            "action": "請確認 redis 套件與 Redis 服務可用性",
        })
    if rate_limit_storage.startswith("memory://"):
        findings.append({
            "severity": "low",
            "type": "ephemeral_rate_limit_storage",
            "provider": "system",
            "message": "Rate limit 使用記憶體儲存，重啟後統計會清空",
            "action": "正式環境建議改用持久化儲存（例如 redis）",
        })

    if configured_provider_count == 0:
        findings.append({
            "severity": "low",
            "type": "no_cloud_provider_enabled",
            "provider": "system",
            "message": "目前尚未啟用任何雲端 API 金鑰",
            "action": "若需雲端能力，請至少設定一組有效 API Key",
        })

    if not PRIVACY_MODE:
        findings.append({
            "severity": "low",
            "type": "privacy_mode_disabled",
            "provider": "system",
            "message": "目前聊天內容會以明文方式儲存在本地資料庫",
            "action": "若包含敏感內容，請在 .env 啟用 PRIVACY_MODE=true",
        })

    if SERVER_API_TOKEN_REQUIRED and not SERVER_API_TOKEN:
        findings.append({
            "severity": "high",
            "type": "server_api_token_missing",
            "provider": "system",
            "message": "SERVER_API_TOKEN_REQUIRED=true 但尚未設定 SERVER_API_TOKEN",
            "action": "請設定強隨機 SERVER_API_TOKEN，否則管理 API 應視為不可用",
        })
    if not SERVER_API_TOKEN_REQUIRED:
        findings.append({
            "severity": "medium",
            "type": "server_api_token_validation_disabled",
            "provider": "system",
            "message": "Server 管理 API 未強制 Token 驗證",
            "action": "建議啟用 SERVER_API_TOKEN_REQUIRED=true 並設定 SERVER_API_TOKEN",
        })
    if SERVER_API_IP_ALLOWLIST_ENABLED and not SERVER_API_IP_ALLOWLIST_ENTRIES:
        findings.append({
            "severity": "high",
            "type": "server_api_ip_allowlist_missing",
            "provider": "system",
            "message": "已啟用 Server API IP 白名單，但白名單為空",
            "action": "請設定 SERVER_API_IP_ALLOWLIST，至少包含 127.0.0.1/::1",
        })
    if not SERVER_API_IP_ALLOWLIST_ENABLED:
        findings.append({
            "severity": "low",
            "type": "server_api_ip_allowlist_disabled",
            "provider": "system",
            "message": "Server API 未啟用來源 IP 白名單",
            "action": "若有外網入口，建議啟用 SERVER_API_IP_ALLOWLIST_ENABLED=true",
        })

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    penalty = 0
    for finding in findings:
        severity = (finding.get("severity") or "low").lower()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        penalty += _severity_score(severity)

    security_index = max(0, 100 - penalty)
    if security_index >= 90:
        risk_level = "低風險 / Low"
        grade = "A"
    elif security_index >= 75:
        risk_level = "中風險 / Medium"
        grade = "B"
    elif security_index >= 60:
        risk_level = "偏高 / Elevated"
        grade = "C"
    else:
        risk_level = "高風險 / High"
        grade = "D"

    return {
        "security_index": security_index,
        "grade": grade,
        "risk_level": risk_level,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "summary": {
            "provider_count": len(providers),
            "configured_provider_count": configured_provider_count,
            "finding_count": len(findings),
            "high_severity_count": severity_counts.get("critical", 0) + severity_counts.get("high", 0),
            "medium_severity_count": severity_counts.get("medium", 0),
            "low_severity_count": severity_counts.get("low", 0),
            "privacy_mode": PRIVACY_MODE,
            "server_api_token_required": SERVER_API_TOKEN_REQUIRED,
            "server_api_token_configured": bool(SERVER_API_TOKEN),
            "server_api_ip_allowlist_enabled": SERVER_API_IP_ALLOWLIST_ENABLED,
            "server_api_ip_allowlist_entries_count": len(SERVER_API_IP_ALLOWLIST_ENTRIES),
        },
        "provider_checks": provider_checks,
        "findings": findings,
    }


@app.route('/system/security-status', methods=['GET'])
def security_status():
    return jsonify(get_api_security_status())


@app.route('/system/zzz-security-status', methods=['GET'])
def zzz_security_status():
    zzz_guard = get_zzz_runtime_guard()
    return jsonify({
        'provider': 'zhizengzeng',
        'enabled': bool(zzz_guard.get('ready')),
        'base_url': ZZZ_API_BASE,
        'model': ZZZ_MODEL,
        'security_protocol_enabled': ZZZ_SECURITY_PROTOCOL_ENABLED,
        'response_obfuscation_enabled': ZZZ_OBFUSCATE_RESPONSE,
        'protocol_version': 'shield-v1',
        'key_encryption_enabled': bool(KEY_ENCRYPTION_SECRET),
        'secret_protocol_key_configured': bool(ZZZ_SECRET_PROTOCOL_KEY),
        'fail_closed_enabled': ZZZ_FAIL_CLOSED,
        'guard_reasons': zzz_guard.get('reasons', []),
        'key_resolution': KEY_RESOLUTION_AUDIT.get('ZZZ_API_KEY', {}),
        'checked_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime()),
    })


@app.route('/system/notebooklm/status', methods=['GET'])
@require_server_api_token
def notebooklm_status():
    return jsonify(get_notebooklm_runtime_status(resolve_token=True))


@app.route('/system/notebooklm/notebooks', methods=['GET', 'POST'])
@require_server_api_token
@limiter.limit("60 per hour")
def notebooklm_notebooks():
    payload = request.get_json(silent=True) or {}
    project_number, location = _notebooklm_project_location_from_request(payload=payload)
    if not project_number:
        return jsonify({'error': 'project_number 未提供，請設定 NOTEBOOKLM_PROJECT_NUMBER 或在 request 傳入'}), 400

    parent = f"projects/{project_number}/locations/{location}/notebooks"

    try:
        if request.method == 'GET':
            page_size = request.args.get('page_size', default=20, type=int)
            page_size = max(1, min(page_size or 20, 100))
            page_token = str(request.args.get('page_token', '') or '').strip()
            params = {'pageSize': page_size}
            if page_token:
                params['pageToken'] = page_token
            result = notebooklm_api_request(
                method='GET',
                resource_path=parent,
                params=params,
                token_payload=payload,
            )
            return jsonify({
                'status': 'ok',
                'token_source': result.get('token_source', ''),
                'result': result.get('data', {}),
            }), 200

        notebook_body = payload.get('notebook')
        if not isinstance(notebook_body, dict):
            display_name = str(payload.get('display_name') or payload.get('displayName') or '').strip()
            if not display_name:
                display_name = f"Notebook {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
            notebook_body = {'displayName': display_name[:128]}

        result = notebooklm_api_request(
            method='POST',
            resource_path=parent,
            payload=notebook_body,
            token_payload=payload,
        )
        emit_notification(
            'researcher',
            'NotebookLM 筆記本建立完成',
            notebook_body.get('displayName', 'Notebook')[:200],
            level='info',
            category='notebooklm',
        )
        return jsonify({
            'status': 'created',
            'token_source': result.get('token_source', ''),
            'result': result.get('data', {}),
        }), 201
    except Exception as exc:
        message = str(exc)
        status_code = 503 if ('disabled' in message.lower() or 'unavailable' in message.lower()) else 500
        return jsonify({'error': message}), status_code


@app.route('/system/notebooklm/notebooks/<path:notebook_id>/sources/batch-create', methods=['POST'])
@require_server_api_token
@limiter.limit("60 per hour")
def notebooklm_sources_batch_create(notebook_id):
    payload = request.get_json(silent=True) or {}
    project_number, location = _notebooklm_project_location_from_request(payload=payload)
    try:
        notebook_resource = _notebooklm_notebook_resource_name(
            notebook_id=notebook_id,
            project_number=project_number,
            location=location,
        )
        body = payload.get('body')
        if not isinstance(body, dict):
            if isinstance(payload.get('requests'), list):
                body = {'requests': payload.get('requests')}
            elif isinstance(payload.get('sources'), list):
                auto_requests = []
                for item in payload.get('sources'):
                    if isinstance(item, dict):
                        auto_requests.append({'source': item})
                    else:
                        auto_requests.append({'source': {'inlineText': str(item)}})
                body = {'requests': auto_requests}
            else:
                body = {}
        if not isinstance(body.get('requests'), list) or len(body.get('requests')) == 0:
            return jsonify({'error': '請提供 body.requests 陣列（NotebookLM sources:batchCreate payload）'}), 400

        result = notebooklm_api_request(
            method='POST',
            resource_path=f"{notebook_resource}/sources:batchCreate",
            payload=body,
            token_payload=payload,
        )
        emit_notification(
            'researcher',
            'NotebookLM 來源匯入完成',
            f"{len(body.get('requests') or [])} 筆來源已送出",
            level='info',
            category='notebooklm',
        )
        return jsonify({
            'status': 'ok',
            'token_source': result.get('token_source', ''),
            'result': result.get('data', {}),
        }), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        message = str(exc)
        status_code = 503 if ('disabled' in message.lower() or 'unavailable' in message.lower()) else 500
        return jsonify({'error': message}), status_code


@app.route('/system/notebooklm/notebooks/<path:notebook_id>', methods=['GET', 'DELETE'])
@require_server_api_token
@limiter.limit("80 per hour")
def notebooklm_notebook_detail(notebook_id):
    payload = request.get_json(silent=True) or {}
    project_number, location = _notebooklm_project_location_from_request(payload=payload)
    try:
        notebook_resource = _notebooklm_notebook_resource_name(
            notebook_id=notebook_id,
            project_number=project_number,
            location=location,
        )
        method = 'GET' if request.method == 'GET' else 'DELETE'
        result = notebooklm_api_request(
            method=method,
            resource_path=notebook_resource,
            token_payload=payload,
        )
        return jsonify({
            'status': 'ok' if method == 'GET' else 'deleted',
            'token_source': result.get('token_source', ''),
            'result': result.get('data', {}),
        }), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        message = str(exc)
        status_code = 503 if ('disabled' in message.lower() or 'unavailable' in message.lower()) else 500
        return jsonify({'error': message}), status_code


@app.route('/system/notebooklm/request', methods=['POST'])
@require_server_api_token
@limiter.limit("80 per hour")
def notebooklm_request_proxy():
    payload = request.get_json(silent=True) or {}
    method = str(payload.get('method', 'GET') or 'GET').strip().upper()
    if method not in {'GET', 'POST', 'PATCH', 'DELETE'}:
        return jsonify({'error': 'method 僅支援 GET/POST/PATCH/DELETE'}), 400

    resource_path = str(payload.get('path', '') or '').strip()
    if not resource_path:
        return jsonify({'error': 'path 為必填，格式需為 projects/...'}), 400

    params = payload.get('params')
    if params is not None and not isinstance(params, dict):
        return jsonify({'error': 'params 必須為 JSON 物件'}), 400

    body = payload.get('body')
    if body is not None and not isinstance(body, dict):
        return jsonify({'error': 'body 必須為 JSON 物件'}), 400

    try:
        result = notebooklm_api_request(
            method=method,
            resource_path=resource_path,
            payload=body,
            params=params,
            token_payload=payload,
        )
        return jsonify({
            'status': 'ok',
            'method': method,
            'path': _normalize_notebooklm_resource_path(resource_path),
            'token_source': result.get('token_source', ''),
            'endpoint': result.get('endpoint', ''),
            'result': result.get('data', {}),
        }), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        message = str(exc)
        status_code = 503 if ('disabled' in message.lower() or 'unavailable' in message.lower()) else 500
        return jsonify({'error': message}), status_code


@app.route('/status', methods=['GET'])
@limiter.exempt
def legacy_status():
    model_info = model_status().get_json()
    security_info = get_api_security_status()
    proclaimer_detection = get_proclaimer_detection_status()
    whitehat_detection = get_whitehat_detection_status()
    server_api_auth = get_server_api_auth_status()
    return jsonify({
        'ollama': model_info['ollama_available'],
        'gpt2': model_info['gpt2']['ml_runtime_available'] or model_info['gpt2']['backend'] == 'sidecar',
        'openai': model_info['openai_key_configured'],
        'openrouter': model_info['openrouter_key_configured'],
        'groq': model_info['groq_key_configured'],
        'gemini': model_info.get('gemini_key_configured', False),
        'nvidia': model_info.get('nvidia_key_configured', False),
        'zhizengzeng': model_info.get('zhizengzeng_runtime_ready', False),
        'huggingface': model_info['huggingface_key_configured'],
        'together': model_info['together_key_configured'],
        'security_index': security_info['security_index'],
        'security_risk_level': security_info['risk_level'],
        'proclaimer_detection_status': proclaimer_detection.get('status'),
        'proclaimer_detector_online': bool(proclaimer_detection.get('detector_online')),
        'whitehat_detection_status': whitehat_detection.get('status'),
        'whitehat_detector_online': bool(whitehat_detection.get('detector_online')),
        'server_api_token_required': bool(server_api_auth.get('required')),
        'server_api_token_configured': bool(server_api_auth.get('token_configured')),
    })


@app.route('/health', methods=['GET'])
def health():
    model_info = model_status().get_json()
    security_info = get_api_security_status()
    proclaimer_detection = get_proclaimer_detection_status()
    whitehat_detection = get_whitehat_detection_status()
    db_ok = True
    db_error = ""
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    return jsonify({
        'status': 'ok' if db_ok else 'degraded',
        'timestamp': time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        'database': {
            'ok': db_ok,
            'backend': 'sqlite' if IS_SQLITE_DB else 'postgresql',
            'uri': ACTIVE_DATABASE_URI_REDACTED,
            'path': str(DATABASE_PATH) if IS_SQLITE_DB else "",
            'error': db_error,
        },
        'models': model_info,
        'security': security_info,
        'proclaimer_detection': proclaimer_detection,
        'whitehat_detection': whitehat_detection,
        'cns': {
            'enabled': ENABLE_PROACTIVE_CNS,
            'runtime': CNS_RUNTIME,
        },
    }), (200 if db_ok else 503)


@app.route('/system/cns/run-cycle', methods=['POST'])
@require_server_api_token
@limiter.limit("30 per hour")
def cns_run_cycle():
    summary = run_cns_cycle(cycle_type='manual_trigger')
    return jsonify(summary)


@app.route('/agent/dispatcher/rules', methods=['GET'])
def dispatcher_rules():
    rules = DispatcherRule.query.order_by(DispatcherRule.hit_count.desc(), DispatcherRule.updated_at.desc()).all()
    return jsonify([serialize_dispatcher_rule(rule) for rule in rules])


@app.route('/agent/dispatcher/feedback', methods=['POST'])
@limiter.limit("30 per hour")
def dispatcher_feedback():
    """Teach the dispatcher which agent should handle a kind of message."""
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    corrected_agent = (data.get('corrected_agent') or '').strip()
    predicted_agent = (data.get('predicted_agent') or '').strip()
    notes = (data.get('notes') or '').strip()
    patterns = data.get('patterns')

    if not message:
        return jsonify({'error': 'message 為必填欄位'}), 400
    if corrected_agent not in DEFAULT_DISPATCH_RULES:
        return jsonify({'error': f'corrected_agent 必須為 {list(DEFAULT_DISPATCH_RULES.keys())} 之一'}), 400
    if patterns is not None and not isinstance(patterns, list):
        return jsonify({'error': 'patterns 必須為陣列'}), 400

    learned_patterns = extract_dispatch_patterns(message, patterns)
    if not learned_patterns:
        return jsonify({'error': '無法從訊息中提取可學習的關鍵模式，請提供 patterns'}), 400

    learned_rules = upsert_dispatcher_rules(
        patterns=learned_patterns,
        target_agent=corrected_agent,
        source='user_feedback',
        notes=notes,
        message=message,
    )
    learn_agent_signals(corrected_agent, [message, notes, " ".join(learned_patterns)], source='dispatcher_feedback', message=message, boost=3)

    return jsonify({
        'message': '總管已學習新的分派規則',
        'predicted_agent': predicted_agent,
        'corrected_agent': corrected_agent,
        'learned_patterns': learned_patterns,
        'rules': [serialize_dispatcher_rule(rule) for rule in learned_rules],
        'dispatcher_learning': get_data_framework_summary()['dispatcher'],
    })


@app.route('/system/engineer-research/audit', methods=['POST'])
@require_server_api_token
@limiter.limit("20 per hour")
def engineer_research_audit():
    """
    Engineer-first audit workflow:
    1) 工程師先檢查系統狀態與資料框架衝突
    2) 研究員再掃描本地資料（精神/心理學/精神疾病求生指南/腦神經科學/聖經）
    """
    data = request.get_json(silent=True) or {}
    custom_topics = data.get('topics')
    custom_roots = data.get('roots')
    max_results = data.get('max_results', 120)
    max_scan_files = data.get('max_scan_files', 6000)

    try:
        max_results = max(20, min(int(max_results), 500))
    except Exception:
        max_results = 120

    try:
        max_scan_files = max(500, min(int(max_scan_files), 30000))
    except Exception:
        max_scan_files = 6000

    return jsonify(
        run_engineer_research_audit(
            custom_topics=custom_topics,
            custom_roots=custom_roots,
            max_results=max_results,
            max_scan_files=max_scan_files,
        )
    )


@app.route('/system/cns/scheduler-status', methods=['GET'])
def cns_scheduler_status():
    now_local = time.localtime()
    return jsonify({
        'enabled': {
            'proactive_cns': ENABLE_PROACTIVE_CNS,
            'startup_audit': ENABLE_STARTUP_AUDIT,
            'daily_autonomous_jobs': ENABLE_DAILY_AUTONOMOUS_JOBS,
        },
        'daily_schedule': {
            'hour': DAILY_JOB_HOUR,
            'minute': DAILY_JOB_MINUTE,
            'max_results': DAILY_JOB_MAX_RESULTS,
            'max_scan_files': DAILY_JOB_MAX_SCAN_FILES,
        },
        'runtime': CNS_RUNTIME,
        'will_run_now_if_checked': should_run_daily_job(now_local),
        'now': time.strftime("%Y-%m-%dT%H:%M:%S", now_local),
    })


@app.route('/system/cns/run-daily-jobs', methods=['POST'])
@require_server_api_token
@limiter.limit("10 per hour")
def cns_run_daily_jobs():
    result = run_daily_autonomous_jobs(trigger='manual')
    return jsonify(result)


@app.route('/agent/task', methods=['POST'])
@limiter.limit("40 per hour")
def agent_task():
    """Create a generic task for a specific agent or let dispatcher choose one."""
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    assigned_agent = _fuse_agent_key((data.get('assigned_agent') or '').strip())
    run_async = bool(data.get('run_async', False))
    workflow_parent_id = _to_int_or_none(data.get('workflow_parent_id'))
    workflow_stage = str(data.get('workflow_stage', '') or '').strip()[:80]
    workflow_run_id = str(data.get('workflow_run_id', '') or '').strip()[:120]
    source_channel = str(data.get('source_channel', 'manual_task') or 'manual_task').strip()[:80]
    external_ref = str(data.get('external_ref', '') or '').strip()[:160]
    workflow_relations = _normalize_workflow_relations(data.get('workflow_relations'))

    if not title or not description:
        return jsonify({'error': 'title 和 description 為必填欄位'}), 400

    if not assigned_agent:
        dispatch_result = dispatch_task(description)
        assigned_agent = _fuse_agent_key(dispatch_result.get('agent')) or dispatch_result.get('agent')

    assigned_agent = _fuse_agent_key(assigned_agent) or assigned_agent
    if assigned_agent not in DEFAULT_DISPATCH_RULES:
        return jsonify({'error': f'assigned_agent 必須為 {list(DEFAULT_DISPATCH_RULES.keys())} 之一'}), 400

    signal_tags = infer_signal_tags(title, description, data.get('goals', ''), data.get('constraints', ''))
    agent_label = _normalize_agent_label_with_fusion(infer_agent_label({'assigned_agent': assigned_agent, 'description': description, 'title': title}), assigned_agent=assigned_agent)
    status = 'pending' if run_async else 'running'

    task = AgentTask(
        title=title,
        description=description,
        goals=data.get('goals', ''),
        style_guidelines=data.get('style_guidelines', ''),
        constraints=data.get('constraints', ''),
        output_format=data.get('output_format', ''),
        model_hint=data.get('model_hint', 'auto'),
        assigned_agent=assigned_agent,
        agent_label=agent_label,
        issue_tags=json.dumps(signal_tags, ensure_ascii=False),
        workflow_parent_id=workflow_parent_id,
        workflow_stage=workflow_stage or 'manual_dispatch',
        workflow_run_id=workflow_run_id or f"task_{uuid.uuid4().hex[:12]}",
        workflow_relations=_json_text(workflow_relations),
        source_channel=source_channel,
        external_ref=external_ref,
        status=status,
    )
    db.session.add(task)
    db.session.commit()
    emit_task_lifecycle_event(task, "task.created", {"run_async": run_async, "source": source_channel})

    if run_async:
        return jsonify({
            'message': '任務已加入待辦佇列，將由中樞主動處理',
            'task': serialize_agent_task(task),
        })

    try:
        response, model_used, fallback_attempts = execute_task_with_fallback(
            assigned_agent,
            description,
            task_data={
                'title': title,
                'description': description,
                'goals': data.get('goals', ''),
                'style_guidelines': data.get('style_guidelines', ''),
                'constraints': data.get('constraints', ''),
                'output_format': data.get('output_format', ''),
                'model_hint': data.get('model_hint', 'auto'),
                'assigned_agent': assigned_agent,
                'agent_label': agent_label,
            },
        )
        learning_report = build_learning_report(
            {'title': title, 'description': description, 'assigned_agent': assigned_agent},
            response,
            agent_label=agent_label,
            issue_tags=signal_tags,
        )
        task.result = response
        task.status = 'completed'
        task.learning_report = json.dumps(learning_report, ensure_ascii=False)
        db.session.commit()
        emit_task_lifecycle_event(task, "task.completed", {"model_used": model_used, "source": source_channel, "fallback_attempts": fallback_attempts})
        learn_agent_signals(assigned_agent, [title, description, response], source='generic_task', message=description)
        payload = serialize_agent_task(task)
        payload.update({'response': response, 'model_used': model_used, 'fallback_attempts': fallback_attempts})
        return jsonify(payload)
    except Exception as exc:
        task.status = 'failed'
        task.result = str(exc)
        task.learning_report = json.dumps(build_learning_report({'title': title, 'description': description}, str(exc), agent_label=agent_label, issue_tags=signal_tags), ensure_ascii=False)
        db.session.commit()
        emit_task_lifecycle_event(task, "task.failed", {"error": str(exc), "source": source_channel})
        return jsonify({'error': str(exc)}), 500


@app.route('/api/upload_file', methods=['POST'])
@limiter.limit("30 per hour")
def upload_file():
    data = request.get_json(silent=True) or {}
    raw_filename = str(data.get('filename', '') or '').strip()
    encoded = data.get('data')

    if not raw_filename or not encoded:
        return jsonify({'ok': False, 'error': 'filename 與 data 為必填欄位'}), 400
    if not _allowed_upload_extension(raw_filename):
        return jsonify({'ok': False, 'error': '不支援的檔案類型'}), 400

    safe_name = secure_filename(raw_filename)
    suffix = Path(safe_name).suffix.lower()
    stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}{suffix}"
    upload_dir = Path(app.config.get('UPLOAD_FOLDER', str(UPLOADS_DIR))).expanduser().resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / stored_name

    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception:
        return jsonify({'ok': False, 'error': 'data 必須為有效的 base64 字串'}), 400

    save_path.write_bytes(payload)

    return jsonify({
        'ok': True,
        'filename': raw_filename,
        'stored_name': stored_name,
        'content_type': _guess_content_type(stored_name),
        'size_bytes': len(payload),
        'path': str(save_path),
        'url': f'/uploads/{stored_name}',
    })


@app.route('/uploads/<path:filename>', methods=['GET'])
def serve_uploaded_file(filename: str):
    upload_dir = Path(app.config.get('UPLOAD_FOLDER', str(UPLOADS_DIR))).expanduser().resolve()
    return send_from_directory(upload_dir, filename, as_attachment=False)


@app.route('/agent/xiaobian/video-task', methods=['POST'])
@limiter.limit("20 per hour")
def xiaobian_video_task():
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '') or '').strip()
    description = str(data.get('description', '') or '').strip()
    user_prompt = str(data.get('user_prompt', '') or '').strip()

    if not title or not (description or user_prompt):
        return jsonify({'error': 'title 與 description 或 user_prompt 為必填欄位'}), 400

    workflow_run_id = str(data.get('workflow_run_id', '') or '').strip()[:120] or f"seedance_{uuid.uuid4().hex[:12]}"
    workflow_relations = _normalize_workflow_relations(data.get('workflow_relations'))
    video_request = _video_request_payload(data)
    issue_tags = infer_signal_tags(title, description, user_prompt, video_request.get('creative_submode', ''))

    task = AgentTask(
        title=title,
        description=description or user_prompt,
        goals=data.get('goals', '製作直式影片成片'),
        style_guidelines=data.get('style_guidelines', '直式 9:16、成熟敘事、可直接進入 Seedance/n8n 工作流'),
        constraints=data.get('constraints', '最終輸出至少 3 分鐘，需保留雙語字幕、zh-TW 配音與免版權音效欄位'),
        output_format=data.get('output_format', 'video_task'),
        model_hint=data.get('model_hint', 'seedance2_n8n'),
        assigned_agent='xiaobian',
        agent_label='xiaobian.video_producer',
        issue_tags=json.dumps(issue_tags, ensure_ascii=False),
        learning_report=json.dumps({'video_request': video_request}, ensure_ascii=False),
        workflow_parent_id=_to_int_or_none(data.get('workflow_parent_id')),
        workflow_stage='video_submit',
        workflow_run_id=workflow_run_id,
        workflow_relations=_json_text(workflow_relations),
        source_channel='xiaobian_video_task',
        external_ref=str(data.get('external_ref', '') or '').strip()[:160],
        status='pending',
        result='等待 n8n / Seedance 工作流受理',
    )
    db.session.add(task)
    db.session.commit()

    video_request['task_id'] = task.id
    task.learning_report = json.dumps({'video_request': video_request}, ensure_ascii=False)
    db.session.commit()

    emit_task_lifecycle_event(task, 'task.created', {
        'workflow': 'seedance2_n8n',
        'creative_submode': video_request.get('creative_submode', ''),
        'source': 'xiaobian_video_task',
    })
    _dispatch_n8n_event_async(
        N8N_SEEDANCE_SUBMIT_WEBHOOK,
        'seedance.video.submit',
        {
            'task': serialize_agent_task(task),
            'video_request': video_request,
        },
    )

    return jsonify({
        'message': '小編影片任務已建立，等待 n8n / Seedance 工作流執行',
        'task': serialize_agent_task(task),
    }), 202


@app.route('/api/n8n/seedance-callback', methods=['POST'])
def seedance_callback():
    if not _seedance_callback_authorized(request):
        return jsonify({'error': 'unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    task = None
    task_id = _to_int_or_none(data.get('task_id'))
    workflow_run_id = str(data.get('workflow_run_id', '') or '').strip()

    if task_id is not None:
        task = db.session.get(AgentTask, task_id)
    if task is None and workflow_run_id:
        task = AgentTask.query.filter_by(workflow_run_id=workflow_run_id).first()
    if task is None:
        return jsonify({'error': 'task not found'}), 404

    normalized_status = str(data.get('status', task.status or 'pending') or 'pending').strip().lower()
    stage = str(data.get('stage', '') or '').strip()[:80] or task.workflow_stage or 'video_callback'
    result_video_url = str(data.get('result_video_url', '') or '').strip()
    final_composition_url = str(data.get('final_composition_url', '') or '').strip()
    status_map = {
        'success': 'completed',
        'completed': 'completed',
        'done': 'completed',
        'failed': 'failed',
        'error': 'failed',
        'running': 'running',
        'processing': 'running',
        'queued': 'pending',
        'pending': 'pending',
    }

    task.status = status_map.get(normalized_status, normalized_status or 'pending')
    task.workflow_stage = stage
    if workflow_run_id:
        task.workflow_run_id = workflow_run_id[:120]

    video_result = {
        'status': task.status,
        'stage': stage,
        'result_video_url': result_video_url,
        'final_composition_url': final_composition_url,
        'subtitle_manifest': data.get('subtitle_manifest') if isinstance(data.get('subtitle_manifest'), dict) else {},
        'audio_track_manifest': data.get('audio_track_manifest') if isinstance(data.get('audio_track_manifest'), dict) else {},
        'segment_manifest': data.get('segment_manifest') if isinstance(data.get('segment_manifest'), dict) else {},
        'callback_received_at': datetime.now().isoformat(),
    }
    learning_report = _merge_learning_report(task, {'video_result': video_result})

    summary_parts = []
    if result_video_url:
        summary_parts.append(f"影片結果：{result_video_url}")
    if final_composition_url:
        summary_parts.append(f"成片位置：{final_composition_url}")
    task.result = "；".join(summary_parts) if summary_parts else f"影片任務狀態更新為 {task.status}"
    db.session.commit()

    event_type = {
        'completed': 'task.completed',
        'failed': 'task.failed',
        'running': 'task.running',
    }.get(task.status, 'task.updated')
    emit_task_lifecycle_event(task, event_type, {
        'workflow': 'seedance2_n8n',
        'video_result': video_result,
    })

    return jsonify({
        'ok': True,
        'task': serialize_agent_task(task),
        'learning_report': learning_report,
    })


@app.route('/agent/xiaobian/task', methods=['POST'])
@limiter.limit("20 per hour")
def xiaobian_task():
    """Create and execute a 小編 (design assistant) task."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    description = data.get('description')
    run_async = bool(data.get('run_async', False))
    workflow_parent_id = _to_int_or_none(data.get('workflow_parent_id'))
    workflow_stage = str(data.get('workflow_stage', '') or '').strip()[:80]
    workflow_run_id = str(data.get('workflow_run_id', '') or '').strip()[:120]
    source_channel = str(data.get('source_channel', 'xiaobian_task') or 'xiaobian_task').strip()[:80]
    external_ref = str(data.get('external_ref', '') or '').strip()[:160]
    workflow_relations = _normalize_workflow_relations(data.get('workflow_relations'))

    if not title or not description:
        return jsonify({'error': 'title 和 description 為必填欄位'}), 400

    issue_tags = data.get('issue_tags')
    if issue_tags is not None and not isinstance(issue_tags, list):
        return jsonify({'error': 'issue_tags 必須為陣列'}), 400

    agent_label = _normalize_agent_label_with_fusion(infer_agent_label(data), assigned_agent='xiaobian')

    # Create task record
    task = AgentTask(
        title=title,
        description=description,
        goals=data.get('goals', ''),
        style_guidelines=data.get('style_guidelines', ''),
        constraints=data.get('constraints', ''),
        output_format=data.get('output_format', ''),
        model_hint=data.get('model_hint', 'auto'),
        assigned_agent='xiaobian',
        agent_label=agent_label,
        issue_tags=json.dumps(issue_tags or infer_signal_tags(title, description, data.get('goals', ''), data.get('constraints', '')), ensure_ascii=False),
        workflow_parent_id=workflow_parent_id,
        workflow_stage=workflow_stage or 'xiaobian_direct',
        workflow_run_id=workflow_run_id or f"xiaobian_{uuid.uuid4().hex[:12]}",
        workflow_relations=_json_text(workflow_relations),
        source_channel=source_channel,
        external_ref=external_ref,
        status='pending' if run_async else 'running'
    )
    db.session.add(task)
    db.session.commit()
    emit_task_lifecycle_event(task, "task.created", {"run_async": run_async, "source": source_channel})

    if run_async:
        return jsonify({
            'message': '小編任務已進入主動工作佇列',
            'task': serialize_agent_task(task),
        })

    try:
        response, model_used = xiaobian_generate(data)
        learning_report = build_learning_report(
            data,
            response,
            agent_label=agent_label,
            issue_tags=_parse_json_text(task.issue_tags, []),
        )
        task.result = response
        task.status = 'completed'
        task.learning_report = json.dumps(learning_report, ensure_ascii=False)
        learn_agent_signals('xiaobian', [title, description, response], source='xiaobian_task', message=description)
        db.session.commit()
        emit_task_lifecycle_event(task, "task.completed", {"model_used": model_used, "source": source_channel})
        payload = serialize_agent_task(task)
        payload.update({
            'response': response,
            'model_used': model_used,
        })
        return jsonify(payload)
    except Exception as e:
        logging.error(f"小編任務執行失敗: {e}")
        task.status = 'failed'
        task.result = str(e)
        task.learning_report = json.dumps(build_learning_report(data, str(e), agent_label=agent_label, issue_tags=_parse_json_text(task.issue_tags, [])), ensure_ascii=False)
        db.session.commit()
        emit_task_lifecycle_event(task, "task.failed", {"error": str(e), "source": source_channel})
        return jsonify({'error': str(e)}), 500


@app.route('/agent/xiaobian/profile', methods=['GET', 'POST'])
def xiaobian_profile():
    """Get or update 小編 user profile context."""
    if request.method == 'GET':
        profile = get_xiaobian_profile()
        return jsonify({'profile': profile})

    # POST updates profile
    data = request.json or {}
    profile_data = data.get('profile')
    if not isinstance(profile_data, dict):
        return jsonify({'error': 'profile must be a JSON object'}), 400

    set_xiaobian_profile(profile_data)
    return jsonify({'message': 'Profile updated', 'profile': profile_data})


@app.route('/agent/xiaobian/chat', methods=['POST'])
@limiter.limit("30 per hour")
def xiaobian_chat():
    """Interact with 小編 in a conversational style, maintaining profile context."""
    data = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    # Optional: store conversation history for context (simple in-memory or DB)
    # For now, we accept optional conversation list for the prompt.
    conversation = data.get('conversation')
    if conversation and not isinstance(conversation, list):
        return jsonify({'error': 'conversation must be a list of {role,text} objects'}), 400
    runtime_ctx = build_runtime_task_context(data)

    task_data = {
        'title': '即時任務（小編）',
        'description': f'使用者詢問：{message}',
        'goals': data.get('goals', ''),
        'style_guidelines': data.get('style_guidelines', ''),
        'constraints': "；".join(filter(None, [str(data.get('constraints', '') or ''), runtime_ctx.get('context_text', '')])),
        'output_format': data.get('output_format', ''),
        'model_hint': data.get('model_hint', 'auto'),
        'agent_label': data.get('agent_label', ''),
        'interaction_mode': runtime_ctx.get('interaction_mode', ''),
        'creative_submode': runtime_ctx.get('creative_submode', ''),
        'video_workflow_engine': runtime_ctx.get('video_workflow_engine', ''),
    }
    task_data['domain'] = infer_task_domain(task_data)

    try:
        response, model_used = xiaobian_generate(task_data, conversation=conversation)
        response, safety_guard = guard_black_gray_response(
            user_message=message,
            ai_response=response,
            model_choice=task_data.get('model_hint', 'auto'),
            agent_key='xiaobian',
            model_used=model_used,
        )
        if safety_guard.get('triggered'):
            emit_notification(
                _fused_safety_agent_key(),
                '小編內容安全攔截',
                '小編回覆命中黑灰產風險詞，已改寫為安全回覆',
                level='warning',
                category='safety',
                details={
                    'agent': 'xiaobian',
                    'model_used': model_used,
                    'matched_terms': safety_guard.get('matched_terms', []),
                    'promotion_terms': safety_guard.get('promotion_terms', []),
                    'regenerated': bool(safety_guard.get('regenerated')),
                    'fallback_used': bool(safety_guard.get('fallback_used')),
                },
            )
        learning_report = build_learning_report(task_data, response)
        learn_agent_signals('xiaobian', [message, response], source='xiaobian_chat', message=message)
        create_conversation_feed_task(
            user_message=message,
            ai_response=response,
            agent_key='xiaobian',
            model_used=model_used,
            routing={
                'reason': 'xiaobian_chat',
                'signal_tags': learning_report['signal_tags'],
                'runtime_context': runtime_ctx,
            },
            source_channel='xiaobian_chat',
        )
        emit_chat_lifecycle_event(
            "chat.xiaobian.completed",
            {
                "agent": "xiaobian",
                "model_used": model_used,
                "domain": task_data.get('domain', 'design'),
                "creative_submode": runtime_ctx.get('creative_submode', ''),
                "video_workflow_engine": runtime_ctx.get('video_workflow_engine', ''),
            },
        )
        return jsonify({
            'response': response,
            'model_used': model_used,
            'profile': get_xiaobian_profile(),
            'agent_label': learning_report['agent_label'],
            'issue_tags': learning_report['issue_tags'],
            'learning_report': learning_report,
            'safety_guard': {
                'triggered': bool(safety_guard.get('triggered')),
                'regenerated': bool(safety_guard.get('regenerated')),
                'fallback_used': bool(safety_guard.get('fallback_used')),
            },
        })
    except Exception as e:
        logging.error(f"小編對話失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/agent/xiaobian/tasks', methods=['GET'])
def xiaobian_tasks():
    """List 小編任務摘要."""
    tasks = AgentTask.query.order_by(AgentTask.created_at.desc()).limit(20).all()
    return jsonify([{
        'task_id': t.id,
        'title': t.title,
        'assigned_agent': t.assigned_agent,
        'agent_label': t.agent_label,
        'issue_tags': _parse_json_text(t.issue_tags, []),
        'status': t.status,
        'updated_at': t.updated_at.isoformat(),
    } for t in tasks])


@app.route('/agent/xiaobian/task/<int:task_id>', methods=['GET'])
def xiaobian_task_status(task_id):
    """Fetch details of a single 小編 task."""
    task = db.session.get(AgentTask, task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(serialize_agent_task(task))


def _serialize_archive_history(limit: int = 2000) -> list[dict]:
    records = (
        ChatHistory.query
        .order_by(ChatHistory.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            'id': record.id,
            'timestamp': record.timestamp.isoformat() if record.timestamp else None,
            'agent_type': record.agent_type,
            'model_used': record.model_used,
            'user_message': record.user_message,
            'ai_response': record.ai_response,
            'signal_tags': record.signal_tags,
            'routing_reason': record.routing_reason,
        }
        for record in records
    ]


@app.route('/archive/list', methods=['GET'])
@limiter.exempt
def archive_list():
    files = []
    for item in sorted(ARCHIVE_DIR.glob('archive_*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        files.append(
            {
                'name': item.name,
                'size_kb': round(item.stat().st_size / 1024, 1),
                'modified_at': datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
            }
        )
    return jsonify({'files': files})


@app.route('/archive/export', methods=['POST'])
def archive_export():
    payload = {
        'created_at': datetime.now().isoformat(),
        'workspace': str(BASE_DIR),
        'records': _serialize_archive_history(limit=2000),
    }
    target = ARCHIVE_DIR / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return jsonify(
        {
            'ok': True,
            'records': len(payload['records']),
            'size_kb': round(target.stat().st_size / 1024, 1),
            'file': str(target),
        }
    )


@app.route('/archive/cleanup', methods=['POST'])
def archive_cleanup():
    payload = request.get_json(silent=True) or {}
    keep_days = int(payload.get('keep_days', 30) or 30)
    cutoff = datetime.now() - timedelta(days=keep_days)

    stale_records = ChatHistory.query.filter(ChatHistory.timestamp < cutoff).all()
    deleted_records = len(stale_records)
    for record in stale_records:
        db.session.delete(record)
    db.session.commit()

    deleted_files = 0
    for item in ARCHIVE_DIR.glob('archive_*.json'):
        if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
            item.unlink(missing_ok=True)
            deleted_files += 1

    return jsonify(
        {
            'ok': True,
            'deleted_records': deleted_records,
            'merged_archived_records': deleted_files,
            'keep_days': keep_days,
        }
    )

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() == "true"
SERVER_HOST = os.getenv("CHAT_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("CHAT_SERVER_PORT", "5001"))

if __name__ != '__main__':
    start_startup_bootstrap_worker()

if __name__ == '__main__':
    start_startup_bootstrap_worker()
    app.run(debug=DEBUG_MODE, host=SERVER_HOST, port=SERVER_PORT)
