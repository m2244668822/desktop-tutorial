#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡單的 HTTP 服務器 - 測試連接和啟動 desktop_chat_app
"""
import sys
import os
from pathlib import Path

# 設置路徑
BASE_DIR = Path(r"g:\城城城程式")
sys.path.insert(0, str(BASE_DIR))
os.chdir(str(BASE_DIR))

print("\n" + "="*70)
print("  🚀 AI 智能體協作系統 - Web 啟動器")
print("="*70 + "\n")

print(f"📂 工作目錄: {BASE_DIR}")
print(f"🐍 Python: {sys.version}")
print(f"📋 PID: {os.getpid()}\n")

# 第一步：驗證導入
print("✓ 步驟 1: 驗證導入...")
try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    print("  ✅ http.server 模塊可用")
except ImportError as e:
    print(f"  ❌ 導入失敗: {e}")
    sys.exit(1)

# 第二步：檢查 desktop_chat_app
print("\n✓ 步驟 2: 檢查 desktop_chat_app.py...")
chat_app = BASE_DIR / "desktop_chat_app.py"
if chat_app.exists():
    print(f"  ✅ 找到: {chat_app}")
else:
    print(f"  ❌ 找不到: {chat_app}")
    sys.exit(1)

# 第三步：嘗試導入
print("\n✓ 步驟 3: 嘗試導入 desktop_chat_app...")
try:
    import desktop_chat_app
    print("  ✅ 導入成功")
except Exception as e:
    print(f"  ⚠️  導入有警告: {e}")
    print("  但繼續嘗試啟動...")

# 第四步：建立簡單的測試服務器
print("\n✓ 步驟 4: 建立測試服務器 (port 5001)...")

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
<!DOCTYPE html>
<html>
<head>
    <title>✅ AI 智能體系統 - 連接成功</title>
    <meta charset="utf-8">
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #1e1e1e; color: #fff; padding: 40px; }
        .container { max-width: 600px; margin: 0 auto; text-align: center; }
        h1 { color: #4CAF50; }
        .info { background: #2d2d2d; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .status { color: #4CAF50; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✅ 系統連接成功</h1>
        <div class="info">
            <p>🎉 Web 服務器已正常運行</p>
            <p class="status">服務地址: http://127.0.0.1:5001</p>
        </div>
        <p>⏳ 正在加載完整應用...</p>
    </div>
</body>
</html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"  📡 {format % args}")

try:
    server = ThreadingHTTPServer(("127.0.0.1", 5001), SimpleHandler)
    print("  ✅ 服務器已建立\n")
    
    print("="*70)
    print("  🌐 服務已啟動！")
    print("="*70)
    print("\n📍 訪問地址: http://127.0.0.1:5001\n")
    print("💡 提示: 按 Ctrl+C 停止服務\n")
    
    # 自動打開瀏覽器
    try:
        import webbrowser
        print("🔄 正在打開瀏覽器...\n")
        webbrowser.open("http://127.0.0.1:5001")
    except:
        print("⚠️  無法自動打開瀏覽器，請手動訪問: http://127.0.0.1:5001\n")
    
    # 運行服務器
    server.serve_forever()
    
except KeyboardInterrupt:
    print("\n\n✅ 服務已停止")
    sys.exit(0)
except Exception as e:
    print(f"  ❌ 啟動失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
