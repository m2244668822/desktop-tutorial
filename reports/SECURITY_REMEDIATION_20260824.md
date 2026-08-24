# 依賴漏洞修補報告（2026-08-24）

## 結論

- GitHub Dependabot 起始共有 44 個開啟警示：Critical 1、High 7、Medium 28、Low 8。
- Critical 為 `CVE-2025-32434`／`GHSA-53q9-r3pm-6pq6`：受影響 PyTorch 的 `torch.load(..., weights_only=True)` 仍可能造成遠端程式碼執行。
- 所有警示來源已在目前整合分支移除或升級；GitHub 會在修補合併到預設分支後重新計算並關閉警示。

## 根因

- 已退役的 AirLLM 需求檔固定舊版 `torch` 與 `transformers`，產生 Critical、High 及其他級別警示。
- 智能體擴充需求仍直接安裝 `transformers`，但 Trevor 核心實際不再需要本機重型模型堆疊。
- CI 與執行需求固定了舊版 `cryptography`、`requests`、`python-dotenv`。

## 修補

- 刪除 AirLLM 需求、修補工具、煙霧測試與舊操作手冊。
- 從 Trevor 核心需求移除 `torch`、`transformers`、`sentence-transformers` 與無修補版本的 `chromadb`。
- 升級至 `cryptography==50.0.0`、`requests==2.34.2`、`python-dotenv==1.2.3`，並重建 CI 鎖檔。
- 保留 FAISS、SQLite 與 Graphiti 作為記憶／檢索路徑，避免為未使用能力重新引入高風險套件。
- 啟用 GitHub secret scanning、push protection 與 Dependabot security updates；目前 secret scanning 開啟警示為 0。

## 驗證

- `pip-audit`：CI、核心執行、智能體擴充與 Graphiti sidecar 四組解析後依賴均回報 `No known vulnerabilities found`。
- 秘密掃描：606 個版本控制檔案通過。
- 自動測試：276 項全部通過。
- Git 差異檢查：`git diff --check` 通過。

## 後續控制

- Required CI 在合併前執行測試、秘密掃描及 Graphiti Linux 健康檢查。
- `main` 使用 branch protection、merge commit 與 auto-merge，不允許繞過失敗的必要檢查。
- 若未來需要本機模型執行，必須建立獨立 sidecar 與獨立鎖檔，不得直接加入 Trevor 核心執行環境。
