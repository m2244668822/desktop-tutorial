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
