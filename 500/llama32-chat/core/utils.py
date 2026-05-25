"""
工具函數 - 集中管理時間操作、JSON 文件操作等通用功能
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List


# ============ 時間工具類 ============
class TimeHelper:
    """時間操作的統一接口"""

    @staticmethod
    def now_iso() -> str:
        """獲取當前時間的 ISO 格式字符串"""
        return datetime.now().isoformat()

    @staticmethod
    def parse_iso(iso_string: str) -> Optional[datetime]:
        """解析 ISO 格式的時間字符串"""
        try:
            return datetime.fromisoformat(iso_string)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def duration(start_iso: str, end_iso: str) -> str:
        """計算兩個 ISO 格式時間之間的時間差"""
        try:
            start = datetime.fromisoformat(start_iso)
            end = datetime.fromisoformat(end_iso)
            seconds = (end - start).total_seconds()
            return f"{seconds:.1f}秒"
        except (ValueError, TypeError, AttributeError):
            return "未知"

    @staticmethod
    def elapsed_since(start_iso: str) -> float:
        """計算從指定時間到現在經過的秒數"""
        try:
            start = datetime.fromisoformat(start_iso)
            seconds = (datetime.now() - start).total_seconds()
            return seconds
        except (ValueError, TypeError):
            return -1


# ============ JSON 存儲工具類 ============
class JsonStorage:
    """JSON 文件的讀寫操作"""

    @staticmethod
    def load(file_path: Path, default=None) -> Any:
        """
        安全加載 JSON 文件

        Args:
            file_path: 文件路徑
            default: 文件不存在或加載失敗時的默認值

        Returns:
            加載的 JSON 數據或默認值
        """
        file_path = Path(file_path)
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except json.JSONDecodeError as e:
            logging.warning(f"JSON 文件格式錯誤 {file_path}: {e}")
        except Exception as e:
            logging.error(f"加載文件失敗 {file_path}: {e}")

        return default if default is not None else {}

    @staticmethod
    def save(file_path: Path, data: Any, create_backup: bool = False) -> bool:
        """
        安全保存 JSON 文件

        Args:
            file_path: 文件路徑
            data: 要保存的數據
            create_backup: 是否備份原文件

        Returns:
            是否保存成功
        """
        file_path = Path(file_path)
        try:
            # 創建目錄
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 備份原文件
            if create_backup and file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                file_path.rename(backup_path)

            # 保存文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logging.error(f"保存文件失敗 {file_path}: {e}")
            return False

    @staticmethod
    def append(file_path: Path, item: Dict) -> bool:
        """
        追加一條記錄到 JSON 數組文件（用於日誌文件）

        Args:
            file_path: 文件路徑
            item: 要追加的項

        Returns:
            是否追加成功
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                # 創建新文件
                return JsonStorage.save(file_path, [item])
            else:
                # 追加到現有文件
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
                return True
        except Exception as e:
            logging.error(f"追加失敗 {file_path}: {e}")
            return False


# ============ 日誌工具類 ============
class LogHelper:
    """日誌操作的統一接口"""

    _loggers: Dict[str, logging.Logger] = {}

    @staticmethod
    def get_logger(name: str, log_file: Optional[Path] = None) -> logging.Logger:
        """
        獲取或創建日誌記錄器

        Args:
            name: 日誌記錄器名稱
            log_file: 日誌文件路徑（可選）

        Returns:
            日誌記錄器實例
        """
        if name in LogHelper._loggers:
            return LogHelper._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # 添加控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 如果指定了日誌文件，添加文件處理器
        if log_file:
            log_file = Path(log_file)
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        LogHelper._loggers[name] = logger
        return logger


# ============ 打印格式化工具 ============
class PrintHelper:
    """打印輸出的統一格式"""

    @staticmethod
    def header(title: str, width: int = 60):
        """打印標題欄"""
        print("\n" + "=" * width)
        print(f"📊 【{title}】")
        print("=" * width)

    @staticmethod
    def footer(width: int = 60):
        """打印底部分隔線"""
        print("=" * width + "\n")

    @staticmethod
    def section(title: str, width: int = 60):
        """打印小節標題"""
        print(f"\n{title}")
        print("-" * width)

    @staticmethod
    def success(message: str):
        """打印成功消息"""
        print(f"✅ {message}")

    @staticmethod
    def error(message: str):
        """打印錯誤消息"""
        print(f"❌ {message}")

    @staticmethod
    def warning(message: str):
        """打印警告消息"""
        print(f"⚠️  {message}")

    @staticmethod
    def info(message: str):
        """打印信息消息"""
        print(f"ℹ️  {message}")

    @staticmethod
    def truncate(text: str, length: int = 50) -> str:
        """截斷文本"""
        if len(text) > length:
            return text[:length] + "..."
        return text


# ============ 文件操作工具 ============
class FileHelper:
    """文件操作的統一接口"""

    @staticmethod
    def ensure_dir(path: Path) -> Path:
        """確保目錄存在"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def ensure_dirs(*paths: Path) -> List[Path]:
        """確保多個目錄存在"""
        return [FileHelper.ensure_dir(p) for p in paths]

    @staticmethod
    def read_text(file_path: Path, encoding: str = "utf-8") -> Optional[str]:
        """安全讀取文本文件"""
        try:
            return Path(file_path).read_text(encoding=encoding)
        except Exception as e:
            logging.error(f"讀取文件失敗 {file_path}: {e}")
            return None

    @staticmethod
    def write_text(file_path: Path, content: str, encoding: str = "utf-8") -> bool:
        """安全寫入文本文件"""
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            return True
        except Exception as e:
            logging.error(f"寫入文件失敗 {file_path}: {e}")
            return False


# ============ 字符串處理工具 ============
class StringHelper:
    """字符串操作的統一接口"""

    @staticmethod
    def truncate(text: str, max_length: int = 50, suffix: str = "...") -> str:
        """截斷字符串"""
        if len(text) > max_length:
            return text[:max_length] + suffix
        return text

    @staticmethod
    def normalize(text: str) -> str:
        """標準化字符串（移除多余空格）"""
        return " ".join(text.split())

    @staticmethod
    def is_empty(text: str) -> bool:
        """檢查字符串是否為空"""
        return not text or not text.strip()


# ============ 對話管理工具 ============
def get_timestamp() -> str:
    """獲取當前時間戳（ISO 格式）"""
    return TimeHelper.now_iso()


def load_conversations(data_dir: str = "data") -> List[Dict]:
    """
    加載對話記錄

    Args:
        data_dir: 數據目錄

    Returns:
        對話列表
    """
    conversations_file = Path(data_dir) / "conversations.json"
    return JsonStorage.load(conversations_file, default=[])


def save_conversations(conversations: List[Dict], data_dir: str = "data") -> bool:
    """
    保存對話記錄

    Args:
        conversations: 對話列表
        data_dir: 數據目錄

    Returns:
        是否保存成功
    """
    conversations_file = Path(data_dir) / "conversations.json"
    return JsonStorage.save(conversations_file, conversations)
