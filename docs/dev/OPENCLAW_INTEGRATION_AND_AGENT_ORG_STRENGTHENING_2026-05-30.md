# OpenClaw 融合主系統與智能體組織補強（2026-05-30）

## 這次做了什麼
- 將 OpenClaw 從「外部工具」提升為主系統可感知能力。
- 在主程式巡查快照加入 OpenClaw 狀態（版本、daemon 是否常駐）。
- 在 `/api/get_status` 回傳中加入 `openclaw` 區塊，供前端與監控讀取。

## 生活化說明
以前系統像一個辦公室，OpenClaw 是外包同事，大家只知道「他在不在」要靠人工問。
現在改成：總機櫃台（主系統）每天點名，直接知道他有沒有打卡（daemon running）、用哪一版工具（version）。
這樣申言者與工程師在交接時，不會再用猜的。

## 架構層補強
- 新增模組：`core/openclaw_bridge.py`
- 職責：
  - 偵測 `openclaw --version`
  - 偵測 Windows Task Scheduler 的 `OpenClaw Gateway` 狀態
  - 輸出結構化狀態（installed/version/daemon_state/notes）

## 主流程掛接點
- `desktop_chat_app.py`
  - `_build_inspection_block()`：新增 OpenClaw 即時狀態行
  - `get_status()`：新增 `openclaw` JSON 欄位
  - `_openclaw_status()`：統一調用 bridge，隔離異常

## 對組織協作的好處
- 申言者：回覆可先講「系統是否具備 OpenClaw 能力」，再做工程語譯。
- 工程師：看到 daemon 停止可直接進入修復流程，不再浪費一輪排查。
- 中樞：監控頁與任務板可以引用同一份狀態，不會多版本真相。

## 治理規則（本次新增）
- OpenClaw 相關申請（安裝、onboard、daemon、gateway）必須先經 `申言者` 決策。
- 非申言者角色收到 OpenClaw 請求時，系統會自動進入 `governance guard`：
  - 允許提供資料與資源提示（例如目前版本、daemon 狀態、可用命令）。
  - 禁止直接執行變更，避免繞道施工。
- 使用者確認語句建議：
  - `我確認，請申言者決策後再交工程師執行 OpenClaw 整合。`

## 下一步（建議）
1. 前端任務面板新增 OpenClaw 狀態燈（running/stopped）。
2. 若 daemon 非 running，觸發自動修復任務（但保留人類覆核）。
3. 將 OpenClaw 能力加入 handoff acceptance criteria（例如：交接前確認 daemon 狀態）。
