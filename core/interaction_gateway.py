"""Single intent gateway for Trevor conversations and executable tasks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class InteractionDecision:
    route: str
    purpose: str
    capability_mode: str
    should_execute: bool = False
    requires_confirmation: bool = False
    risk_level: str = "low"
    reason: str = "conversation_default"
    clarification: str = ""
    requested_mode: str = "auto"

    def public_dict(self) -> dict:
        return asdict(self)


class InteractionGateway:
    """Prefer dialogue; authorize tools only for explicit, scoped operations."""

    _NO_EXECUTION = (
        "不要直接執行",
        "先不要執行",
        "不用執行",
        "不要動手",
        "先不要動手",
        "只要解釋",
        "只是了解",
        "只是問",
        "先解釋",
        "先聊天",
        "先對話",
        "先討論",
    )
    _DIRECT_REQUEST = ("幫我", "請你", "請幫", "直接", "立刻", "馬上", "開始")
    _QUESTION = (
        "如何",
        "怎麼",
        "為什麼",
        "什麼是",
        "是否",
        "能不能",
        "可不可以",
        "要不要",
        "應不應該",
        "你覺得",
    )
    _AMBIGUOUS = (
        "處理一下",
        "弄一下",
        "幫我做一下",
        "幫我弄好",
        "搞定它",
        "照辦",
    )
    _ACTION = (
        "執行",
        "修復",
        "修正",
        "修改",
        "安裝",
        "解除安裝",
        "啟動",
        "重啟",
        "停止",
        "建立",
        "新增",
        "寫入",
        "更新",
        "優化",
        "改善",
        "重構",
        "測試",
        "檢查",
        "確認",
        "盤點",
        "查看",
        "搜尋",
        "下載",
        "上傳",
        "提交",
        "合併",
        "部署",
        "發布",
        "公開",
        "刪除",
        "移除",
        "關閉",
        "開啟",
        "同步",
        "run",
        "fix",
        "repair",
        "install",
        "start",
        "restart",
        "build",
        "test",
        "commit",
        "merge",
        "push",
        "pull",
        "deploy",
        "delete",
        "remove",
    )
    _OPERATIONAL_TARGET = (
        "repo",
        "repository",
        "git",
        "branch",
        "分支",
        "commit",
        "push",
        "pull",
        "檔案",
        "文件",
        ".py",
        ".html",
        ".js",
        ".ts",
        ".md",
        "前端",
        "後端",
        "程式",
        "代碼",
        "測試",
        "服務",
        "伺服器",
        "server",
        "api",
        "n8n",
        "docker",
        "ollama",
        "qwen",
        "openclaw",
        "資料",
        "資料庫",
        "記憶庫",
        "套件",
        "環境",
        "虛擬環境",
        "本機",
        "電腦",
        "系統",
        "app control",
        "防火牆",
        "防毒",
        "網站",
        "遠端",
        "工作樹",
        "log",
        "日誌",
    )
    _COMMAND_PATTERN = re.compile(
        r"(?:^|\s)(?:git|docker|npm|pnpm|yarn|pytest|pip|uv|ollama|n8n)\s+[a-z0-9:_./-]+",
        re.IGNORECASE,
    )
    _QUESTION_ENDING = re.compile(r"(?:嗎|呢|是不是|好不好)[？?]?$", re.IGNORECASE)
    _HIGH_RISK = (
        "解除安裝",
        "格式化",
        "reset --hard",
        "force push",
        "push --force",
        "drop table",
        "truncate",
        "rm -rf",
        "關閉 smart app control",
        "關閉防火牆",
        "關閉防毒",
        "停用防火牆",
        "停用防毒",
        "變更權限",
        "系統管理員",
        "登錄檔",
        "registry",
        "push 到遠端",
        "推送到遠端",
        "部署",
        "發布",
        "公開網站",
        "上傳",
    )
    _DESTRUCTIVE_ACTION = ("刪除", "移除", "清空")
    _DESTRUCTIVE_TARGET = (
        "資料",
        "檔案",
        "目錄",
        "資料夾",
        "資料庫",
        "記憶",
        "紀錄",
        "記錄",
        "帳號",
        "分支",
        "repo",
        "磁碟",
    )
    _SELF_IMPROVEMENT = (
        "自我優化",
        "自行優化",
        "優化後端",
        "改善後端",
        "重構後端",
        "優化崔佛",
        "改善崔佛",
        "修正崔佛",
        "優化對話路由",
        "改善對話路由",
    )

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        normalized = str(mode or "auto").strip().lower()
        aliases = {
            "execution": "task",
            "workflow": "task",
            "chat": "conversation",
            "general": "conversation",
        }
        return aliases.get(normalized, normalized or "auto")

    @classmethod
    def is_confirmation_message(cls, message: str) -> bool:
        compact = re.sub(r"\s+", "", str(message or "").strip().lower())
        return compact in {
            "確認",
            "我確認",
            "確認執行",
            "是，確認執行",
            "好，確認執行",
            "yes,confirm",
            "confirm",
        }

    def infer_capability(self, message: str, hint: str = "") -> str:
        text = str(message or "").lower()
        normalized_hint = str(hint or "").strip().lower()
        valid = {"general", "coding", "research", "security", "content", "learning"}
        if normalized_hint in valid and normalized_hint != "general":
            return normalized_hint
        if any(token in text for token in ("資安", "安全性", "漏洞", "防火牆", "防毒", "xss", "csrf")):
            return "security"
        if any(
            token in text
            for token in (
                "python",
                "javascript",
                "typescript",
                "程式",
                "代碼",
                "repo",
                "git",
                "測試",
                "前端",
                "後端",
                "api",
                ".py",
                ".html",
            )
        ):
            return "coding"
        if any(token in text for token in ("研究", "論文", "證據", "文獻", "資料來源", "比較")):
            return "research"
        if any(token in text for token in ("文章", "文案", "腳本", "創作", "詩", "改寫")):
            return "content"
        if any(token in text for token in ("教我", "練習", "學習", "教材")):
            return "learning"
        return "general"

    @classmethod
    def is_self_improvement_request(cls, message: str) -> bool:
        text = str(message or "").strip().lower()
        return bool(text) and any(token in text for token in cls._SELF_IMPROVEMENT)

    def decide(
        self,
        message: str,
        *,
        requested_mode: str = "auto",
        capability_hint: str = "",
        confirmed: bool = False,
    ) -> InteractionDecision:
        text = str(message or "").strip()
        lowered = text.lower()
        mode = self._normalize_mode(requested_mode)
        capability = self.infer_capability(text, capability_hint)
        base = {
            "capability_mode": capability,
            "requested_mode": mode,
        }

        if not text:
            return InteractionDecision(
                route="clarification",
                purpose="discussion",
                clarification="我還沒收到要談或處理的內容。",
                reason="empty_message",
                **base,
            )

        if any(token in lowered for token in self._NO_EXECUTION) or mode == "conversation":
            return InteractionDecision(
                route="conversation",
                purpose="discussion",
                reason="conversation_explicit",
                **base,
            )

        has_direct_request = any(token in lowered for token in self._DIRECT_REQUEST)
        is_question = any(token in lowered for token in self._QUESTION) or bool(
            self._QUESTION_ENDING.search(lowered)
        )
        has_action = any(token in lowered for token in self._ACTION)
        has_target = any(token in lowered for token in self._OPERATIONAL_TARGET)
        has_command = bool(self._COMMAND_PATTERN.search(lowered))
        imperative = any(
            re.match(
                rf"^(?:請(?:你)?|麻煩(?:你)?|幫我|先|現在|立刻|馬上)?\s*{re.escape(action)}",
                lowered,
            )
            or re.match(rf"^(?:在)?本機\s*{re.escape(action)}", lowered)
            or re.match(rf"^把.{{1,24}}{re.escape(action)}", lowered)
            for action in self._ACTION
        )

        if is_question and not has_direct_request and mode != "task":
            return InteractionDecision(
                route="conversation",
                purpose="discussion",
                reason="question_not_execution",
                **base,
            )

        if any(token in lowered for token in self._AMBIGUOUS) and not has_target:
            return InteractionDecision(
                route="clarification",
                purpose="discussion",
                clarification=(
                    "我不確定你要處理的是哪個目標或範圍。請告訴我要查看／修改的對象，"
                    "以及這輪只要討論、還是要我實際執行。"
                ),
                reason="missing_operation_target",
                **base,
            )

        wants_task = has_command or (
            has_action
            and has_target
            and (has_direct_request or imperative or mode == "task")
        )
        if mode == "task" and not wants_task:
            return InteractionDecision(
                route="clarification",
                purpose="discussion",
                clarification="你選擇了任務執行，但目前缺少可操作的目標或範圍。",
                reason="task_override_missing_scope",
                **base,
            )
        if not wants_task:
            return InteractionDecision(
                route="conversation",
                purpose="discussion",
                reason="conversation_default",
                **base,
            )

        high_risk = any(token in lowered for token in self._HIGH_RISK) or (
            any(token in lowered for token in self._DESTRUCTIVE_ACTION)
            and any(token in lowered for token in self._DESTRUCTIVE_TARGET)
        )
        if high_risk and not confirmed:
            return InteractionDecision(
                route="confirmation",
                purpose="execution",
                should_execute=False,
                requires_confirmation=True,
                risk_level="high",
                reason="high_risk_confirmation_required",
                clarification=(
                    "這個操作可能刪除資料、降低安全性或造成外部副作用。"
                    f"我先不執行「{text[:160]}」；確認目標與影響後，"
                    "請回覆「確認執行」。"
                ),
                **base,
            )

        self_improvement = self.is_self_improvement_request(text)
        return InteractionDecision(
            route="task",
            purpose="self_improvement" if self_improvement else "execution",
            should_execute=True,
            risk_level="high" if high_risk else "low",
            reason=(
                "confirmed_high_risk_task"
                if high_risk
                else "self_improvement_proposal"
                if self_improvement
                else "explicit_scoped_task"
            ),
            **base,
        )


__all__ = ["InteractionDecision", "InteractionGateway"]
