# TrevorData 加密快照設計

日期：2026-11-02

## 意圖

為 `TrevorData` 建立可重複、可驗證、不可把原始資料推入 GitHub 的保全流程。流程要能：

1. 建立 AES-256-GCM 加密快照。
2. 產生逐檔 SHA-256 checksum manifest。
3. 在隔離目錄解密、解壓並逐檔驗證，且不修改來源資料。

## 範圍

### 目標

- 使用既有 `core.encrypted_store.DeviceEncryptionKey` 作為裝置金鑰來源，避免另造一套密碼儲存機制。
- 將來源目錄打包成 gzip tar，再以 AES-256-GCM 加密。
- 排除明確的瞬時檔案（lock、pid、tmp），並在 manifest 記錄排除規則與來源根目錄。
- manifest 同時保存每個納入檔案的相對路徑、位元組大小、mtime 與 SHA-256。
- 還原驗證只寫入指定的隔離目錄；驗證失敗時以非零退出碼結束。

### 非目標

- 不把 `TrevorData` 原始內容、API key 或資料庫加入 Git。
- 不刪除、搬移或改寫來源資料。
- 不承諾快照可在沒有原裝置金鑰的另一台機器直接解密；跨機復原金鑰交換另列 P0.1。

## 方案比較

| 方案 | 取捨 | 結論 |
| --- | --- | --- |
| 7-Zip／age 外部工具 | Windows 環境目前沒有可依賴的工具；格式與金鑰管理會漂移 | 不採用 |
| Python `cryptography` + AES-256-GCM | 可重用既有 Trevor 金鑰邊界、可測試、跨平台；需要新增小工具 | 採用 |
| 只做 tar＋外部密碼工具 | 目前不可用，且還原可重現性弱 | 不採用 |

## 設計

新增 `tools/trevor_data_snapshot.py`，提供三個子命令：

- `create --source <dir> --output <file> --manifest <file>`：建立快照與 manifest。
- `restore --snapshot <file> --destination <dir> --manifest <file>`：解密、解壓並驗證。
- `verify --snapshot <file> --manifest <file>`：驗證加密快照封裝摘要，不寫入來源。

加密封裝使用固定 magic、版本、演算法、nonce、AAD、壓縮明文大小與加密內容；nonce 每次新建。manifest 使用 canonical JSON，並保存 `source_root`、建立時間、納入／排除檔案、每檔 SHA-256、快照密文 SHA-256，以及驗證結果摘要。

## 安全與邊界

- 快照與 manifest 預設寫入來源目錄之外的 `TrevorBackups`。
- 寫檔採暫存檔＋原子 replace；快照建立未完成時不留下可被誤認為完成的正式檔名。
- 不在 stdout、log 或 manifest 寫入金鑰內容。
- 還原驗證使用新的 temporary directory；完成後只刪除本次建立的隔離目錄。

## 驗收

- 單元測試先驗證：空目錄、二進位檔、排除 lock/pid、篡改密文、篡改 manifest、成功還原與來源未變更。
- 實機驗收：對目前 `E:\智能體\TrevorData` 建立快照，產生 manifest，於隔離目錄還原，逐檔 checksum 全部通過。
- 驗收輸出不得包含任何 API key 或對話正文。

## 待確認

此版本的 P0 使用本機 Trevor 裝置金鑰，因此跨機復原必須先把同一金鑰安全帶到目標機。若需求是可離線帶走的備份，下一版要改成使用使用者提供的 passphrase 或獨立金鑰封裝；那會是不同的金鑰生命週期設計。
