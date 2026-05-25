"""
自主决策引擎 - Central Nervous System (中樞神經)
智能體協作系統的核心，負責模型管理、性能監控和決策調控
"""

import json
import time
import datetime
import threading
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 添加父目录到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "core"))
sys.path.insert(0, str(PROJECT_ROOT / "learning"))

from core.constants import *
from core.utils import TimeHelper, JsonStorage
from agents.agent_communication import (
    MessageBroker,
    CollaborationContext,
    AgentRegistry,
    Message,
    EventType,
    message_broker,
    collaboration_context,
    agent_registry,
)

# 延遲導入文件系統學習器（避免循環導入）
try:
    from learning.file_system_learner import FileSystemLearner

    FILE_SYSTEM_LEARNER_AVAILABLE = True
except ImportError:
    try:
        from file_system_learner import FileSystemLearner

        FILE_SYSTEM_LEARNER_AVAILABLE = True
    except ImportError:
        FILE_SYSTEM_LEARNER_AVAILABLE = False
        print("⚠️  文件系統學習器未載入")

# 導入統一學習中樞
try:
    from core.unified_learning_hub import UnifiedLearningHub

    UNIFIED_LEARNING_HUB_AVAILABLE = True
except ImportError:
    try:
        from unified_learning_hub import UnifiedLearningHub

        UNIFIED_LEARNING_HUB_AVAILABLE = True
    except ImportError:
        UNIFIED_LEARNING_HUB_AVAILABLE = False
        print("⚠️  統一學習中樞未載入")

# 導入會話數據管理系統
try:
    from core.session_data_manager import SessionDataManager

    SESSION_DATA_MANAGER_AVAILABLE = True
except ImportError:
    try:
        from session_data_manager import SessionDataManager

        SESSION_DATA_MANAGER_AVAILABLE = True
    except ImportError:
        SESSION_DATA_MANAGER_AVAILABLE = False
        print("⚠️  會話數據管理系統未載入")

# 導入進階認知能力系統
try:
    from core.cognitive_capabilities import (
        CognitiveCapabilityManager,
        ReflectiveCapability,
        ChallengeCapability,
        ConfidenceCalibrationCapability,
        ActiveHypothesisCapability,
        FailureAnalysisCapability,
        AnalogyTransferCapability,
        ConceptExtractionCapability,
        QueryProcessingCapability,
    )

    COGNITIVE_CAPABILITIES_AVAILABLE = True
except ImportError:
    try:
        from cognitive_capabilities import CognitiveCapabilityManager

        COGNITIVE_CAPABILITIES_AVAILABLE = True
    except ImportError:
        COGNITIVE_CAPABILITIES_AVAILABLE = False
        print("⚠️  認知能力系統未載入")


class AutonomousAgent:
    """中樞神經 - 自主決策智能體，協調所有其他智能體"""

    def __init__(self):
        # 基本初始化
        self.agent_name = "central_nervous"
        self.config = self._load_config()
        self.model_health = {}  # 记录每个模型的健康状态
        self.model_performance = {}  # 记录每个模型的性能数据
        self.model_cooldown_verification = {}  # 冷却验证状态跟踪
        self._health_check_running = False  # 后台健康检查状态

        # 初始化追踪和持久化
        self._initialize_tracking()
        self._load_persisted_data()  # 加载已保存的数据

        # 註冊中樞神經
        agent_registry.register(
            self.agent_name,
            "central_nervous",
            [
                "model_selection",
                "health_monitoring",
                "decision_making",
                "coordination",
                "learning",
            ],
        )

        # 訂閱其他智能體的事件
        message_broker.subscribe(
            EventType.CODE_UPDATE_COMPLETED, self._on_code_update_completed
        )
        message_broker.subscribe(
            EventType.CODE_UPDATE_FAILED, self._on_code_update_failed
        )
        message_broker.subscribe(
            EventType.CODE_ISSUE_DETECTED, self._on_code_issue_detected
        )

        # 啟動後台健康檢查
        self._start_health_check()

        # 初始化文件系統學習器
        self.file_system_learner = None
        if FILE_SYSTEM_LEARNER_AVAILABLE:
            try:
                self.file_system_learner = FileSystemLearner()
                print("✅ 文件系統學習器已初始化")
                # 啟動後台文件系統監控
                self._start_filesystem_monitoring()
            except Exception as e:
                print(f"⚠️  文件系統學習器初始化失敗: {e}")

        # 初始化統一學習中樞
        self.unified_learning_hub = None
        if UNIFIED_LEARNING_HUB_AVAILABLE:
            try:
                self.unified_learning_hub = UnifiedLearningHub()
                print("✅ 統一學習中樞已初始化")
            except Exception as e:
                print(f"⚠️  統一學習中樞初始化失敗: {e}")

        # 初始化會話數據管理系統
        self.session_data_manager = None
        if SESSION_DATA_MANAGER_AVAILABLE:
            try:
                self.session_data_manager = SessionDataManager()
                print("✅ 會話數據管理系統已初始化")
            except Exception as e:
                print(f"⚠️  會話數據管理系統初始化失敗: {e}")

        # 初始化進階認知能力系統
        self.cognitive_manager = None
        if COGNITIVE_CAPABILITIES_AVAILABLE:
            try:
                self.cognitive_manager = CognitiveCapabilityManager()
                print("✅ 進階認知能力系統已初始化")
                print("   - 反思型能力 (Reflective)")
                print("   - 挑戰型能力 (Challenge)")
                print("   - 信心校準能力 (Confidence Calibration)")
                print("   - 主動假說能力 (Active Hypothesis)")
                print("   - 失敗分析能力 (Failure Analysis)")
                print("   - 類比遷移能力 (Analogy Transfer)")
                print("   - 概念提取能力 (Concept Extraction)")
                print("   - 查詢處理能力 (Query Processing)")
            except Exception as e:
                print(f"⚠️  認知能力系統初始化失敗: {e}")

        print(f"✅ 中樞神經 (Central Nervous System) 已初始化")

    def _load_config(self) -> dict:
        """加载配置文件"""
        default_config = {
            "auto_failover": True,  # 自动故障转移
            "smart_model_selection": True,  # 智能模型选择
            "health_check_enabled": True,  # 健康检查
            "model_priority": MODEL_PRIORITY,
            "task_type_preferences": TASK_TYPE_PREFERENCES,
            "max_failover_attempts": MAX_FAILOVER_ATTEMPTS,
            "health_check_interval": HEALTH_CHECK_INTERVAL,
            "performance_window": PERFORMANCE_WINDOW,
        }

        if AUTONOMOUS_CONFIG_FILE.exists():
            try:
                loaded_config = JsonStorage.load(AUTONOMOUS_CONFIG_FILE)
                if loaded_config:
                    default_config.update(loaded_config)
            except:
                pass
        else:
            # 创建默认配置文件
            JsonStorage.save(AUTONOMOUS_CONFIG_FILE, default_config)

        return default_config

    def _initialize_tracking(self):
        """初始化追踪数据"""
        for model in AVAILABLE_MODELS:
            self.model_health[model] = {
                "available": True,
                "last_check": None,
                "consecutive_failures": 0,
                "last_failure_time": None,
            }
            self.model_performance[model] = {
                "success_count": 0,
                "failure_count": 0,
                "total_response_time": 0.0,
                "recent_results": [],  # 最近的结果记录
            }
            self.model_cooldown_verification[model] = {
                "is_verifying": False,
                "verification_attempts": 0,
                "verification_successes": 0,
            }

    def _load_persisted_data(self):
        """加载已保存的性能和健康数据（实现持久化学习）"""
        # 加载性能数据
        saved_performance = JsonStorage.load(AGENT_PERFORMANCE_FILE, default={})
        if saved_performance:
            for model, data in saved_performance.items():
                if model in self.model_performance:
                    # 合并保存的数据（保留最近结果）
                    self.model_performance[model].update(data)

        # 加载健康数据
        saved_health = JsonStorage.load(AGENT_HEALTH_FILE, default={})
        if saved_health:
            for model, data in saved_health.items():
                if model in self.model_health:
                    self.model_health[model].update(data)

    def _save_persisted_data(self):
        """保存性能和健康数据到文件（持久化学习）"""
        JsonStorage.save(AGENT_PERFORMANCE_FILE, self.model_performance)
        JsonStorage.save(AGENT_HEALTH_FILE, self.model_health)

    def _start_health_check(self):
        """启动后台健康检查线程"""
        if not self.config.get("health_check_enabled", True):
            return

        self._health_check_running = True
        health_check_thread = threading.Thread(
            target=self._background_health_check, daemon=True
        )
        health_check_thread.start()
        print("✅ 后台健康检查已启动")

    def _background_health_check(self):
        """后台健康检查循环"""
        check_interval = self.config.get("health_check_interval", HEALTH_CHECK_INTERVAL)

        while self._health_check_running:
            try:
                time.sleep(check_interval)
                self._perform_health_check()
            except Exception as e:
                print(f"❌ 健康检查异常: {e}")

    def _perform_health_check(self):
        """执行健康检查"""
        for model in AVAILABLE_MODELS:
            try:
                # 检查模型状态
                health = self.model_health[model]
                perf = self.model_performance[model]

                # Ollama 特殊健康檢查（使用 /api/tags endpoint）
                if model == "ollama":
                    self._check_ollama_health()

                # 如果模型不可用，检查是否可以恢复
                if not health["available"]:
                    self._is_model_healthy(model)  # 这会触发验证流程

                # 更新最后检查时间
                health["last_check"] = TimeHelper.now_iso()

                # 计算并报告模型状态
                total_calls = perf["success_count"] + perf["failure_count"]
                if total_calls > 0:
                    success_rate = (perf["success_count"] / total_calls) * 100
                    status = "✅ 正常" if health["available"] else "⚠️  不可用"
                    # print(f"   {model}: {status} (成功率: {success_rate:.1f}%)")

            except Exception as e:
                print(f"❌ 检查 {model} 失败: {e}")

        # 保存更新的状态
        self._save_persisted_data()

    def _check_ollama_health(self):
        """專門檢查 Ollama 服務健康狀況（使用 /api/tags endpoint）"""
        import requests

        try:
            # 使用 tags endpoint 檢查 Ollama 服務狀態
            health_url = DEFAULT_OLLAMA_HEALTH_URL
            response = requests.get(
                health_url, timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_TIMEOUT)
            )

            if response.status_code == 200:
                # Ollama 服務正常運行
                if not self.model_health["ollama"]["available"]:
                    print(f"✅ Ollama 服務已恢復正常")
                    self.model_health["ollama"]["available"] = True
                    self.model_health["ollama"]["consecutive_failures"] = 0
                return True
            else:
                return False

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            # 連線失敗時不立即標記為不可用（可能是暫時的）
            if (
                self.model_health["ollama"]["consecutive_failures"]
                < CONSECUTIVE_FAILURE_THRESHOLD
            ):
                # 只記錄警告，不立即標記為不健康
                pass
            return False
        except Exception as e:
            return False

    def stop_health_check(self):
        """停止后台健康检查"""
        self._health_check_running = False
        print("🛑 后台健康检查已停止")

    def _start_filesystem_monitoring(self):
        """啟動後台文件系統監控"""
        if not self.file_system_learner:
            return

        self._filesystem_monitoring_running = True

        # 立即執行一次掃描
        try:
            print("🔍 執行初始文件系統掃描...")
            self.file_system_learner.scan_filesystem(deep_scan=False)
        except Exception as e:
            print(f"⚠️  初始掃描失敗: {e}")

        # 啟動後台監控線程
        monitoring_thread = threading.Thread(
            target=self._background_filesystem_monitoring, daemon=True
        )
        monitoring_thread.start()
        print("✅ 文件系統監控已啟動（每10分鐘掃描一次）")

    def _background_filesystem_monitoring(self):
        """後台文件系統監控循環"""
        # 每10分鐘掃描一次
        scan_interval = 600  # 10分鐘

        while getattr(self, "_filesystem_monitoring_running", False):
            try:
                time.sleep(scan_interval)

                if self.file_system_learner:
                    print("\n🔍 定期文件系統掃描開始...")
                    results = self.file_system_learner.scan_filesystem(deep_scan=False)

                    # 如果發現需要清理的文件，發送通知
                    if results["cleanup_candidates"]:
                        self._notify_cleanup_needed(results["cleanup_candidates"])

                    # 發佈學習更新事件
                    message_broker.publish(
                        Message(
                            sender=self.agent_name,
                            receiver="all",
                            event_type=EventType.LEARNING_UPDATED,
                            data={"update_type": "filesystem_scan", "results": results},
                            priority=5,
                        )
                    )

            except Exception as e:
                print(f"❌ 文件系統監控異常: {e}")

    def _notify_cleanup_needed(self, cleanup_candidates: List):
        """通知需要清理的文件"""
        if len(cleanup_candidates) > 5:
            print(f"\n⚠️  發現 {len(cleanup_candidates)} 個文件需要清理")
            print(f"   運行 'python file_system_learner.py --cleanup' 查看詳情")

    def perform_filesystem_scan(self, deep_scan: bool = False):
        """手動執行文件系統掃描"""
        if not self.file_system_learner:
            print("⚠️  文件系統學習器未初始化")
            return None

        return self.file_system_learner.scan_filesystem(deep_scan=deep_scan)

    def get_filesystem_insights(self):
        """獲取文件系統洞察"""
        if not self.file_system_learner:
            print("⚠️  文件系統學習器未初始化")
            return None

        return self.file_system_learner.get_file_insights()

    def auto_cleanup_filesystem(self, dry_run: bool = True):
        """自動清理文件系統"""
        if not self.file_system_learner:
            print("⚠️  文件系統學習器未初始化")
            return None

        return self.file_system_learner.auto_cleanup(dry_run=dry_run)

    def decide_best_model(
        self, prompt: str, preferred_model: Optional[str] = None
    ) -> str:
        """
        智能决策：选择最佳模型（改进版 - 基于性能评分）

        Args:
            prompt: 用户的提示词
            preferred_model: 用户偏好的模型（可选）

        Returns:
            选择的模型名称
        """
        # 如果智能选择未启用，返回偏好模型或默认模型
        if not self.config.get("smart_model_selection", True):
            return preferred_model or "ollama"

        # 检测任务类型
        task_type = self._detect_task_type(prompt)

        # 获取该任务类型的推荐模型列表
        recommended_models = self.config["task_type_preferences"].get(
            task_type, self.config["task_type_preferences"]["default"]
        )

        # 如果用户有偏好且模型健康，优先使用
        if preferred_model and self._is_model_healthy(preferred_model):
            return preferred_model

        # 从推荐模型中选择性能最好的健康模型
        healthy_models = [m for m in recommended_models if self._is_model_healthy(m)]

        if healthy_models:
            # 按性能评分排序，选择最佳
            best_model = self._select_best_model_by_score(healthy_models)
            return best_model

        # 如果所有推荐模型都不健康，选择任意健康的模型
        healthy_any = [
            m for m in self.config["model_priority"] if self._is_model_healthy(m)
        ]
        if healthy_any:
            best_model = self._select_best_model_by_score(healthy_any)
            print(f"\n⚠️  推荐模型不可用，自动切换到 {best_model}")
            return best_model

        # 如果所有模型都不健康，返回默认模型（让其失败并记录）
        print("\n⚠️  警告：所有模型可能都不可用，尝试使用默认模型")
        return preferred_model or "ollama"

    def _select_best_model_by_score(self, models: List[str]) -> str:
        """基于性能评分选择最佳模型"""
        scores = {model: self._calculate_model_score(model) for model in models}
        return max(scores, key=scores.get)

    def _calculate_model_score(self, model: str) -> float:
        """
        计算模型的综合性能评分
        基于多个指标：成功率、响应速度、稳定性、近期表现
        """
        perf = self.model_performance[model]

        # 1. 成功率（0-100分）
        total = perf["success_count"] + perf["failure_count"]
        success_rate_score = (perf["success_count"] / total * 100) if total > 0 else 0

        # 2. 响应速度（平均响应时间越短越好）
        avg_response_time = (
            (perf["total_response_time"] / perf["success_count"])
            if perf["success_count"] > 0
            else DEFAULT_TIMEOUT
        )
        response_time_score = max(0, 100 - (avg_response_time / DEFAULT_TIMEOUT * 100))

        # 3. 稳定性（方差越小越稳定）
        stability_score = self._calculate_stability_score(model)

        # 4. 近期表现（最近结果的权重更高）
        recency_score = self._calculate_recency_score(model)

        # 综合评分（加权平均）
        weights = MODEL_SCORING_WEIGHTS
        composite_score = (
            success_rate_score * weights["success_rate"] / 100
            + response_time_score * weights["response_time"] / 100
            + stability_score * weights["consistency"] / 100
            + recency_score * weights["recency"] / 100
        )

        return composite_score

    def _calculate_stability_score(self, model: str) -> float:
        """计算模型的稳定性评分（基于结果的一致性）"""
        recent = self.model_performance[model]["recent_results"]
        if not recent:
            return 50  # 默认中等稳定性

        # 计算最近30条结果的成功率变异
        recent_30 = recent[-30:]
        successes = sum(1 for r in recent_30 if r.get("success", False))
        stability = (successes / len(recent_30)) * 100 if recent_30 else 0

        return stability

    def _calculate_recency_score(self, model: str) -> float:
        """计算最近表现评分（最近的结果权重更高）"""
        recent = self.model_performance[model]["recent_results"]
        if not recent:
            return 50  # 默认中等评分

        # 最近10条结果的成功率
        recent_10 = recent[-10:]
        recent_success = sum(1 for r in recent_10 if r.get("success", False))
        recent_score = (recent_success / len(recent_10)) * 100 if recent_10 else 0

        return recent_score

    def _detect_task_type(self, prompt: str) -> str:
        """检测任务类型"""
        prompt_lower = prompt.lower()

        # 代码相关关键词
        code_keywords = [
            "代码",
            "code",
            "程序",
            "program",
            "函数",
            "function",
            "bug",
            "错误",
            "python",
            "javascript",
            "java",
            "编程",
            "programming",
            "算法",
            "algorithm",
        ]
        # 创意相关关键词
        creative_keywords = [
            "故事",
            "story",
            "诗",
            "poem",
            "创意",
            "creative",
            "写作",
            "writing",
            "小说",
            "novel",
            "歌词",
            "lyrics",
            "想象",
            "imagine",
        ]
        # 分析相关关键词
        analysis_keywords = [
            "分析",
            "analysis",
            "评估",
            "evaluate",
            "比较",
            "compare",
            "总结",
            "summarize",
            "数据",
            "data",
            "统计",
            "statistics",
        ]

        if any(keyword in prompt_lower for keyword in code_keywords):
            return "code"
        elif any(keyword in prompt_lower for keyword in creative_keywords):
            return "creative"
        elif any(keyword in prompt_lower for keyword in analysis_keywords):
            return "analysis"
        else:
            return "conversation"

    def _verify_model_recovery(self, model: str) -> bool:
        """
        验证模型是否已经恢复（冷却验证机制）

        冷却时间满足后，通过实际验证确认模型是否真正恢复
        而不仅仅依赖时间计算
        """
        if model not in self.model_cooldown_verification:
            self.model_cooldown_verification[model] = {
                "is_verifying": False,
                "verification_attempts": 0,
                "verification_passed": 0,
            }

        verification_state = self.model_cooldown_verification[model]

        # 如果还没有开始验证，标记开始
        if not verification_state["is_verifying"]:
            verification_state["is_verifying"] = True
            verification_state["verification_attempts"] = 0
            verification_state["verification_passed"] = 0
            print(f"\n🔍 开始验证 {model} 的恢复状态...")
            return False  # 第一次验证，返回 False 让系统重试

        # 统计验证进度
        verification_attempts = verification_state["verification_attempts"]
        verification_passed = verification_state["verification_passed"]
        required_attempts = COOLDOWN_VERIFICATION_ATTEMPTS
        required_success_rate = COOLDOWN_VERIFICATION_THRESHOLD

        # 如果验证尝试已完成
        if verification_attempts >= required_attempts:
            success_rate = (verification_passed / required_attempts) * 100

            if success_rate >= required_success_rate:
                # 验证通过 - 模型恢复
                self.model_health[model]["consecutive_failures"] = 0
                self.model_health[model]["available"] = True
                verification_state["is_verifying"] = False
                print(
                    f"\n✅ {model} 验证通过 ({verification_passed}/{required_attempts} 成功)，标记为可用"
                )
                self._save_persisted_data()
                return True
            else:
                # 验证失败 - 模型未恢复，延长冷却
                self.model_health[model]["last_failure_time"] = TimeHelper.now_iso()
                verification_state["is_verifying"] = False
                print(
                    f"\n❌ {model} 验证失败 ({verification_passed}/{required_attempts} 成功)，延长冷却"
                )
                self._save_persisted_data()
                return False

        # 验证还在进行中
        return False

    def record_verification_attempt(self, model: str, success: bool):
        """记录冷却验证尝试的结果"""
        if model not in self.model_cooldown_verification:
            return

        state = self.model_cooldown_verification[model]
        if not state.get("is_verifying", False):
            return

        state["verification_attempts"] += 1
        if success:
            state["verification_passed"] += 1

        print(
            f"   验证进度: {state['verification_passed']}/{state['verification_attempts']}"
        )

    def _detect_error_type(self, error_message: str) -> str:
        """
        自动检测错误类型
        """
        error_lower = error_message.lower()

        # 检查各种错误类型
        if any(
            kw in error_lower
            for kw in ["connection", "连接", "network", "网络", "refused", "拒绝"]
        ):
            return "connection_error"
        elif any(
            kw in error_lower
            for kw in ["config", "配置", "invalid", "无效", "key", "密钥"]
        ):
            return "config_error"
        elif any(
            kw in error_lower
            for kw in ["rate", "limit", "限流", "quota", "配额", "太多"]
        ):
            return "rate_limit_error"
        elif any(kw in error_lower for kw in ["timeout", "超时", "timed out"]):
            return "timeout_error"
        elif any(
            kw in error_lower for kw in ["api", "error", "错误", "failed", "失败"]
        ):
            return "api_error"
        else:
            return "unknown_error"

    def _get_cooldown_multiplier(
        self, error_type: str, consecutive_failures: int
    ) -> float:
        """
        根据错误类型和连续失败次数计算冷却时间倍数
        """
        base_multiplier = 1.0

        if error_type == "connection_error":
            # 连接错误：快速重试（较短冷却）
            base_multiplier = 0.5
        elif error_type == "config_error":
            # 配置错误：永久失败（跳过重试）
            base_multiplier = float("inf")  # 实际上配置错误不应该重试
        elif error_type == "rate_limit_error":
            # 限流错误：长时间冷却，指数退避
            base_multiplier = 2.0 ** min(consecutive_failures, 4)  # 最多4倍指数
        elif error_type == "timeout_error":
            # 超时错误：逐步增加冷却
            base_multiplier = 1.0 + (consecutive_failures * 0.5)
        else:
            # 未知或 API 错误：标准冷却
            base_multiplier = 1.0

        return base_multiplier

    def _is_model_healthy(self, model: str) -> bool:
        """检查模型是否健康"""
        health = self.model_health.get(model, {})

        # 如果模型标记为可用，直接返回
        if health.get("available", True):
            return True

        # 模型不可用，检查冷却时间
        last_failure = health.get("last_failure_time")
        if not last_failure:
            return False

        time_since_failure = TimeHelper.elapsed_since(last_failure)

        # 冷却时间未满，模型仍不可用
        if time_since_failure < COOLDOWN_SECONDS:
            return False

        # 冷却时间已满，开始验证流程（而不是直接恢复）
        # 需要进行恢复验证以确保模型真正恢复
        return self._verify_model_recovery(model)

    def auto_failover(
        self, failed_model: str, prompt: str, original_error: str
    ) -> Optional[Tuple[str, str]]:
        """
        自动故障转移：当模型失败时，自动切换到备用模型

        Args:
            failed_model: 失败的模型
            prompt: 原始提示词
            original_error: 原始错误信息

        Returns:
            (备用模型名称, "failover") 或 None
        """
        if not self.config.get("auto_failover", True):
            return None

        # 记录失败
        self.record_failure(failed_model, original_error)

        # 获取备用模型列表（排除已失败的模型）
        all_models = self.config["model_priority"]
        backup_models = [
            m for m in all_models if m != failed_model and self._is_model_healthy(m)
        ]

        if not backup_models:
            print(f"\n❌ 自动故障转移失败：没有可用的备用模型")
            return None

        # 选择性能最好的备用模型（而不是第一个）
        backup_model = self._select_best_model_by_score(backup_models)

        print(f"\n🔄 自动故障转移：{failed_model} → {backup_model}")
        print(f"   原因：{original_error[:100]}")

        return (backup_model, "failover")

    def record_success(self, model: str, response_time: float = 0.0):
        """记录成功调用"""
        # 更新健康状态
        self.model_health[model]["consecutive_failures"] = 0
        self.model_health[model]["available"] = True

        # 更新性能数据
        perf = self.model_performance[model]
        perf["success_count"] += 1
        perf["total_response_time"] += response_time

        # 记录最近的结果
        perf["recent_results"].append(
            {
                "success": True,
                "timestamp": TimeHelper.now_iso(),
                "response_time": response_time,
            }
        )

        # 保持最近N条记录
        window = self.config.get("performance_window", PERFORMANCE_WINDOW)
        if len(perf["recent_results"]) > window:
            perf["recent_results"] = perf["recent_results"][-window:]

        # 持久化保存性能数据（实现跨会话学习）
        self._save_persisted_data()

    def record_failure(self, model: str, error_message: str, error_type: str = None):
        """
        记录失败调用

        根据错误类型采取不同的处理策略：
        - 连接错误：快速重试
        - 配置错误：跳过重试（永久失败）
        - 限流错误：长时间冷却，指数退避
        - 超时错误：逐步增加冷却时间
        - 未知错误：标准处理
        """
        # 自动检测错误类型如果未指定
        if not error_type:
            error_type = self._detect_error_type(error_message)

        # 更新健康状态
        health = self.model_health[model]
        health["consecutive_failures"] += 1
        health["last_failure_time"] = TimeHelper.now_iso()

        # 根据错误类型调整冷却策略
        cooldown_multiplier = self._get_cooldown_multiplier(
            error_type, health["consecutive_failures"]
        )
        health["cooldown_multiplier"] = cooldown_multiplier

        # 如果连续失败超过阈值，标记为不可用
        if health["consecutive_failures"] >= CONSECUTIVE_FAILURE_THRESHOLD:
            health["available"] = False
            warning_msg = (
                f"\n⚠️  警告：{model} 连续失败 {health['consecutive_failures']} 次"
            )

            if error_type == "config_error":
                warning_msg += "（配置错误，跳过重试）"
            elif error_type == "rate_limit_error":
                warning_msg += "（限流，需要长时间冷卻）"

            print(warning_msg + f"，暂时标记为不可用")

            # 發佈健康下降事件，通知其他智能體
            message_broker.publish(
                Message(
                    sender=self.agent_name,
                    receiver="all",
                    event_type=EventType.HEALTH_DEGRADED,
                    data={
                        "model": model,
                        "error_type": error_type,
                        "consecutive_failures": health["consecutive_failures"],
                        "cooldown_multiplier": cooldown_multiplier,
                    },
                    priority=8,
                )
            )

        # 更新性能数据
        perf = self.model_performance[model]
        perf["failure_count"] += 1

        # 记录最近的结果（包含错误分类信息）
        perf["recent_results"].append(
            {
                "success": False,
                "timestamp": TimeHelper.now_iso(),
                "error": error_message[:200],
                "error_type": error_type,
            }
        )

        # 保持最近N条记录
        window = self.config.get("performance_window", PERFORMANCE_WINDOW)
        if len(perf["recent_results"]) > window:
            perf["recent_results"] = perf["recent_results"][-window:]

        # 持久化保存性能数据（实现跨会话学习）
        self._save_persisted_data()

    def get_model_statistics(self) -> dict:
        """获取所有模型的统计信息"""
        stats = {}
        for model in ["ollama", "openai", "gemini", "xai"]:
            perf = self.model_performance[model]
            health = self.model_health[model]

            total_calls = perf["success_count"] + perf["failure_count"]
            success_rate = (
                (perf["success_count"] / total_calls * 100) if total_calls > 0 else 0
            )
            avg_response_time = (
                (perf["total_response_time"] / perf["success_count"])
                if perf["success_count"] > 0
                else 0
            )

            stats[model] = {
                "健康状态": "✅ 正常" if health["available"] else "❌ 不可用",
                "连续失败": health["consecutive_failures"],
                "成功次数": perf["success_count"],
                "失败次数": perf["failure_count"],
                "成功率": f"{success_rate:.1f}%",
                "平均响应时间": f"{avg_response_time:.2f}秒"
                if avg_response_time > 0
                else "N/A",
            }

        return stats

    def health_check(self) -> dict:
        """执行健康检查（可以定期调用）"""
        results = {}
        for model in ["ollama", "openai", "gemini", "claude", "xai"]:
            health = self.model_health[model]
            results[model] = {
                "healthy": self._is_model_healthy(model),
                "consecutive_failures": health["consecutive_failures"],
                "last_failure": health.get("last_failure_time", "从未失败"),
            }
        return results

    def reset_model_health(self, model: str):
        """重置模型健康状态（手动修复后可调用）"""
        self.model_health[model]["consecutive_failures"] = 0
        self.model_health[model]["available"] = True
        self.model_health[model]["last_failure_time"] = None
        print(f"\n✅ {model} 的健康状态已重置")

    def submit_feedback(
        self, model: str, quality_score: float, response_id: str = None
    ):
        """
        提交对模型响应的反馈（改进基于反馈的学习）

        Args:
            model: 模型名称
            quality_score: 质量评分（0-100），100表示非常满意，0表示非常不满意
            response_id: 响应ID（用于追踪反馈和响应的对应关系）
        """
        if model not in self.model_performance:
            return

        # 确保分数在有效范围内
        quality_score = max(0, min(100, quality_score))

        # 初始化反馈数据结构
        if "feedback" not in self.model_performance[model]:
            self.model_performance[model]["feedback"] = {
                "total_score": 0,
                "feedback_count": 0,
                "recent_feedback": [],
            }

        feedback_data = self.model_performance[model]["feedback"]

        # 记录反馈
        feedback_entry = {
            "timestamp": TimeHelper.now_iso(),
            "score": quality_score,
            "response_id": response_id,
        }

        feedback_data["recent_feedback"].append(feedback_entry)
        feedback_data["total_score"] += quality_score
        feedback_data["feedback_count"] += 1

        # 保持最近feedback数量
        if len(feedback_data["recent_feedback"]) > 100:
            feedback_data["recent_feedback"] = feedback_data["recent_feedback"][-100:]

        # 计算平均反馈评分
        avg_feedback = feedback_data["total_score"] / feedback_data["feedback_count"]

        print(
            f"\n📊 {model} 获得反馈评分: {quality_score}/100 (平均: {avg_feedback:.1f}/100)"
        )

        # 持久化保存
        self._save_persisted_data()

    def get_feedback_statistics(self, model: str = None) -> dict:
        """
        获取模型的反馈统计信息

        Args:
            model: 模型名称，如果为None则返回所有模型的统计

        Returns:
            反馈统计数据
        """
        stats = {}

        models_to_check = [model] if model else AVAILABLE_MODELS

        for m in models_to_check:
            if m not in self.model_performance:
                continue

            perf = self.model_performance[m]
            feedback = perf.get("feedback", {})

            if feedback.get("feedback_count", 0) == 0:
                stats[m] = {"has_feedback": False, "message": "暂无反馈数据"}
            else:
                avg_score = feedback["total_score"] / feedback["feedback_count"]
                recent_feedback = feedback.get("recent_feedback", [])
                recent_10 = recent_feedback[-10:]
                recent_avg = (
                    sum(f["score"] for f in recent_10) / len(recent_10)
                    if recent_10
                    else 0
                )

                stats[m] = {
                    "has_feedback": True,
                    "总反馈次数": feedback["feedback_count"],
                    "平均评分": f"{avg_score:.1f}/100",
                    "近期评分": f"{recent_avg:.1f}/100",
                    "质量等级": self._rate_quality(avg_score),
                }

        return stats

    def _rate_quality(self, score: float) -> str:
        """根据评分给出质量等级"""
        if score >= 85:
            return "🟢 优秀"
        elif score >= 70:
            return "🟡 良好"
        elif score >= 50:
            return "🟠 中等"
        elif score >= 30:
            return "🔴 较差"
        else:
            return "⚫ 很差"

    def adjust_model_selection_by_feedback(self):
        """
        根据反馈数据调整模型选择策略
        （这个方法可以被定期调用来优化task_type_preferences）
        """
        for task_type in self.config.get("task_type_preferences", {}).keys():
            if task_type == "default":
                continue

            # 获取该任务类型的推荐模型
            preferred = self.config["task_type_preferences"][task_type]

            # 计算每个模型的综合评分（包括反馈）
            scores = {}
            for model in preferred:
                perf_score = self._calculate_model_score(model)

                # 获取反馈评分
                feedback = self.model_performance[model].get("feedback", {})
                feedback_score = (
                    feedback.get("total_score", 0) / feedback.get("feedback_count", 1)
                    if feedback.get("feedback_count", 0) > 0
                    else 50
                )

                # 综合评分（70% 性能 + 30% 反馈）
                combined_score = (perf_score * 0.7) + (feedback_score * 0.3)
                scores[model] = combined_score

            # 重新排序推荐模型
            if scores:
                sorted_models = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                new_preference = [m for m, _ in sorted_models]

                if new_preference != preferred:
                    old_pref = " > ".join(preferred)
                    new_pref = " > ".join(new_preference)
                    print(f"\n🔄 {task_type} 任务优选顺序已更新:")
                    print(f"   原: {old_pref}")
                    print(f"   新: {new_pref}")

                    self.config["task_type_preferences"][task_type] = new_preference
                    JsonStorage.save(AUTONOMOUS_CONFIG_FILE, self.config)

    # ============ 智能體協作方法 ============

    def _on_code_update_completed(self, message: Message):
        """處理代碼更新完成事件"""
        print(f"\n✅ 代碼更新智能體: 更新成功")
        print(f"   {message.data.get('result')}")

        # 更新協作上下文
        collaboration_context.update_shared_insight(
            {
                "from_agent": self.agent_name,
                "event": "code_update_success",
                "update_info": message.data,
            }
        )

        # 發佈學習更新事件
        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="all",
                event_type=EventType.LEARNING_UPDATED,
                data={"update_type": "code_improvement"},
                priority=7,
            )
        )

        # 更新自己的狀態
        agent_registry.update_activity(self.agent_name)

    def _on_code_update_failed(self, message: Message):
        """處理代碼更新失敗事件"""
        print(f"\n❌ 代碼更新智能體: 更新失敗")
        print(f"   {message.data.get('result')}")

        collaboration_context.update_shared_insight(
            {
                "from_agent": self.agent_name,
                "event": "code_update_failed",
                "error_info": message.data,
            }
        )

    def _on_code_issue_detected(self, message: Message):
        """處理代碼問題檢測事件"""
        print(f"\n🔍 代碼更新智能體: 檢測到 {message.data.get('issues_found')} 個問題")

        # 根據问题数量决定是否主动要求更新
        if message.data.get("issues_found", 0) >= 5:
            print(f"   → 問題數量較多，建議進行代碼優化")

            message_broker.publish(
                Message(
                    sender=self.agent_name,
                    receiver="code_updater",
                    event_type=EventType.CODE_UPDATE_REQUESTED,
                    data={"auto_generated": True},
                    priority=6,
                )
            )

    def request_code_analysis(self):
        """請求代碼更新智能體進行代碼分析"""
        print(f"\n📋 中樞神經發起代碼分析請求...")

        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="code_updater",
                event_type=EventType.CODE_UPDATE_REQUESTED,
                data={
                    "request_type": "analyze_code",
                    "target_files": None,  # None 表示分析所有文件
                },
                priority=5,
            )
        )

    def request_code_improvement(self, specific_issues: List[str] = None):
        """請求代碼改進"""
        print(f"\n🔧 中樞神經發起代碼改進請求...")

        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="code_updater",
                event_type=EventType.CODE_UPDATE_REQUESTED,
                data={
                    "request_type": "improve_code",
                    "specific_issues": specific_issues,
                },
                priority=6,
            )
        )

    def share_learning_insights(self):
        """與協作上下文共享學習洞察"""
        insights = {"model_scores": {}, "performance_trends": {}, "health_summary": {}}

        # 收集每個模型的評分
        for model in AVAILABLE_MODELS:
            insights["model_scores"][model] = self._calculate_model_score(model)

        # 收集健康摘要
        for model in AVAILABLE_MODELS:
            health = self.model_health[model]
            perf = self.model_performance[model]
            total = perf["success_count"] + perf["failure_count"]

            insights["health_summary"][model] = {
                "available": health["available"],
                "success_rate": f"{(perf['success_count'] / total * 100):.1f}%"
                if total > 0
                else "N/A",
                "consecutive_failures": health["consecutive_failures"],
            }

        collaboration_context.update_shared_insight(
            {"from_agent": self.agent_name, "learning_data": insights}
        )

    def get_collaboration_status(self) -> Dict:
        """獲取協作系統的狀態"""
        status = {
            "central_nervous": {
                "status": "active",
                "coordinating_agents": agent_registry.list_agents(),
            },
            "message_queue": {
                "pending_messages": len(message_broker.message_queue),
                "total_history": len(message_broker.message_history),
            },
            "collaboration_insights": len(collaboration_context.get_all_insights()),
            "pending_suggestions": len(collaboration_context.get_pending_suggestions()),
        }

        return status

    def get_comprehensive_learning_insights(self) -> Dict:
        """獲取全面的學習洞察（整合所有數據源）"""
        if self.unified_learning_hub:
            return self.unified_learning_hub.get_comprehensive_insights()
        else:
            return {
                "error": "統一學習中樞未初始化",
                "fallback_data": {
                    "model_performance": self.model_performance,
                    "model_health": self.model_health,
                },
            }

    def generate_learning_report(self) -> str:
        """生成全面的學習報告"""
        if self.unified_learning_hub:
            return self.unified_learning_hub.generate_learning_report()
        else:
            return "⚠️  統一學習中樞未初始化，無法生成報告"

    def get_system_recommendations(self) -> List[Dict]:
        """獲取系統優化建議"""
        if self.unified_learning_hub:
            insights = self.unified_learning_hub.get_comprehensive_insights()
            return insights.get("recommendations", [])
        return []

    # ===== 會話數據管理方法 =====

    def record_conversation_session(
        self, user_message: str, ai_response: str, context: Optional[Dict] = None
    ) -> Optional[str]:
        """記錄對話會話"""
        if self.session_data_manager:
            return self.session_data_manager.record_conversation(
                user_message, ai_response, context
            )
        return None

    def get_session_verification_status(self) -> Dict:
        """獲取會話驗證狀態"""
        if self.session_data_manager:
            return self.session_data_manager.get_verification_status()
        return {"error": "會話數據管理系統未初始化"}

    def analyze_and_cleanup_trash_data(self, dry_run: bool = True) -> Dict:
        """分析和清理廢棄數據（按文件夾分類）"""
        if self.session_data_manager:
            return self.session_data_manager.analyze_and_cleanup_trash(dry_run)
        return {"error": "會話數據管理系統未初始化"}

    def get_cleanup_recommendations(self) -> Dict:
        """獲取按文件夾分類的清理建議"""
        if self.session_data_manager:
            return self.session_data_manager.get_cleanup_recommendations_by_folder()
        return {"error": "會話數據管理系統未初始化"}

    def generate_data_management_report(self) -> str:
        """生成數據管理報告"""
        if self.session_data_manager:
            return self.session_data_manager.generate_management_report()
        return "⚠️  會話數據管理系統未初始化"

    # ===== 進階認知能力方法 =====

    def reflect_on_decision(
        self, decision: str, outcome: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        反思決策的質量和結果

        Args:
            decision: 所做的決策
            outcome: 決策的結果
            context: 決策時的上下文

        Returns:
            反思結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.reflective.reflect_on_decision(
            decision, outcome, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "quality_score": result.output_data.get("quality_score"),
            "lessons_learned": result.output_data.get("lessons_learned"),
            "improvements": result.output_data.get("improvements"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def challenge_assumption(
        self, assumption: str, evidence: List[str], context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        挑戰某個假設的合理性

        Args:
            assumption: 要挑戰的假設
            evidence: 支持該假設的證據
            context: 上下文信息

        Returns:
            挑戰結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.challenge.challenge_assumption(
            assumption, evidence, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "strength": result.output_data.get("strength"),
            "counter_examples": result.output_data.get("counter_examples"),
            "challenges": result.output_data.get("challenges"),
            "should_revise": result.output_data.get("should_revise"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def calibrate_confidence(
        self,
        prediction: str,
        initial_confidence: float,
        supporting_factors: List[str],
        uncertainty_factors: List[str],
    ) -> Dict[str, Any]:
        """
        校準信心水平

        Args:
            prediction: 預測或判斷
            initial_confidence: 初始信心水平 (0-1)
            supporting_factors: 支持因素
            uncertainty_factors: 不確定因素

        Returns:
            校準後的信心結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.confidence_calibration.calibrate_confidence(
            prediction, initial_confidence, supporting_factors, uncertainty_factors
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "initial_confidence": initial_confidence,
            "calibrated_confidence": result.output_data.get("calibrated_confidence"),
            "confidence_level": result.output_data.get("confidence_level"),
            "adjustment": result.output_data.get("adjustment"),
            "reasoning": result.reasoning,
        }

    def generate_hypotheses(
        self, observation: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        基於觀察生成假說

        Args:
            observation: 觀察到的現象
            context: 上下文信息

        Returns:
            假說生成結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.active_hypothesis.generate_hypotheses(
            observation, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "hypotheses": result.output_data.get("hypotheses"),
            "ranked_hypotheses": result.output_data.get("ranked_hypotheses"),
            "verification_plans": result.output_data.get("verification_plans"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def analyze_failure_with_cognition(
        self, failure_event: Dict[str, Any], historical_failures: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        使用認知能力深度分析失敗事件

        Args:
            failure_event: 失敗事件詳情
            historical_failures: 歷史失敗記錄

        Returns:
            失敗分析結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.failure_analysis.analyze_failure(
            failure_event, historical_failures
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "failure_type": result.output_data.get("failure_type"),
            "root_causes": result.output_data.get("root_causes"),
            "similar_patterns": result.output_data.get("similar_patterns"),
            "preventive_measures": result.output_data.get("preventive_measures"),
            "severity": result.output_data.get("severity"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def transfer_knowledge(
        self,
        source_domain: str,
        target_domain: str,
        source_solution: str,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        將知識從源領域遷移到目標領域

        Args:
            source_domain: 源領域
            target_domain: 目標領域
            source_solution: 源領域的解決方案
            context: 上下文信息

        Returns:
            知識遷移結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.analogy_transfer.transfer_knowledge(
            source_domain, target_domain, source_solution, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "similarities": result.output_data.get("similarities"),
            "adapted_solution": result.output_data.get("adapted_solution"),
            "pitfalls": result.output_data.get("pitfalls"),
            "transferability": result.output_data.get("transferability"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def extract_concepts(
        self, examples: List[Dict[str, Any]], context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        從實例中提取概念

        Args:
            examples: 具體實例列表
            context: 上下文信息

        Returns:
            概念提取結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.concept_extraction.extract_concepts(
            examples, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "common_patterns": result.output_data.get("common_patterns"),
            "core_concepts": result.output_data.get("core_concepts"),
            "concept_hierarchy": result.output_data.get("concept_hierarchy"),
            "concept_definitions": result.output_data.get("concept_definitions"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def process_temporal_query(
        self, query: str, time_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        處理時效性查詢

        Args:
            query: 查詢內容
            time_context: 時間上下文

        Returns:
            查詢處理結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.query_processing.process_temporal_query(
            query, time_context
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "is_time_sensitive": result.output_data.get("is_time_sensitive"),
            "time_constraints": result.output_data.get("time_constraints"),
            "data_freshness": result.output_data.get("data_freshness"),
            "requires_update": result.output_data.get("requires_update"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def process_gap_filling_query(
        self, known_data: Dict[str, Any], missing_fields: List[str]
    ) -> Dict[str, Any]:
        """
        處理缺口填補型查詢

        Args:
            known_data: 已知數據
            missing_fields: 缺失字段

        Returns:
            缺口填補結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.query_processing.process_gap_filling_query(
            known_data, missing_fields
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "inferred_values": result.output_data.get("inferred_values"),
            "inference_confidence": result.output_data.get("inference_confidence"),
            "needs_more_info": result.output_data.get("needs_more_info"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def process_verification_query(
        self, claim: str, evidence: List[str], context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        處理驗證式查詢

        Args:
            claim: 待驗證的聲明
            evidence: 證據列表
            context: 上下文

        Returns:
            驗證結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.query_processing.process_verification_query(
            claim, evidence, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "is_verified": result.output_data.get("is_verified"),
            "support_score": result.output_data.get("support_score"),
            "contradictions": result.output_data.get("contradictions"),
            "confidence_level": result.output_data.get("confidence_level"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def process_decomposition_query(
        self, complex_query: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        處理分解式查詢 - 將複雜查詢分解為子問題

        Args:
            complex_query: 複雜查詢
            context: 上下文

        Returns:
            分解結果
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        result = self.cognitive_manager.query_processing.process_decomposition_query(
            complex_query, context or {}
        )

        self.cognitive_manager.log_capability_usage(result)

        return {
            "capability": result.capability_type,
            "query_components": result.output_data.get("query_components"),
            "sub_queries": result.output_data.get("sub_queries"),
            "dependencies": result.output_data.get("dependencies"),
            "execution_plan": result.output_data.get("execution_plan"),
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

    def get_cognitive_usage_statistics(self) -> Dict[str, Any]:
        """
        獲取認知能力使用統計

        Returns:
            使用統計數據
        """
        if not self.cognitive_manager:
            return {"error": "認知能力系統未初始化"}

        return self.cognitive_manager.get_usage_statistics()

    def enhanced_failure_handling(
        self, model: str, error_message: str, error_type: str = None
    ):
        """
        增強的失敗處理 - 整合認知能力

        Args:
            model: 模型名稱
            error_message: 錯誤訊息
            error_type: 錯誤類型
        """
        # 標準失敗記錄
        self.record_failure(model, error_message, error_type)

        # 使用認知能力進行深度分析
        if self.cognitive_manager:
            failure_event = {
                "model": model,
                "error_message": error_message,
                "error_type": error_type or self._detect_error_type(error_message),
                "timestamp": TimeHelper.now_iso(),
                "consecutive_failures": self.model_health[model][
                    "consecutive_failures"
                ],
            }

            # 執行失敗分析
            analysis = self.analyze_failure_with_cognition(
                failure_event,
                historical_failures=self.model_performance[model].get(
                    "recent_results", []
                ),
            )

            # 生成假說
            hypotheses = self.generate_hypotheses(
                observation=f"{model} 發生 {error_type or '未知'} 錯誤: {error_message[:100]}",
                context={"model": model, "error_type": error_type},
            )

            # 反思決策（如果有最近的模型切換決策）
            if hasattr(self, "_last_model_decision"):
                self.reflect_on_decision(
                    decision=f"選擇使用 {model}",
                    outcome=f"失敗: {error_message[:50]}",
                    context={"model": model, "error_type": error_type},
                )

            # 記錄增強分析結果
            print(f"\n🧠 認知能力分析:")
            print(f"   失敗類型: {analysis.get('failure_type', '未知')}")
            print(f"   根本原因: {', '.join(analysis.get('root_causes', [])[:2])}")
            print(f"   優先假說: {hypotheses.get('ranked_hypotheses', ['無'])[0]}")

            # 發佈增強學習事件
            message_broker.publish(
                Message(
                    sender=self.agent_name,
                    receiver="all",
                    event_type=EventType.LEARNING_UPDATED,
                    data={
                        "update_type": "cognitive_failure_analysis",
                        "analysis": analysis,
                        "hypotheses": hypotheses,
                    },
                    priority=8,
                )
            )


# 全局中樞神經實例
autonomous_agent = AutonomousAgent()
