# Windows 圖片 API 憑證操作

崔佛在 Windows 使用目前登入者的 Credential Manager 保存 AI Horde 金鑰。金鑰不應放進 `.env`、Git、聊天訊息或命令列參數。

## 立即啟用匿名模式

匿名模式使用 AI Horde 官方公開的匿名身分，優先級最低，但不需要註冊：

```powershell
.\.venv\Scripts\python.exe tools\configure_ai_horde_credential.py anonymous
```

## 設定個人金鑰

下列命令會顯示隱藏輸入提示；輸入內容不會出現在螢幕或 shell history：

```powershell
.\.venv\Scripts\python.exe tools\configure_ai_horde_credential.py set
```

設定後重新啟動崔佛後端，再檢查：

```powershell
.\.venv\Scripts\python.exe tools\configure_ai_horde_credential.py status
Invoke-RestMethod http://127.0.0.1:5001/api/ai-horde/status
```

預期 `configured` 為 `true`，且 API 回應不得包含金鑰內容。

## 移除

移除會刪除 Credential Manager 中 `Trevor/perob.ai-horde/api-key` 這一筆資料：

```powershell
.\.venv\Scripts\python.exe tools\configure_ai_horde_credential.py delete --yes
```

## 邊界

- Qwen 負責理解對話與整理提示詞；AI Horde 的志願工作節點負責生成圖片。
- 圖片提示詞會傳送到 AI Horde；不要在提示詞放入密碼、身分資料或其他敏感資訊。
- 匿名模式在忙碌時等待較久。需要較高優先級時，再用 `set` 換成個人金鑰。
- Windows Credential Manager 修復同時適用於崔佛其他以 `KeychainCredentialStore` 管理的供應商金鑰。
