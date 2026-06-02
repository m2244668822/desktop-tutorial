# Branch Protection Policy（私有展示版）

適用 repo：`m2244668822/desktop-tutorial`（Private）

## 目標

- 防止未驗證變更直接進 `main`
- 強制 PR 審查與可追溯驗證
- 與智能體自運作 Git 流程對齊

---

## Protected Branch

主要保護分支：`main`

建議次要保護分支（可選）：
- `codex/backend-mainline`
- `codex/frontend-showcase`
- `codex/db-migration-postgres`

---

## `main` 建議規則

### Pull request gate
- Require a pull request before merging: **ON**
- Require approvals: **1**（單人維運可先 0，建議 1）
- Dismiss stale approvals when new commits are pushed: **ON**
- Require conversation resolution before merging: **ON**

### Status checks gate
- Require status checks to pass before merging: **ON**
- Required checks 建議：
  - `autopilot-plan`（若你加 CI 工作）
  - `autopilot-guard`（若你加 CI 工作）
  - `verification-report`（若你加 CI 工作）
- Require branches to be up to date before merging: **ON**

### Safety gate
- Restrict who can push to matching branches: **只保留你自己**
- Do not allow bypassing the above settings: **ON**
- Allow force pushes: **OFF**（除非你在做歷史整理）
- Allow deletions: **OFF**

---

## Actions Policy（搭配你目前設定）

建議：
- `Allow m2244668822 actions and reusable workflows`
- `Require actions to be pinned to a full-length commit SHA` = **ON**

---

## 與 Autopilot Hook 對齊

本機已啟用：
- `.githooks/pre-commit`
- `.githooks/commit-msg`
- `.githooks/pre-push`

建議 push 前使用：

```bash
python3 tools/agent_git_autopilot.py plan
python3 tools/agent_git_autopilot.py guard
GIT_AUTOPILOT_STRICT_PUSH=1 git push
```

---

## 建議 PR 流程

1. Autopilot 自動判斷領域並切分支：

```bash
python3 tools/agent_git_autopilot.py checkout --suffix <task>
```

2. 完成改動並提交（commit-msg hook 會檢查格式）
3. 推送後開 PR（自動套用 `.github/pull_request_template.md`）
4. 依模板填寫驗證證據與風險說明
5. 合併到 `main`

---

## 上線前最低門檻

- [ ] PR 模板驗證欄位皆填寫
- [ ] `tools/run_full_verification.sh` 有最新報告
- [ ] 敏感資料掃描無異常
- [ ] DB 改動有回滾路徑
