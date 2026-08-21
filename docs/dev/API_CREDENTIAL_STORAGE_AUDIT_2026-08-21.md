# API 憑證儲存與分散資料稽核（2026-08-21）

## 執行摘要

- 本次只做唯讀盤點；所有憑證值均遮罩，未輸出、搬移或刪除任何 API Key。
- 目前找不到以 `perob.ai-horde`、`ai-horde`、`stablehorde.net` 或 `aihorde.net` 命名的 macOS Keychain 項目，也沒有 AI Horde／Stable Horde 環境變數或 Git 歷史引用。先前提供的金鑰尚未位於後端可安全解析的位置。
- 既有雲端模型憑證目前以明文放在被 Git 忽略的 `500/llama32-chat/.env`；檔案未曾進入 Git，但權限是 `0644`，而上層目錄可被其他本機帳號穿越，因此本機其他帳號可能讀取。
- `500/llama32-chat/config/.env` 與主要 `.env` 重複 27 個設定，而且 27 個值全部不同；它目前是較後順位的舊回退來源，主要檔遺失時可能靜默啟用過時設定。
- API 設定載入、範本與文件分散在多個模組，且 `chatgpt_server.py` 的載入行為與桌面主程式不同，應收斂成單一後端憑證解析器與單一非機密設定來源。

## 儲存現況

| 位置 | Git 狀態 | 權限 | 內容狀態 | 建議 |
| --- | --- | --- | --- | --- |
| `.env.example` | 已追蹤 | `0644` | 只有空白範例 Key 與非機密設定 | 保留，但改成完整的非機密設定契約 |
| `.env.oci` | 已忽略 | `0644` | OCI 連線中繼資料；目前設定的私鑰目標不存在或未配置 | 保留，權限改為 `0600` |
| `.env.oci.example` | 已追蹤 | `0644` | OCI 範例 | 保留 |
| `500/llama32-chat/.env` | 已忽略、從未追蹤 | `0644` | 5 個非空白機密型變數；目前桌面主程式的主要來源 | 先改 `0600`，再把機密移入 Keychain |
| `500/llama32-chat/config/.env` | 已忽略、從未追蹤 | `0644` | 27 個舊非機密設定，全部與主要 `.env` 不同 | 完成收斂後移除 |
| macOS Keychain | 不在 Git | 系統保護 | 尚無 AI Horde／Stable Horde 項目 | 建立專用 service/account |

## 稽核發現

### API-001：明文憑證檔可被其他本機帳號讀取

- **嚴重度：High**
- **位置：** `500/llama32-chat/.env:11`、`500/llama32-chat/.env:13`、`500/llama32-chat/.env:21`、`500/llama32-chat/.env:26`、`500/llama32-chat/.env:43`
- **證據：** 上述位置分別存在非空白的 `GEMINI_API_KEY`、`GROQ_API_KEY`、`NVAPI_API_KEY`、`OPENAI_API_KEY`、`GOOGLE_API_KEY`；值未顯示。檔案模式為 `-rw-r--r--`，專案上層目錄模式為 `0755`。
- **影響：** 同一台 Mac 上的其他本機帳號可能讀取並濫用付費或具配額的 API 憑證。
- **修正：** 立即將實際憑證檔改為 `0600`；後續把 Stable Horde 與其他供應商憑證逐步移到 macOS Keychain，後端執行時才讀取。
- **緩解：** 確認磁碟與備份已加密，避免終端輸出檔案內容，並輪替曾暴露於共享帳號或備份的 Key。
- **誤判說明：** 若這台 Mac 永遠只有單一帳號且磁碟沒有其他讀取途徑，風險較低，但 `0644` 仍不是機密檔的安全預設。

### API-002：舊 `.env` 回退會造成設定漂移

- **嚴重度：Medium**
- **位置：** `core/data_paths.py:73`、`core/llm_cns.py:140`
- **證據：** 候選順序為根目錄 `.env`、`500/llama32-chat/.env`、`500/llama32-chat/config/.env`，採第一個非空白／非 placeholder 值。兩個巢狀檔重複 27 個變數，稽核時 27 個值全部不同。
- **影響：** 主要檔被移動、缺漏或改成空白時，系統會靜默採用舊設定，導致模型、離線模式、RAG、日誌與雲端傳輸行為改變。
- **修正：** 指定單一非機密設定檔；遷移完成後移除 `config/.env` 候選與實體檔案，缺少必要設定時明確失敗。
- **緩解：** 過渡期間啟動時只回報「來源路徑與變數名稱」，不要回報值，並在發現多來源衝突時警告。
- **誤判說明：** 目前主要 `.env` 的非空值優先，因此舊檔多數時間不生效；風險發生在主要來源缺失或變空時。

### API-003：既有自製加密不適合保存新憑證

- **嚴重度：Medium**
- **位置：** `chatgpt_server.py:440`、`chatgpt_server.py:446`、`chatgpt_server.py:496`、`chatgpt_server.py:542`
- **證據：** `encrypt_secret_value` 使用自製 XOR 流程，沒有驗證標籤；`resolve_api_key` 仍可回退讀取明文環境變數。
- **影響：** 密文可被竄改而無法驗證，且若主密鑰與密文同在環境檔，無法提供有效的靜態機密隔離，容易造成「已加密」的錯誤安全感。
- **修正：** Stable Horde 不使用 `*_ENC`／XOR 路徑；改由 macOS Keychain 保存，後端以固定 service/account 解析。
- **緩解：** 在完成遷移前，不要新增依賴此格式的憑證；既有格式應標示為 legacy obfuscation，而不是強加密。
- **誤判說明：** 此機制仍能避免部分無意間的純文字瀏覽，但不等同經審查的 authenticated encryption 或作業系統秘密儲存庫。

### API-004：API 設定契約與載入器過度分散

- **嚴重度：Medium**
- **位置：** `.env.example:12`、`chatgpt_server.py:44`、`core/llm_cns.py:124`、`tools/api_onboarding.py:86`、`tools/lightweight_chat_frontend_server.py:74`
- **證據：** 根範本只列 4 個 API Key；主要執行碼另引用至少 26 個機密型變數／安全旗標，但沒有一致的範本或秘密儲存說明。至少七個執行模組各自解析或合併 `.env`；Flask 入口只呼叫工作目錄相依的 `load_dotenv()`。
- **影響：** 不同啟動方式可能讀到不同憑證，維護者容易重複建立 `.env`、把 Key 放錯位置，或誤判供應商是否可用。
- **修正：** 建立唯一的後端 `credential_store` 與 `settings` 入口；所有前後端橋接、健康檢查與 CLI 都依賴同一介面。
- **緩解：** 在範本列出非機密旗標、Keychain service/account 名稱與遷移說明，但不要放真實 Key 或要求把 Key 寫進前端。
- **誤判說明：** 並非 26 個變數都必須出現在同一範本；重點是它們需要一份可驗證的設定契約與明確秘密來源。

### API-005：文件鼓勵直接輸出秘密檔

- **嚴重度：Low**
- **位置：** `docs/AGENT_SYSTEM_GUIDE.md:197`、`500/llama32-chat/docs/API_KEY_SETUP_GUIDE.md:67`、`docs/桌面聊天使用說明.md:35`
- **證據：** 文件包含 `cat .../500/llama32-chat/.env`，並分別指示使用 `config/.env`、子專案 `.env` 或工作目錄 `.env`。
- **影響：** Key 可能出現在畫面錄影、共享終端或支援截圖中；不同文件也會繼續製造多份設定。
- **修正：** 改成只顯示遮罩狀態的診斷指令，所有文件統一指向 Keychain 與單一非機密設定來源。
- **緩解：** 在遷移前明確標示「不得貼出、截圖或提交 `.env` 內容」。
- **誤判說明：** `cat` 不會自行把檔案內容寫入 shell history，但仍會把秘密顯示在終端與可能的錄影／日誌中。

## Git 與外洩檢查

- `.gitignore:34` 已忽略所有 `.env`，`.dockerignore:5` 也排除 Docker build context 內的 `.env`。
- 根 `.env`、`500/llama32-chat/.env`、`500/llama32-chat/config/.env` 在所有可見 Git 歷史中均為 0 次提交。
- 目前追蹤樹與整個工作區的常見 OpenAI、Google、GitHub、AWS、Slack Key 簽名掃描沒有命中；AI Horde／Stable Horde 字串在 Git 歷史中也沒有命中。
- 本機沒有 `gitleaks`、`trufflehog` 或 `detect-secrets`，因此上述檢查不是完整的全歷史秘密掃描；不能保證所有供應商格式都被涵蓋。
- 稽核開始時分支沒有 staged 變更，並有 16 個 modified 與 17 個 untracked 項目；建立本報告後新增 1 個 untracked 文件。環境檔皆未出現在 Git 變更中。

## 可整理或移出的候選

### 優先處理

1. `500/llama32-chat/config/.env`：目前是完全不一致的舊回退。先更新載入器與文件，再移除實體檔。
2. `reports/*_before_*.py`：6 個已追蹤的原始碼快照，共 137,263 bytes；沒有執行期引用，其中 2 個只被舊稽核文件列名。Git 本身已保存歷史，確認後可從主線刪除或移到外部封存。
3. `white-studio-arcade/`：是乾淨且有自己 `.git` 的獨立倉庫，約 740 KB；主倉庫只把它視為一個 untracked 目錄。應移到同層目錄，或明確改成 submodule，不應直接整包加入主倉庫。

### 保留但需歸檔規則

1. `reports/`：目前約 207 個檔案，其中 50 個已追蹤；執行期 JSON、HTML、圖片等多數已被忽略。建議保留 canonical Markdown，對可重建的輸出設定保存期限。
2. `reports/AGENT_COLLABORATION_REPAIR_REVIEW_20260606.md` 與 `tools/generate_agent_collaboration_review.py`：前者可重建，但目前仍是待審查成果；完成審查前不要自動刪除，之後只保留產生器或正式結論之一。
3. `docs/superpowers/specs/2026-08-21-perob-microcopy-design.md`：屬於另一項尚未完成的設計工作，與 API 整理無關；應明確續作、歸檔或移除，不要混入本次憑證提交。
4. 目前未追蹤的 `core/`、`tests/`、`tools/`、AirLLM 文件與需求檔彼此形成可辨識的功能群；沒有證據顯示它們是垃圾檔，不能直接刪除。

## 建議目標狀態

1. Stable Horde 憑證只存在 macOS Keychain，例如 service `perob.ai-horde`，account 使用目前 macOS 使用者或固定應用帳號。
2. 後端以單一 resolver 讀取 Keychain；前端只呼叫同源後端端點，永遠不接收、儲存或記錄 Key。
3. `.env.example` 只保留非機密設定，例如啟用旗標、API base、Client-Agent、逾時與 Keychain service/account 名稱；不新增真實 `AI_HORDE_API_KEY`。
4. 非機密本機設定只保留一個來源；移除 `config/.env` 與多套 fallback merge 行為。
5. 啟動診斷只輸出 `configured/missing`、來源類型與遮罩長度，不輸出內容、前綴或完整路徑。

## 建議執行順序

1. 先把現有實際 `.env` 與 `.env.oci` 權限改成 `0600`。
2. 完成 AI Horde Keychain 寫入工具與後端 resolver。
3. 由使用者在本機安全提示中輸入 Key，不在聊天、指令參數或 `.env.example` 傳遞。
4. 驗證圖像與文字請求都只經後端代理，且日誌不含 `apikey` header。
5. 收斂非機密設定與載入器，更新互相矛盾的文件。
6. 移除舊 `config/.env`、追蹤的原始碼快照，並決定巢狀倉庫的正式位置。

本次未執行刪除、權限變更、Keychain 寫入或程式碼修改。
