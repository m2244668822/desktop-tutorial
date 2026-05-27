# 2026-05-23 Mac / Windows 狀態交接報告

產出時間：2026-05-23 11:20 +08:00

## 結論

目前主程式、總管對談模式、Knowledge Hub、ChatGPT 長期記憶庫、SQLite、FAISS、任務看板都已重新核對。

- 主程式服務：已重啟，`http://127.0.0.1:5001/status` 回傳 `ok: true`
- ChatGPT 長期記憶庫：就緒
- SQLite：就緒
- FAISS：就緒
- Knowledge Hub 索引筆數：446
- `data/knowledge_hub/manifest.json`：已重建
- 任務看板：pending 0、running 0、completed 192、failed 44
- 舊 HDD pending smoke test：已跑成功並標記完成

## 這次真正的問題

### 1. 總管反應變慢、講話像工具報表

原因不是模型變笨，而是舊邏輯把「總管」直接接到 LangGraph 工具工作流。

生活化講法：

- 以前你跟櫃台說「你好」，櫃台就跑去倉庫、會計室、機房全部巡一次。
- 所以回覆很慢，而且回來只給你一張設備巡檢單。
- 現在改成：一般聊天走櫃台；你明確說「檢查、修復、執行、debug」才開工具間。

已修復位置：

- `desktop_chat_app.py`
- `core/web_server.py`

驗證結果：

- `以前不會這樣，解釋原因`：輕量對談，`workflow_ran=false`，約 0.003 秒
- `請檢查系統狀態`：工具工作流，`workflow_ran=true`，約 10.8 秒

### 2. 記憶庫顯示不一致

原因是資料本體存在，但舊 workflow 只看 `data/knowledge_hub/manifest.json`。
當 manifest 缺失時，它誤報「ChatGPT 長期記憶庫未就緒」。

生活化講法：

- 書其實都在圖書館裡。
- 但門口的地圖不見了，所以舊櫃台以為圖書館還沒開。
- 現在已重新貼上地圖，並且櫃台會直接問圖書館本體，不只看門口紙條。

已修復位置：

- `core/knowledge_hub.py`
- `core/workflow_runtime.py`
- `core/langgraph_workflow.py`
- `tools/sync_knowledge_hub.py`

核對結果：

- ChatGPT DB：`G:\城城城程式\500\llama32-chat\data\local_knowledge\complete_chatgpt_database.json`
- SQLite：`G:\城城城程式\data\knowledge_hub\memory_layers\memory.sqlite3`
- FAISS：`G:\城城城程式\data\knowledge_hub\memory_layers\long_term.faiss`
- FAISS meta：`G:\城城城程式\data\knowledge_hub\memory_layers\long_term_meta.json`
- Memory items：446

### 3. JSON 偶發讀取錯誤

曾看到 `data/agent_memories/conversations.json` 在讀取時出現 UTF-8/JSON 錯誤。
重新驗證後檔案有效，判斷是「讀取時剛好碰到寫檔中」。

生活化講法：

- 有人正在重抄筆記本，另一個人剛好拿去看，所以看到半頁。
- 現在改成先寫暫存檔，整本寫完後一次替換，讀取者只會看到舊本或新本，不會看到半本。

已修復位置：

- `tools/agent_memory_manager.py`

驗證結果：

- `data/agent_memories/conversations.json`：valid JSON，123 組
- `data_hdd_storage/agent_memories/conversations.json`：valid JSON，79 組
- `500/llama32-chat/data/conversations.json`：valid JSON，1385 組

## Mac 端接手步驟

1. 確認工作區已掛載。
2. 設定 UTF-8：

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
```

3. 重新生成當機器路徑專用的 manifest：

```bash
python3 tools/sync_knowledge_hub.py
```

4. 啟動主程式：

```bash
python3 desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

5. 檢查：

```bash
curl http://127.0.0.1:5001/status
```

預期：`ok: true`

## 不可行或高風險做法

- 不要直接拿 Windows 絕對路徑 manifest 給 Mac 當真相。
- 不要刪掉 `data/knowledge_hub/memory_layers/` 來「重建乾淨環境」。
- 不要把 n8n 混進 Web 啟動腳本。
- 不要在 Git 狀態大量未追蹤時使用 `git reset --hard`。
- 不要用硬編碼 `/Volumes/...` 或 `G:\...` 寫進共用 Python 核心。

## FFmpeg / MP4 狀態

- `ffmpeg` 目前仍未完成永久安裝。
- `winget` 找得到 `Gyan.FFmpeg 8.1.1`，但下載程序卡住。
- 手動 GitHub 來源可連，但下載速度過低，估計需一小時以上，因此本輪停止。
- Lacan 任務仍維持 GIF + HTML 交付，MP4 需下輪用更穩定網路或離線安裝包補上。

## 本輪驗證命令摘要

```powershell
.\.venv\Scripts\python.exe tools\sync_knowledge_hub.py
.\.venv\Scripts\python.exe -m py_compile core\knowledge_hub.py core\workflow_runtime.py core\langgraph_workflow.py desktop_chat_app.py tools\agent_memory_manager.py
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5001/status
```

## 目前剩餘風險

- Git 工作區仍是大量未追蹤檔案狀態，這是歷史結構問題，不是本輪修復造成。
- 看板仍有 44 個 failed 舊 workflow log，屬於歷史失敗紀錄；目前 active pending/running 已清零。
- FFmpeg 尚未完成安裝，所以 MP4 仍未產出。

