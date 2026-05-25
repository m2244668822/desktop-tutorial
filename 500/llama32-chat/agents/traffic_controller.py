"""
速率限制和流量控制模組
支持多個 AI 模型的限流、重試、快取等機制
"""

import time
import json
import hashlib
from threading import Lock
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable
import logging

logger = logging.getLogger(__name__)


# ============ 速率限制器 ============


class RateLimiter:
    """
    基於滑動時間窗口的速率限制器
    使用令牌桶算法
    """

    def __init__(self, max_requests: int, time_window: int = 60):
        """
        初始化速率限制器

        Args:
            max_requests: 時間窗口內最大請求數
            time_window: 時間窗口（秒），默認 60 秒
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times = deque()
        self.lock = Lock()

    def is_allowed(self) -> bool:
        """檢查是否允許請求"""
        with self.lock:
            now = time.time()

            # 移除超出時間窗口的請求
            while self.request_times and self.request_times[0] < now - self.time_window:
                self.request_times.popleft()

            # 檢查是否超過限制
            if len(self.request_times) < self.max_requests:
                self.request_times.append(now)
                return True

            return False

    def wait_if_needed(self):
        """如果超過限制就等待"""
        while not self.is_allowed():
            time.sleep(0.1)  # 每 100ms 檢查一次

    def get_wait_time(self) -> float:
        """取得需要等待的時間（秒）"""
        with self.lock:
            if len(self.request_times) < self.max_requests:
                return 0.0

            oldest_request = self.request_times[0]
            now = time.time()
            wait_time = (oldest_request + self.time_window) - now
            return max(0.0, wait_time)

    def reset(self):
        """重置限制器"""
        with self.lock:
            self.request_times.clear()


class DailyLimitChecker:
    """
    檢查每日配額限制
    """

    def __init__(self, daily_limit: int, reset_hour: int = 0):
        """
        初始化每日限制檢查器

        Args:
            daily_limit: 每日最大請求數
            reset_hour: 重置時間（小時，0-23），默認午夜
        """
        self.daily_limit = daily_limit
        self.reset_hour = reset_hour
        self.request_count = 0
        self.reset_date = datetime.now().date()
        self.lock = Lock()

    def _should_reset(self) -> bool:
        """檢查是否應重置計數"""
        now = datetime.now()
        if now.date() > self.reset_date or now.hour >= self.reset_hour:
            return True
        return False

    def can_request(self) -> bool:
        """檢查是否可以發起請求"""
        with self.lock:
            if self._should_reset():
                self.request_count = 0
                self.reset_date = datetime.now().date()

            return self.request_count < self.daily_limit

    def increment(self) -> int:
        """增加計數並返回新計數"""
        with self.lock:
            if self._should_reset():
                self.request_count = 0
                self.reset_date = datetime.now().date()

            self.request_count += 1
            return self.request_count

    def get_remaining(self) -> int:
        """取得今日剩餘配額"""
        with self.lock:
            if self._should_reset():
                return self.daily_limit
            return max(0, self.daily_limit - self.request_count)


# ============ 重試機制 ============


class ExponentialBackoff:
    """
    指數退避重試機制
    """

    def __init__(
        self, base_wait: float = 1, max_wait: float = 60, max_attempts: int = 5
    ):
        """
        初始化指數退避

        Args:
            base_wait: 基礎等待時間（秒）
            max_wait: 最大等待時間（秒）
            max_attempts: 最大重試次數
        """
        self.base_wait = base_wait
        self.max_wait = max_wait
        self.max_attempts = max_attempts

    def get_wait_time(self, attempt: int) -> float:
        """計算第 N 次嘗試應等待的時間"""
        import random

        wait_time = self.base_wait * (2**attempt)
        wait_time = min(wait_time, self.max_wait)
        # 添加隨機抖動，避免雷鳴羊群效應
        jitter = random.uniform(0, wait_time * 0.1)
        return wait_time + jitter

    def retry(self, func: Callable, *args, **kwargs):
        """
        帶有指數退避的重試

        Args:
            func: 要執行的函數
            *args, **kwargs: 函數的參數

        Returns:
            函數的返回值

        Raises:
            Exception: 如果所有重試都失敗
        """
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                # 最後一次嘗試不等待
                if attempt < self.max_attempts - 1:
                    wait_time = self.get_wait_time(attempt)
                    logger.warning(
                        f"⚠️  嘗試 {attempt + 1}/{self.max_attempts} 失敗：{str(e)}\n"
                        f"⏳ {wait_time:.1f} 秒後重試..."
                    )
                    time.sleep(wait_time)

        raise last_exception


# ============ 響應快取 ============


class ResponseCache:
    """
    簡單的響應快取，基於提示的哈希值
    """

    def __init__(self, cache_file: str = "response_cache.json", ttl_hours: int = 24):
        """
        初始化快取

        Args:
            cache_file: 快取檔案路徑
            ttl_hours: 快取有效期（小時）
        """
        self.cache_file = cache_file
        self.ttl_hours = ttl_hours
        self.cache = self._load_cache()
        self.lock = Lock()

    @staticmethod
    def _get_hash(prompt: str) -> str:
        """生成提示的哈希值"""
        return hashlib.md5(prompt.encode()).hexdigest()

    def _load_cache(self) -> Dict:
        """從檔案載入快取"""
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"無法載入快取檔案：{e}")
            return {}

    def _save_cache(self):
        """保存快取到檔案"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"無法保存快取檔案：{e}")

    def get(self, prompt: str, model: str = None) -> Optional[str]:
        """
        取得快取的回應

        Args:
            prompt: 提示詞
            model: 模型名稱（用於區分同一提示的不同模型回應）

        Returns:
            快取的回應，或 None 如果不存在或已過期
        """
        with self.lock:
            hash_val = self._get_hash(prompt)
            key = f"{hash_val}_{model}" if model else hash_val

            if key not in self.cache:
                return None

            cached_item = self.cache[key]

            # 檢查是否過期
            created_at = datetime.fromisoformat(cached_item.get("created_at", ""))
            if datetime.now() - created_at > timedelta(hours=self.ttl_hours):
                del self.cache[key]
                self._save_cache()
                return None

            return cached_item.get("response")

    def set(self, prompt: str, response: str, model: str = None):
        """
        保存回應到快取

        Args:
            prompt: 提示詞
            response: 模型回應
            model: 模型名稱
        """
        with self.lock:
            hash_val = self._get_hash(prompt)
            key = f"{hash_val}_{model}" if model else hash_val

            self.cache[key] = {
                "prompt": prompt[:100],  # 只保存前 100 字
                "response": response,
                "model": model,
                "created_at": datetime.now().isoformat(),
            }

            self._save_cache()

    def clear(self):
        """清空所有快取"""
        with self.lock:
            self.cache.clear()
            self._save_cache()

    def get_stats(self) -> Dict:
        """取得快取統計信息"""
        with self.lock:
            return {
                "total_cached": len(self.cache),
                "cache_size_bytes": len(json.dumps(self.cache)),
            }


# ============ 流量管理器 ============


class TrafficController:
    """
    全局流量控制器
    管理所有模型的速率限制、重試、快取等
    """

    def __init__(self):
        """初始化流量控制器"""
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.daily_limiters: Dict[str, DailyLimitChecker] = {}
        self.retry_handler = ExponentialBackoff()
        self.cache = ResponseCache()
        self.request_log: Dict[str, list] = {}
        self.lock = Lock()

    def register_model(self, model: str, rpm: int = 60, daily_limit: int = None):
        """
        註冊模型的流量限制

        Args:
            model: 模型名稱
            rpm: 每分鐘請求數
            daily_limit: 每日請求限制（可選）
        """
        self.rate_limiters[model] = RateLimiter(rpm, 60)

        if daily_limit:
            self.daily_limiters[model] = DailyLimitChecker(daily_limit)

        self.request_log[model] = []

    def can_request(self, model: str) -> tuple[bool, str]:
        """
        檢查是否可以發起請求

        Returns:
            (是否允許, 原因文本)
        """
        # 檢查每日限制
        if model in self.daily_limiters:
            if not self.daily_limiters[model].can_request():
                remaining = self.daily_limiters[model].get_remaining()
                return False, f"超過每日限制（剩餘：{remaining}）"

        # 檢查速率限制
        if model in self.rate_limiters:
            if not self.rate_limiters[model].is_allowed():
                wait_time = self.rate_limiters[model].get_wait_time()
                return False, f"超過速率限制（等待 {wait_time:.1f} 秒）"

        return True, "允許"

    def wait_for_availability(self, model: str):
        """等待直到模型可用"""
        if model in self.rate_limiters:
            self.rate_limiters[model].wait_if_needed()

        if model in self.daily_limiters:
            if not self.daily_limiters[model].can_request():
                logger.warning(f"⚠️  {model} 今日配額已用完")
                raise RuntimeError(f"{model} 每日限制已達")

    def log_request(self, model: str, prompt: str, response: str, success: bool = True):
        """記錄請求"""
        with self.lock:
            self.request_log[model].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "prompt": prompt[:50],
                    "response_length": len(response),
                    "success": success,
                }
            )

            # 每日限制增加
            if model in self.daily_limiters:
                self.daily_limiters[model].increment()

            # 只保留最近 1000 條記錄
            if len(self.request_log[model]) > 1000:
                self.request_log[model] = self.request_log[model][-1000:]

    def get_stats(self, model: str = None) -> Dict:
        """取得流量統計"""
        with self.lock:
            if model:
                return {
                    "model": model,
                    "requests": len(self.request_log.get(model, [])),
                    "cache": self.cache.get_stats(),
                }

            return {
                "total_models": len(self.rate_limiters),
                "total_requests": sum(
                    len(self.request_log.get(m, [])) for m in self.rate_limiters
                ),
                "cache": self.cache.get_stats(),
            }


# ============ 使用示例 ============

if __name__ == "__main__":
    # 配置日誌
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 創建流量控制器
    controller = TrafficController()

    # 註冊各個模型
    controller.register_model("ollama", rpm=999)  # 本地無限
    controller.register_model("gemini", rpm=60, daily_limit=1500)
    controller.register_model("groq", rpm=30, daily_limit=5000)
    controller.register_model("claude", rpm=50, daily_limit=100)

    print("✅ 流量控制器已初始化")
    print(f"統計：{controller.get_stats()}")

    # 示例：模擬請求
    test_prompt = "請簡短介紹一下人工智能"
    test_model = "gemini"

    # 檢查是否可以請求
    can_request, reason = controller.can_request(test_model)
    print(f"\n模型 {test_model}：{reason}")

    if can_request:
        # 在實際應用中，這裡會調用真實的 API
        test_response = "人工智能是一種模擬人類智能的技術..."
        controller.log_request(test_model, test_prompt, test_response)
        print(f"✅ 請求已記錄")

    print(f"\n統計信息：{controller.get_stats(test_model)}")
