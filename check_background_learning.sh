#!/bin/bash
# 檢查背景學習狀態

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.autonomous_learning.pid"
LOG_FILE="$SCRIPT_DIR/logs/autonomous_learning_background.log"

echo "=========================================="
echo "  背景學習狀態檢查"
echo "=========================================="
echo ""

if [ ! -f "$PID_FILE" ]; then
    echo "❌ 沒有運行中的背景學習"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "❌ 進程 (PID: $PID) 已停止"
    rm -f "$PID_FILE"
    exit 0
fi

echo "✅ 背景學習運行中"
echo "   PID: $PID"
echo ""

# 顯示進程信息
echo "📊 進程資訊:"
ps -p "$PID" -o pid,etime,rss,args

echo ""
echo "📝 最近 10 行日誌:"
echo "----------------------------------------"
tail -n 10 "$LOG_FILE"
echo "----------------------------------------"
echo ""
echo "查看完整日誌: tail -f $LOG_FILE"
