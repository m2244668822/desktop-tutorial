# SSD -> HDD 轉移與程式編排修整報告（2026-05-17）

## 1) 轉移結果
- 來源（SSD）：`/Volumes/智能體/城城城程式`
- 目標（HDD）：`/Volumes/For Word/Agent_FastData/城城城程式_full_backup_20260517`
- 同步方式：`rsync -aH --delete`
- SSD 釋放動作：`/Volumes/For Word/Agent_FastData/城城城程式_ssd_offload_20260517`

### 同步統計（最後一次完整同步）
- Number of files: `127570`
- Number of files transferred: `8711`
- Total file size: `7719465245` bytes
- Total transferred file size: `2540838555` bytes
- Total time: 約 `9m31s`

## 2) 重要相容性發現（Windows 也會受影響）
偵測到大小寫衝突案例（case-insensitive collision）：

- `.venv312/bin/Activate.ps1`
- `.venv312/bin/activate.ps1`

在大小寫不敏感檔案系統（多數 HDD / Windows NTFS）會被視為同名，無法完整共存。  
這是為什麼乾跑比對仍出現 1 筆差異。

## 3) 已落地修整

### 啟動鏈路（不破壞結構）
1. `start_desktop_chat_app.sh`
   - 移除硬編碼路徑，改為使用腳本自身目錄。
   - 同時支援：
     - `.venv/bin/python`（macOS/Linux）
     - `.venv/Scripts/python.exe`（Windows）

2. `system_main.py`
   - 新增跨平台 Python 執行檔偵測（macOS/Linux/Windows）。
   - 保持既有 `web / desktop / health` 模式不變。

### 同步工具化
新增：
- `tools/check_case_collisions.py`：掃描大小寫衝突檔名
- `tools/sync_ssd_to_hdd.sh`：一鍵同步 + 碰撞掃描 + dry-run 驗證 + 日誌

### SSD 空間釋放實作（實際執行）
已搬到 HDD（offload）：
- `.venv312`
- `.venv.backup.20260329_085315`
- `.pip-cache`
- `.sync_user_project`
- `本地`
- `封存.zip`

> 注意：`.python-installations` 原本也搬走，但 `.venv/bin/python3.12` 依賴該路徑（符號連結）。
> 已立即回補到 SSD，確保主線可啟動。

## 4) 後續建議（程式編排）
### A. 先做「無風險」整理
- 保留主線入口：
  - `start_desktop_chat_app.sh`
  - `system_main.py`
  - `desktop_chat_app.py`
- 根目錄其他一次性腳本逐步移到 `legacy/scripts/`（先搬文檔、再搬腳本）

### B. 建立分層目錄（分批，不一次大搬）
- `apps/`：執行主程式
- `tools/`：維運工具
- `docs/`：文件
- `reports/`：報告
- `legacy/`：舊方案歸檔

### C. Windows 搬機前必做
1. 跑大小寫衝突掃描
2. 修掉衝突檔名
3. 再做打包或同步

## 5) 操作指令
```bash
# 一鍵同步（預設路徑）
./tools/sync_ssd_to_hdd.sh

# 指定來源/目標
./tools/sync_ssd_to_hdd.sh "/Volumes/智能體/城城城程式" "/Volumes/For Word/Agent_FastData/城城城程式_full_backup_自訂名稱"

# 單獨掃描大小寫衝突
python3 tools/check_case_collisions.py "/Volumes/智能體/城城城程式"
```
