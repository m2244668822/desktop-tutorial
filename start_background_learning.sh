#!/bin/bash
# 背景啟動連續自主學習引擎

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.autonomous_learning.pid"
LOG_FILE="$SCRIPT_DIR/logs/autonomous_learning_background.log"

cd "$SCRIPT_DIR" || exit 1

# 確保 logs 目錄存在
mkdir -p "$SCRIPT_DIR/logs"

# 檢查是否已經在運行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "❌ 連續學習已在背景運行中 (PID: $OLD_PID)"
        echo "   使用 ./stop_background_learning.sh 停止"
        exit 1
    else
        # PID 文件存在但進程不存在，清理舊文件
        rm -f "$PID_FILE"
    fi
fi

echo "🚀 啟動背景連續自主學習..."
echo "   日誌: $LOG_FILE"
echo "   停止指令: ./stop_background_learning.sh"
echo ""

# 設定 API 密鑰
if [ -f "$SCRIPT_DIR/config/gemini_config.json" ]; then
    GEMINI_API_KEY=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config/gemini_config.json'))['api_key'])")
    export GEMINI_API_KEY
    echo "   ✅ Gemini API 密鑰已設定"
fi

# 在背景啟動（使用 -u 參數確保即時輸出）
nohup python3 -u "$SCRIPT_DIR/autonomous_continuous_learning.py" \
    --continuous \
    --interval 10.0 \
    > "$LOG_FILE" 2>&1 &

PID=$!
echo $PID > "$PID_FILE"

echo "✅ 已啟動 (PID: $PID)"
echo "   查看即時日誌: tail -f $LOG_FILE"
