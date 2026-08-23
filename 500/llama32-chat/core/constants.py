"""
常量定義 - 集中管理所有常量，便於配置和維護
"""

# ============ 模型相關常量 ============
AVAILABLE_MODELS = ["ollama", "openai", "gemini", "claude", "xai", "groq", "custom"]
DEFAULT_MODEL = "ollama"

# 默認模型及參數
DEFAULT_MODELS = {
    "ollama": "llama3.2",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-flash",
    "claude": "claude-3-5-sonnet-20240620",
    "xai": "grok-2-latest",
    "groq": "llama-3.1-70b-versatile",
    "custom": "custom",
}

# 模型優先級（用於故障轉移）
# 已暫時關閉付費服務：openai, xai, custom
# 保留免費服務：ollama (本地), groq (雲端快速), gemini (大量免費額度), claude (有限免費額度)
MODEL_PRIORITY = ["ollama", "groq", "gemini", "claude"]

# ============ 任務相關常量 ============
PRIORITY_LEVELS = {1: "🔴 高", 2: "🟡 中", 3: "🟢 低"}

TASK_STATUS = {
    "pending": "待處理",
    "in_progress": "進行中",
    "completed": "已完成",
    "failed": "已失敗",
}

# ============ 重試和故障轉移相關常量 ============
MAX_FAILOVER_ATTEMPTS = 3
MAX_RETRY_COUNT = 3
CONSECUTIVE_FAILURE_THRESHOLD = 3
HEALTH_CHECK_INTERVAL = 300  # 秒
COOLDOWN_SECONDS = 300  # 5分鐘

# ============ 性能監控相關常量 ============
PERFORMANCE_WINDOW = 100  # 評估窗口（最近N次調用）

# ============ 超時相關常量 ============
DEFAULT_TIMEOUT = 120  # 秒
API_TIMEOUT = 90  # 秒
OLLAMA_TIMEOUT = 90  # Ollama 超時（秒）
OLLAMA_CONNECT_TIMEOUT = 10  # Ollama 連接超時（秒）
OLLAMA_MAX_RETRIES = 3  # Ollama 最大重試次數

# ============ 文件和目錄相關常量 ============
from pathlib import Path

BASE_DIR = Path(__file__).parent
# 專案根（llama32-chat）：與 `data/`、`logs/`、`tasks/` 對齊，避免 core/data 與上層 data 分裂
PROJECT_ROOT = BASE_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
TASKS_DIR = PROJECT_ROOT / "tasks"

RAG_DB_DIR = DATA_DIR / "chroma_db"
RAG_COLLECTION = "conversations"
RAG_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

CONVERSATION_FILE = DATA_DIR / "conversations.json"
ERROR_LOG_FILE = LOGS_DIR / "agent.log"
TASKS_FILE = TASKS_DIR / "tasks.json"
TASK_HISTORY_FILE = TASKS_DIR / "history.json"
AUTONOMOUS_CONFIG_FILE = BASE_DIR / "autonomous_config.json"

# 智能體性能數據文件（用於持久化學習）
AGENT_PERFORMANCE_FILE = DATA_DIR / "agent_performance.json"
AGENT_HEALTH_FILE = DATA_DIR / "agent_health.json"

# ============ 任務類型偏好設置 ============
TASK_TYPE_PREFERENCES = {
    "code": ["gemini", "claude", "openai", "ollama"],
    "creative": ["claude", "openai", "xai", "gemini"],
    "analysis": ["claude", "openai", "gemini", "xai"],
    "conversation": ["ollama", "gemini", "claude", "openai"],
    "default": ["ollama", "gemini", "claude", "openai", "xai"],
}

# ============ 任務類型關鍵詞 ============
CODE_KEYWORDS = [
    "代碼",
    "code",
    "程序",
    "program",
    "函數",
    "function",
    "bug",
    "錯誤",
    "python",
    "javascript",
    "java",
    "編程",
    "programming",
    "算法",
    "algorithm",
]

CREATIVE_KEYWORDS = [
    "故事",
    "story",
    "詩",
    "poem",
    "創意",
    "creative",
    "寫作",
    "writing",
    "小說",
    "novel",
    "歌詞",
    "lyrics",
    "想象",
    "imagine",
]

ANALYSIS_KEYWORDS = [
    "分析",
    "analysis",
    "評估",
    "evaluate",
    "比較",
    "compare",
    "總結",
    "summarize",
    "數據",
    "data",
    "統計",
    "statistics",
]

# ============ 環境變數默認值 ============
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_HEALTH_URL = "http://localhost:11434/api/tags"
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"

# ============ UI 相關常量 ============
SEPARATOR_LINE = "=" * 60
SHORT_SEPARATOR = "-" * 60
TRUNCATE_LENGTH = 50

# ============ 模型類型 ============
MODEL_TYPES = {
    "ollama": "http",
    "openai": "openai_api",
    "gemini": "genai",
    "claude": "anthropic_api",
    "xai": "openai_compatible",
    "custom": "http",
}

# ============ 性能評分體系 ============
# 用於計算模型評分的權重（總和為100）
MODEL_SCORING_WEIGHTS = {
    "success_rate": 50,  # 成功率權重（最重要）
    "response_time": 20,  # 響應速度權重
    "consistency": 15,  # 穩定性權重（變異性小）
    "recency": 15,  # 近期表現權重（最近的結果更重要）
}

# 冷卻驗證相關
COOLDOWN_VERIFICATION_ATTEMPTS = 2  # 冷卻後驗證次數
COOLDOWN_VERIFICATION_THRESHOLD = 0.5  # 驗證成功率閾值（50%）

# 故障分類
ERROR_TYPES = {
    "connection_error": "連接錯誤",
    "config_error": "配置錯誤",
    "api_error": "API錯誤",
    "rate_limit_error": "限流錯誤",
    "timeout_error": "超時",
    "unknown_error": "未知錯誤",
}
