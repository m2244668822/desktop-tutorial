# GitHub Branch Protection Checklist（`main`）

> 目標：保持「只有你可控」但仍具備品質閘門，避免壞改動直上 `main`。

## A. Repository 前置
- Repository visibility：`Private`
- Collaborators：目前 `0`（僅 owner）
- Default branch：`main`

## B. 建議保護規則（Rules / Branch protection）
對 `main` 建立規則：

1. **Require a pull request before merging**：`ON`
   - Solo 模式：可不強制 approval（避免只有自己時卡住）
   - 團隊模式：改為至少 `1` approval
2. **Require status checks to pass before merging**：`ON`
   - 先放最小檢查（例如 lint / smoke test）
3. **Require conversation resolution before merging**：`ON`
4. **Restrict force pushes**：`ON`
5. **Do not allow bypassing the above settings**：`ON`
6. **Include administrators**：`ON`（建議，避免熱修時忘了流程）

## C. 分支命名建議（跟智能體工作流對齊）
- `codex/frontend-*`
- `codex/backend-*`
- `codex/db-*`
- `codex/docs-*`
- `codex/integration-*`

## D. PR 內容最低標準
- 必填：`變更摘要 / 驗證紀錄 / Busy 保護 / 回滾方案`
- 若動到資料層：需附 migration 說明與風險
- 若動到前端事件：需註明是否有重複綁定防護

## E. 合併策略建議
- `Squash and merge`：`ON`（主線歷史乾淨）
- `Merge commit`：`OFF`（除非需要保留完整分支歷史）
- `Rebase merge`：可選

## F. 上線前最小檢查（M1 本機）
1. `./start_desktop_chat_app.sh health`
2. `./start_desktop_chat_app.sh web`
3. 開啟 `http://127.0.0.1:5001/Perob` 手動驗證核心頁面
4. 檢查 console/network 無連線錯誤與重複請求洪流

## G. 常見誤區
- 只看「已連線」燈號，不看實際 API 回傳
- 任務刷新鈕可連點造成併發炸裂
- 把 `logs/*.pid`、臨時素材、金鑰檔推上 repo

