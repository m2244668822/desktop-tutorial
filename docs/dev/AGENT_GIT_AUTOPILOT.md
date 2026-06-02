# Agent Git Autopilot（智能體 Git 自運作）

## 目標

讓智能體在 Git 協作時可以自動：

1. 判斷本次改動是前端 / 後端 / DB / 文件
2. 推薦分支前綴與對應 skill
3. 在推送前做守門檢查，避免把錯誤與髒資料推上去

---

## 指令

### 1) 產生自動計畫（plan）

```bash
python3 tools/agent_git_autopilot.py plan
```

輸出 JSON 包含：

- `domains`：改動領域
- `dominant_domain`：主領域
- `branch_prefix`：建議分支前綴
- `skills`：建議 skill（例如 `frontend-skill`, `systematic-debugging`）
- `checks`：建議執行檢查

### 2) 推送守門（guard）

```bash
python3 tools/agent_git_autopilot.py guard
```

- 會阻擋 runtime/generated 檔案（如 `logs/`, `tmp/`, `instance/`）被推送流程夾帶。

### 3) 嚴格守門（guard strict）

```bash
python3 tools/agent_git_autopilot.py guard --strict
```

- 除了基本阻擋，還會執行建議檢查（含整體驗證腳本）。

### 4) 自動切分支（checkout）

```bash
python3 tools/agent_git_autopilot.py checkout --suffix git-optimize
```

- 會依改動主領域自動套用分支前綴（例如 `codex/frontend-` / `codex/backend-` / `codex/db-`）。
- 若不提供 `--suffix`，會自動用時間戳建立分支。

---

## Hook 行為

### pre-commit

- Python 語法檢查
- staged 內容敏感字串掃描

### commit-msg

- 強制 Conventional Commit 格式：

```text
<type>(optional-scope): summary
```

範例：

```text
feat(backend): add postgres-first db metadata
```

### pre-push

- 預設：執行 `guard`（穩定模式）
- 若設定 `GIT_AUTOPILOT_STRICT_PUSH=1`，改執行 `guard --strict`

---

## Skill 對應策略

- `frontend` → `frontend-skill`, `systematic-debugging`
- `backend` → `systematic-debugging`, `open-source-maintainer`
- `db` → `systematic-debugging`
- `docs` → `internal-comms`
- `mixed` → `systematic-debugging`, `open-source-maintainer`, `internal-comms`

---

## 建議使用流程

1. 改完程式先跑 `plan` 看領域判斷
2. 依 `branch_prefix` 建分支
3. commit 前讓 hooks 自動檢查
4. push 前自動 guard
5. 發版前再跑一次完整驗證腳本
