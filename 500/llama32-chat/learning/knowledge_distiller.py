#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KnowledgeDistiller — 三層知識蒸餾
Raw原文 → Wiki蒸餾 → Schema控制

架構對應 KAL Loop 的「擷取蒸餾」節點：
  1. RawStore    — 存原始片段，不加工
  2. WikiDistiller — 用 ollama 把原始文本提煉成 wiki 風格摘要
  3. SchemaValidator — 確保輸出符合結構化 schema（topic/summary/facts/confidence）
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama

logger = logging.getLogger("knowledge_distiller")

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
_DISTILL_DIR = _PROJECT_ROOT / "data" / "knowledge"

# ── Schema 結構 ──────────────────────────────────────────────

KNOWLEDGE_SCHEMA = {
    "topic": str,  # 主題關鍵詞
    "summary": str,  # wiki 風格一段摘要
    "key_facts": list,  # 3-5 條重要事實（字串列表）
    "confidence": float,  # 0.0~1.0 可信度
    "source_type": str,  # conversation / file / external / error_log
    "distilled_at": str,  # ISO timestamp
}

_DISTILL_PROMPT = """\
你是知識提煉助手。將以下原始文字提煉為結構化知識。

原始文字：
{raw_text}

請輸出嚴格 JSON（不要任何 markdown），格式：
{{
  "topic": "主題（10字以內）",
  "summary": "wiki 風格摘要（100-200字）",
  "key_facts": ["事實1", "事實2", "事實3"],
  "confidence": 0.85
}}"""


# ── RawStore ─────────────────────────────────────────────────


class RawStore:
    """儲存未加工的原始片段。"""

    def __init__(self, store_dir: Path = _DISTILL_DIR / "raw"):
        self.dir = store_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.dir / "index.json"
        self._index: List[Dict] = self._load_index()

    def save(self, fragment: Dict) -> str:
        fid = fragment.get("id") or f"raw_{int(time.time() * 1000)}"
        entry = {
            "id": fid,
            "query": fragment.get("query", ""),
            "content": fragment.get("content", ""),
            "source_type": fragment.get("type", "unknown"),
            "saved_at": datetime.now().isoformat(),
        }
        path = self.dir / f"{fid}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        self._index.append({"id": fid, "query": entry["query"], "path": str(path)})
        self._save_index()
        return fid

    def get(self, fid: str) -> Optional[Dict]:
        path = self.dir / f"{fid}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def _load_index(self) -> List[Dict]:
        if self._index_path.exists():
            try:
                with open(self._index_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_index(self):
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index[-5000:], f, ensure_ascii=False, indent=2)


# ── WikiDistiller ─────────────────────────────────────────────


class WikiDistiller:
    """用 ollama 把 raw 文本蒸餾為 wiki 摘要。"""

    def __init__(self, model: str = "llama3.2"):
        self.model = model
        self._wiki_dir = _DISTILL_DIR / "wiki"
        self._wiki_dir.mkdir(parents=True, exist_ok=True)

    def distill(self, raw_id: str, raw_text: str, query: str = "") -> Dict:
        """回傳 wiki 格式的知識物件，並持久化。"""
        wiki = self._call_ollama(raw_text) or self._fallback(raw_text, query)
        wiki["raw_id"] = raw_id
        wiki["distilled_at"] = datetime.now().isoformat()
        wiki.setdefault("source_type", "unknown")

        wiki_id = f"wiki_{raw_id}"
        path = self._wiki_dir / f"{wiki_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wiki, f, ensure_ascii=False, indent=2)

        logger.debug(
            "蒸餾完成: %s → topic=%s conf=%.2f",
            raw_id,
            wiki.get("topic"),
            wiki.get("confidence", 0),
        )
        return wiki

    def _call_ollama(self, raw_text: str) -> Optional[Dict]:
        prompt = _DISTILL_PROMPT.format(raw_text=raw_text[:3000])
        try:
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 512},
            )
            text = resp["message"]["content"].strip()
            # 擷取 JSON 區塊
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                data["confidence"] = float(data.get("confidence", 0.7))
                return data
        except Exception as e:
            logger.debug("ollama 蒸餾失敗: %s", e)
        return None

    def _fallback(self, raw_text: str, query: str) -> Dict:
        """ollama 失敗時的規則蒸餾。"""
        sentences = [
            s.strip()
            for s in raw_text.replace("\n", "。").split("。")
            if len(s.strip()) > 10
        ]
        return {
            "topic": query[:20] or "未知主題",
            "summary": "。".join(sentences[:3]),
            "key_facts": sentences[:5],
            "confidence": 0.4,
        }


# ── SchemaValidator ───────────────────────────────────────────


class SchemaValidator:
    """驗證並修正知識物件的 schema 合規性。"""

    REQUIRED = {"topic", "summary", "key_facts", "confidence", "distilled_at"}

    def validate(self, wiki: Dict) -> Dict:
        """回傳經過修正的 wiki，並附加 schema_valid 欄位。"""
        result = dict(wiki)

        result.setdefault("topic", "未知主題")
        result.setdefault("summary", "")
        result.setdefault("key_facts", [])
        result.setdefault("confidence", 0.5)
        result.setdefault("distilled_at", datetime.now().isoformat())
        result.setdefault("source_type", "unknown")

        # 型別強制
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        if not isinstance(result["key_facts"], list):
            result["key_facts"] = [str(result["key_facts"])]
        result["topic"] = str(result["topic"])[:50]
        result["summary"] = str(result["summary"])[:1000]

        result["schema_valid"] = all(k in result for k in self.REQUIRED)
        return result

    def save(self, wiki: Dict) -> str:
        """將通過 schema 的知識存入 schema_store。"""
        schema_dir = _DISTILL_DIR / "schema"
        schema_dir.mkdir(parents=True, exist_ok=True)
        sid = f"schema_{wiki.get('raw_id', int(time.time()))}"
        path = schema_dir / f"{sid}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wiki, f, ensure_ascii=False, indent=2)
        return sid


# ── 主協調器 ─────────────────────────────────────────────────


class KnowledgeDistiller:
    """
    統一入口：Raw → Wiki → Schema
    呼叫 distill_fragment(fragment_dict) 即可完成全流程。
    """

    def __init__(self, model: str = "llama3.2"):
        self.raw_store = RawStore()
        self.wiki_distiller = WikiDistiller(model=model)
        self.schema_validator = SchemaValidator()

    def distill_fragment(self, fragment: Dict) -> Optional[Dict]:
        """
        fragment 格式：{"id": "...", "content": "...", "type": "...", "query": "..."}
        回傳 schema-validated 知識物件，失敗回傳 None。
        """
        content = (fragment.get("content") or "").strip()
        if not content or len(content) < 30:
            return None

        try:
            # 1. Raw 存檔
            raw_id = self.raw_store.save(fragment)

            # 2. Wiki 蒸餾
            wiki = self.wiki_distiller.distill(
                raw_id=raw_id,
                raw_text=content,
                query=fragment.get("query", ""),
            )
            wiki["source_type"] = fragment.get("type", "unknown")

            # 3. Schema 驗證
            validated = self.schema_validator.validate(wiki)

            # 4. 若可信度太低，拒絕（低於 0.3 為雜訊）
            if validated["confidence"] < 0.3:
                logger.debug("蒸餾結果可信度過低 (%.2f)，捨棄", validated["confidence"])
                return None

            self.schema_validator.save(validated)
            return validated

        except Exception as e:
            logger.warning("蒸餾失敗 [%s]: %s", fragment.get("id"), e)
            return None

    def distill_batch(self, fragments: List[Dict]) -> List[Dict]:
        results = []
        for frag in fragments:
            wiki = self.distill_fragment(frag)
            if wiki:
                results.append(wiki)
        logger.info("蒸餾批次: %d/%d 成功", len(results), len(fragments))
        return results

    def load_schema_store(self) -> List[Dict]:
        """讀取所有已蒸餾的 schema 知識。"""
        schema_dir = _DISTILL_DIR / "schema"
        if not schema_dir.exists():
            return []
        items = []
        for path in schema_dir.glob("schema_*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    items.append(json.load(f))
            except Exception:
                pass
        return items
