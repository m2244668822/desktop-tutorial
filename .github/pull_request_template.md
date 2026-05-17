## 變更摘要
- 這次改了什麼：
- 為什麼要改：

## 變更範圍（可複選）
- [ ] `frontend`（UI / `templates` / `static`）
- [ ] `backend`（`desktop_chat_app.py` / `core` / `tools`）
- [ ] `db`（schema / migration / data contract）
- [ ] `docs`（說明文件）
- [ ] `infra`（部署、啟動腳本、監控）

## 風險等級
- [ ] 低：純文件或不影響執行路徑
- [ ] 中：局部功能變更，可快速回滾
- [ ] 高：核心流程/資料層變更（需附回滾方案）

## Busy / 迴圈保護檢查（必填）
- [ ] 沒有新增無上限輪詢或未受控迴圈
- [ ] 非同步任務有 timeout / cancel / backoff
- [ ] 前端事件綁定避免重複註冊（避免重複觸發）
- [ ] 任務看板更新有節流（throttle/debounce）或明確週期

## 驗證紀錄（至少填 1 項）
- [ ] 本地啟動驗證：`./start_desktop_chat_app.sh web`
- [ ] Web 路由驗證：`http://127.0.0.1:5001/Perob`
- [ ] API 健康檢查：`/health` / `/api/*`（請在下方填結果）
- [ ] 測試指令（請填）：

驗證結果摘要：

## 資安與資料檢查
- [ ] 未提交 API Key / token / 私鑰
- [ ] 未提交 `logs/`, `uploads/`, `*.pid`, 暫存檔
- [ ] 若有資料結構調整，已更新對應文件（Data Contract / Migration）

## 回滾方案（中高風險必填）
- 回滾步驟：
- 影響範圍：

## 介面變更（若有）
- 截圖 / 錄影：

## 關聯項目
- Issue / 任務編號：
- 相關文件：
