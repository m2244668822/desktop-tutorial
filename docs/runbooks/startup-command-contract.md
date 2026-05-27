# 啟動命令契約（永久記憶）

## 正確命令
```bash
python3 desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

## 常見誤用
- `--web-server` 在此版本不支援，會啟動失敗。

## 快速自檢
```bash
curl -s -o /tmp/status.json -w '%{http_code}\n' http://127.0.0.1:5001/status
```
應回 `200`。

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`ops/startup-contract`
- 次流程標籤：`ops/gateway-single-entry`
- 正相關判定：是（直接規範啟動命令，可降低開機失敗與端口偏移）
- 處置：維持運維主標籤，作為啟動流程根節點。
- 神經連結：
  - [[06_MOC_運維群組_2026-05-26]]
  - [[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]
  - [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]
