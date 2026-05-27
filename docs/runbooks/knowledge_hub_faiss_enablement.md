# Knowledge Hub FAISS 啟用補強 Runbook

## 目標
- 在不破壞既有 `sqlite_only` 可用性的前提下，啟用 FAISS 向量索引加速。
- 完成後需讓報告中的「尚待補強」從 `FAISS 未就緒` 變為已完成。

## 現況（2026-05-21）
- SQLite 記憶層：已可用（`total_items = 241`）。
- FAISS：未安裝，系統可降級運作。

## 執行步驟
1. 安裝依賴（以目前 Python 環境）：
   - `python3 -m pip install faiss-cpu sentence-transformers`
2. 重建知識中樞：
   - `python3 -c "from core.knowledge_hub import KnowledgeHub; from pathlib import Path; h=KnowledgeHub(Path('.')); print(h.rebuild()); print(h.status())"`
3. 重新產生共同報告：
   - `python3 tools/generate_agent_collab_report.py`

## 驗證標準
- `h.status()` 中：
  - `faiss_ready == True`
  - `total_items > 0`
- 最新 `reports/AGENT_COMMON_STATUS_*.md`：
  - 不再出現 `FAISS 未就緒` 作為尚待補強。

## 回滾與風險
- 若安裝失敗，系統保持 `sqlite_only` 不中斷。
- 若版本衝突，先移除套件後改用乾淨 venv 安裝：
  - `python3 -m venv .venv-faiss && source .venv-faiss/bin/activate`
  - 再執行安裝與重建。

