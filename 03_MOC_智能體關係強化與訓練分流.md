# MOC：智能體關係強化與訓練分流

## 生活化理解
把智能體團隊想成球隊：
- 每次對話 = 一次進攻回合
- 關鍵字檢索 = 看戰術板
- 回寫摘要 = 賽後記錄
- 訓練分流 = 練習賽，不直接改正式賽戰術

## 每輪對話固定流程
1. 抽關鍵字（topic + keywords + phrase）
2. 檢索知識（Knowledge Hub）
3. 生成回覆（含防重複）
4. 回寫關係（turn/edge JSONL）
5. 訓練分流（training overlay JSONL）

## 目標
- 對話不孤島
- 關係圖可增強
- 主線穩定、訓練獨立

## 關聯
- [[Templates/對話回寫模板]]
- [[04_關係圖強化操作清單]]
- [[ProjectDocs/dev/AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25]]
- [[07_MOC_訓練群組_2026-05-26]]
- [[06_MOC_運維群組_2026-05-26]]
- [[08_關係圖更新紀錄_2026-05-26]]
