# MOC：單一入口與分支治理

## 生活化理解
把系統想成百貨公司：
- 單一入口 = 所有人都走一樓服務台（5001）。
- 分支治理 = 施工都先在施工區（feature/training branch），驗收後才開放到主商場。

## 規則
1. 前端只打 `5001`。
2. n8n 永遠獨立常駐 `5678`。
3. 新訓練與高風險優化都走 training branch。
4. 主分支只收「已驗證」結果。

## 日常檢查
- [ ] `/status` 是否 200
- [ ] `/api/gateway/policy` 是否 200
- [ ] `5678` 是否 listen
- [ ] 今日 commit 是否有回歸測試記錄

## 關聯
- [[00_智能體中樞儀表板]]
- [[01_專案全貌與進度總覽_2026-05-25]]
- [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]
- [[ProjectDocs/dev/GIT_INTEGRITY_AND_BRANCH_TRACKING_2026-05-22]]
