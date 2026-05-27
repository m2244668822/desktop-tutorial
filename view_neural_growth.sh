#!/bin/bash
# 查看神經系統成長狀態

echo "🧠 神經系統成長追蹤器"
echo "===================="
echo ""

python3 tools/view_neural_growth.py

echo ""
echo "💡 提示: 查看詳細日誌文件:"
echo "   - logs/neural_growth_log.json      (成長事件記錄)"
echo "   - logs/connection_usage.json       (連接使用統計)"
