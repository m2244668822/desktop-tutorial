# Git 完整性與分支追蹤擴大紀錄

日期：2026-05-22

## 1) 為什麼 `empty object = 0` 不奇怪

`empty object = 0` 的意思是「壞掉的 0-byte Git 物件已清除」，不是「沒有 Git 物件」。

本次實測：

- `git fsck --full --no-reflogs`：OK
- `git count-objects -vH`：
  - `count: 51`
  - `size: 1.69 MiB`
  - `garbage: 0`

所以目前是「有正常物件，且沒有空壞檔」。

## 2) 分支追蹤擴大（已執行）

已把本地分支追蹤擴大到所有遠端 `origin/*`：

- `codex/backend-mainline` -> `origin/codex/backend-mainline`
- `codex/db-migration-postgres` -> `origin/codex/db-migration-postgres`
- `codex/frontend-showcase` -> `origin/codex/frontend-showcase`
- `codex/git-governance-20260517` -> `origin/codex/git-governance-20260517`
- `main` -> `origin/main`
- `showcase-upload-20260514` -> `origin/showcase-upload-20260514`

各分支目前可見追蹤檔案數：

- `codex/git-governance-20260517`: 5
- `main`: 21
- `codex/backend-mainline`: 21
- `codex/db-migration-postgres`: 21
- `codex/frontend-showcase`: 21
- `showcase-upload-20260514`: 21

## 3) 建議後續檢查

```bash
git fetch --all --prune
git branch -vv
git for-each-ref refs/remotes/origin --format='%(refname:short) -> %(objectname:short)'
```

如果之後需要把「目前大量未追蹤工作檔」納入版本控制，建議另開資料治理分支，分批納入，不要一次全加。
