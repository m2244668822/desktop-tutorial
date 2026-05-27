#!/bin/bash
# 停止背景運行的連續自主學習引擎

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.autonomous_learning.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "❌ 找不到運行中的背景學習進程"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "❌ 進程 (PID: $PID) 已不存在"
    rm -f "$PID_FILE"
    exit 1
fi

echo "🛑 正在停止背景學習 (PID: $PID)..."

# 發送 SIGINT 信號（等同於 Ctrl+C），讓程式正常保存
kill -INT "$PID"

# 等待最多 10 秒
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ 已成功停止並保存學習記錄"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 如果還沒停止，強制終止
echo "⚠️ 正常停止超時，強制終止..."
kill -9 "$PID"
rm -f "$PID_FILE"
echo "✅ 已強制停止"
