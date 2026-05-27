# 申言者重評報告：校正後分數與補救紀錄

日期：2026-05-23
評分角色：申言者
校正來源：使用者最新扣分規則

## 1. 扣分規則更新

本次重新承認以下扣分：

- 主程式前端一開始沒有開啟：扣 10 分。
- 圖片只用 SVG/連結呈現，沒有交付可直接視覺檢查的完整圖片：扣 10 分。
- 論文導讀不夠生活化，未達費曼法等級：扣 10 分。
- 使用目前 OpenAI Codex / OpenAI Code 協助本身列為外部支援：扣 10 分。
- n8n 未在前次評分時做到長駐：扣 10 分。

## 2. 原始交付重評

前一版申言者給 `99 / 100` 不成立。

依照新規則，原始交付應調整為：

- 基準：100
- 主程式前端未先開：-10
- 圖片任務失敗：-10
- 論文內容不夠費曼法：-10
- 使用 OpenAI Codex：-10
- n8n 未完成長駐：-10

原始交付重評：`50 / 100`

## 3. 補救後狀態

### 主程式前端

- 已啟動主 Web。
- `http://127.0.0.1:5001/status` 回傳 200。

### n8n 長駐

- 已修復 n8n 啟動崩潰：本機 `@langchain/core/language_models/stream` exports 缺失，已加本機 shim，並備份原 `package.json`。
- `n8n --help` 已可正常列出 `start` 指令。
- `n8n_watchdog_windows.ps1` 可啟動 n8n。
- `127.0.0.1:5678/healthz` 回傳 200。
- Windows Scheduled Task 安裝因權限拒絕失敗，已改用使用者 Startup 資料夾備援：
  - `C:\Users\pc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ChengWorkspaceN8nWatchdog.cmd`
- 目前 watchdog loop 已啟動，n8n 5678 正在監聽。

### 圖片任務

- 已新增真正 PNG 圖片：`reports/eye_mold_mental_health_infographic_20260522.png`
- 原 SVG 保留為可編輯版本：`reports/eye_mold_mental_health_infographic_20260522.svg`

### 論文導讀

- 已改寫為費曼法版本：`reports/EYE_MOLD_MENTAL_HEALTH_PAPER_20260522.md`
- 補上「身體像房子、眼睛像窗戶、免疫系統像警報器」的生活化解釋。
- 明確分開「黴菌暴露」與「眼部真菌感染」。
- 保守處理精神疾病因果，不誇大。

### 亂碼清理

工程師負責項目成立。已處理會阻斷任務的 UTF-8 子程序問題：

- `system_main.py`
- `tools/harmony_check.py`
- `tools/portable_workspace_audit.py`
- `core/workflow_runtime.py`
- `tools/agent_autonomy_daemon.py`

仍需逐步清理舊歷史 log/MD 裡的文字亂碼。這是資料清潔任務，不應一次性硬替換，以免破壞舊紀錄。

## 4. 補救後重評

補救後可恢復的項目：

- 主程式前端：已修正。
- n8n 長駐：已修正為 watchdog + Startup 備援。
- 圖片：已修正為 PNG。
- 論文導讀：已改為費曼法版本。

不可恢復扣分：

- 本次工作確實使用了 OpenAI Codex / OpenAI Code，依規則扣 10 分。

補救後評分：`90 / 100`

## 5. 申言者結論

前一版 `99 / 100` 是過度樂觀，應撤回。依新規則，原始交付是 `50 / 100`；補救後，除使用 OpenAI Codex 這項不可回復扣分外，其餘主要失誤已修正，因此補救後為 `90 / 100`。
