# Git 自動化 + Skill 協作指南

## 核心原則
- 前端改動：優先 `frontend-skill` + `systematic-debugging`
- 後端改動：優先 `systematic-debugging` + `open-source-maintainer`
- 文件改動：優先 `internal-comms`

## 推薦流程（每次 PR）
1. 建分支（依範圍命名）
2. 小步提交（每個 commit 一個意圖）
3. 填寫 PR 模板（尤其 Busy 檢查）
4. 跑本地健康檢查
5. 再合併 `main`

## Busy 保護落地要點
- 任務輪詢一定要有 `interval + backoff + timeout`
- 相同按鈕觸發需有「執行中鎖」避免重入
- UI 狀態更新需要節流，避免 DOM 狂刷
- 非同步任務需可取消（AbortController / cancel token）

## 何時升級為團隊規則
當協作者 > 1 時，將 `main` 規則升級為：
- 必須 1 個 approval
- 必須過 CI
- 必須 resolve 對話
