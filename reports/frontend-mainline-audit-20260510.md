# Frontend Mainline Audit — 2026-05-10

## 結論

使用者目前實際主用前端不是 `desktop_chat_app.py --web-server`，而是：

- `https://perob.com:5443/Perob`
- 對應後端：`/Users/user/Desktop/城城城程式/chatgpt_server.py`
- 對應模板：`/Users/user/Desktop/城城城程式/templates/chat.html`

`/Perob` 路由在 `chatgpt_server.py` 中明確定義為：

```python
@app.route('/')
@app.route('/Perob')
@app.route('/Perob/')
def index():
    return render_template('chat.html')
```

## 已驗證

- 已抓取遠端部署頁面：`logs/browser-check/deployed-perob.html`
- 已比對三份模板：
  - `logs/browser-check/deployed-perob.html`
  - `templates/chat.html`
  - `/Users/user/Desktop/城城城程式/templates/chat.html`

比對結果：

- 部署頁面幾乎等於 `/Users/user/Desktop/城城城程式/templates/chat.html`
- 與目前 workspace 的 `templates/chat.html` 有大幅差異

## 主線保留

這些檔案是使用者目前實際主線的一部分，不應刪除：

- `/Users/user/Desktop/城城城程式/chatgpt_server.py`
- `/Users/user/Desktop/城城城程式/templates/chat.html`

## Workspace 內非主線前端

以下檔案位於目前 workspace `/Volumes/智能體/城城城程式`，但不是使用者目前主用的 `Perob` 前端主線：

- `templates/chat.html`
- `templates/chat_shell.html`
- `templates/monitor_shell.html`
- `templates/agent_shell.html`
- `templates/visual_template.html`

## 刪除風險分級

### 可直接標記廢棄

這些檔案對目前 `Perob` 主線沒有作用，可優先標記 deprecated：

- `templates/chat_shell.html`
- `templates/monitor_shell.html`
- `templates/agent_shell.html`
- `templates/visual_template.html`

理由：

- 它們屬於 `desktop_chat_app.py` 這條分支
- 不被 `chatgpt_server.py /Perob` 使用
- `agent_shell.html` 在 `desktop_chat_app.py --web-server` 下也不是主入口，而是多視窗/本地用途
- `visual_template.html` 為空檔

### 不建議直接刪除，應先比對後處理

- `templates/chat.html`

理由：

- 雖然不是 `Perob` 現行主線
- 但它曾被用於 `desktop_chat_app.py --unified`
- 內容與實際部署版不同，仍有參考/遷移價值

建議先做：

1. 若要完全收斂到 `Perob`，先備份
2. 再決定是刪除、覆蓋，或只留廢棄說明

## 實際建議

若目標是「只保留使用者現在真的在用的 web server 前端」：

1. 保留桌面專案主線：
   - `/Users/user/Desktop/城城城程式/chatgpt_server.py`
   - `/Users/user/Desktop/城城城程式/templates/chat.html`
2. 在目前 workspace 先標記以下為廢棄，而不是立刻刪除：
   - `templates/chat_shell.html`
   - `templates/monitor_shell.html`
   - `templates/agent_shell.html`
   - `templates/visual_template.html`
3. `templates/chat.html` 最後處理

## 下一步

若要正式清理，建議順序：

1. 先在 workspace 模板檔案頂部加上 `DEPRECATED` 註記
2. 再把 `desktop_chat_app.py` 相關說明一起改成「非主線」
3. 最後才做實體刪除
