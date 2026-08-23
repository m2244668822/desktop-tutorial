#!/bin/bash
# 神經系統漸進式維護腳本
# 定期運行以強化活躍的神經連接

echo "🧠 神經系統漸進式維護"
echo ""

# 檢查參數
if [ "$1" = "--status" ]; then
    python3 tools/progressive_neural_maintenance.py --status-only
else
    echo "這將分析和強化您的神經系統連接..."
    echo ""
    python3 tools/progressive_neural_maintenance.py
fi

echo ""
echo "💡 建議:"
echo "   - 每 100 個新對話後運行一次"
echo "   - 或每週運行一次以優化系統"
echo ""
echo "   快速檢查: ./maintain_neural_system.sh --status"
