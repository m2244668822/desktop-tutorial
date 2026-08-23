# Knowledge Hub FAISS 啟用補強 Runbook（2026-05-28 強化版）

## 目標
- 在不破壞既有 `sqlite_only` 可用性的前提下，啟用 FAISS 向量索引加速。
- 完成後需讓報告中的「尚待補強」從 `FAISS 未就緒` 變為已完成。

## 現況（2026-05-28）
- SQLite 記憶層：已可用（`total_items = 241`）。
- FAISS：未安裝，系統可降級運作。

## 前置檢查
1. 確認目前 Python 環境：
   - `python3 -V`
   - `which python3`
2. 確認專案根目錄可寫入：
   - `pwd` 應為工作區根目錄。
3. 確認現況報表：
   - `python3 tools/generate_agent_collab_report.py`
   - 檢視最新 `reports/AGENT_COMMON_STATUS_*.md` 是否仍有 `FAISS 未就緒`。

## 執行步驟
1. 安裝依賴（以目前 Python 環境）：
   - `python3 -m pip install faiss-cpu sentence-transformers`
2. 重建知識中樞：
   - `python3 -c "from core.knowledge_hub import KnowledgeHub; from pathlib import Path; h=KnowledgeHub(Path('.')); print(h.rebuild()); print(h.status())"`
3. 重新產生共同報告：
   - `python3 tools/generate_agent_collab_report.py`

## 一鍵驗證（建議）
可用以下命令在啟用後快速驗證：

```bash
python3 - <<'PY'
from pathlib import Path
from core.knowledge_hub import KnowledgeHub

h = KnowledgeHub(Path('.'))
st = h.status()
print('faiss_ready =', st.get('faiss_ready'))
print('total_items =', st.get('total_items'))
print('backend_mode =', st.get('backend_mode'))

if not st.get('faiss_ready'):
    raise SystemExit('FAIL: FAISS not ready')
if int(st.get('total_items') or 0) <= 0:
    raise SystemExit('FAIL: total_items <= 0')
print('OK: KnowledgeHub FAISS verification passed.')
PY
```

## 驗證標準
- `h.status()` 中：
  - `faiss_ready == True`
  - `total_items > 0`
- 最新 `reports/AGENT_COMMON_STATUS_*.md`：
  - 不再出現 `FAISS 未就緒` 作為尚待補強。

## 驗證輸出判讀
- 若 `faiss_ready = True`、`total_items > 0`：代表向量索引層可用。
- 若 `faiss_ready = False` 但系統可回應：代表仍在 `sqlite_only` 降級模式，非中斷故障。
- 若 `total_items = 0`：通常是資料尚未匯入或 rebuild 未成功，先重跑 rebuild。

## 回滾與風險
- 若安裝失敗，系統保持 `sqlite_only` 不中斷。
- 若版本衝突，先移除套件後改用乾淨 venv 安裝：
  - `python3 -m venv .venv-faiss && source .venv-faiss/bin/activate`
  - 再執行安裝與重建。

## 故障排查速記
1. `ImportError: No module named faiss`：
   - 表示安裝到錯誤 Python 環境，重新確認 `which python3`。
2. `faiss-cpu` 安裝成功但 `faiss_ready=False`：
   - 先重跑 rebuild，確認 `core/knowledge_hub` 目錄可寫入。
3. 報告仍顯示 `FAISS 未就緒`：
   - 先重建，再重新生成報告，確認看的不是舊報告檔。
