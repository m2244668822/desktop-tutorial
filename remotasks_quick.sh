#!/bin/bash
# Remotasks 收益管理快速工具集
# 用法: ./remotasks_quick.sh [command]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 顏色定義
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

show_help() {
    echo -e "${BLUE}Remotasks 收益管理工具${NC}"
    echo ""
    echo "用法: ./remotasks_quick.sh [命令]"
    echo ""
    echo "命令:"
    echo "  add          新增收益記錄（互動式）"
    echo "  list         顯示最近記錄"
    echo "  summary      顯示收益摘要"
    echo "  daily        生成今日報告"
    echo "  weekly       生成本週報告"
    echo "  export       導出 CSV（30天）"
    echo "  help         顯示此說明"
    echo ""
    echo "範例:"
    echo "  ./remotasks_quick.sh add"
    echo "  ./remotasks_quick.sh daily"
}

add_entry() {
    echo -e "${BLUE}=== 新增收益記錄 ===${NC}"
    echo ""
    
    # 互動式輸入
    read -p "任務 ID (例: RT-20260301-001): " task_id
    read -p "任務類別 (例: image_annotation): " category
    read -p "工時 (小時): " hours
    read -p "收益 (USD): " amount_usd
    read -p "狀態 [pending/paid] (預設: pending): " status
    status=${status:-pending}
    read -p "備註 (可選): " note
    
    echo ""
    echo -e "${YELLOW}新增中...${NC}"
    
    python3 tools/remotasks_revenue_tracker.py add \
        --task-id "$task_id" \
        --category "$category" \
        --hours "$hours" \
        --amount-usd "$amount_usd" \
        --status "$status" \
        --note "$note"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 記錄已新增${NC}"
    else
        echo "❌ 新增失敗"
        exit 1
    fi
}

list_entries() {
    echo -e "${BLUE}=== 最近記錄 ===${NC}"
    python3 tools/remotasks_revenue_tracker.py list --limit 10
}

show_summary() {
    echo -e "${BLUE}=== 收益摘要 ===${NC}"
    python3 tools/remotasks_revenue_tracker.py summary
}

generate_daily() {
    echo -e "${BLUE}=== 生成每日報告 ===${NC}"
    python3 tools/remotasks_report_generator.py --type daily
    
    if [ $? -eq 0 ]; then
        latest_report=$(ls -t reports/remotasks_*_daily.md 2>/dev/null | head -1)
        if [ -n "$latest_report" ]; then
            echo ""
            echo -e "${GREEN}✅ 報告已生成: $latest_report${NC}"
            echo ""
            echo "預覽前 20 行:"
            head -20 "$latest_report"
        fi
    fi
}

generate_weekly() {
    echo -e "${BLUE}=== 生成每週報告 ===${NC}"
    python3 tools/remotasks_report_generator.py --type weekly
    
    if [ $? -eq 0 ]; then
        latest_report=$(ls -t reports/remotasks_*_weekly.md 2>/dev/null | head -1)
        if [ -n "$latest_report" ]; then
            echo ""
            echo -e "${GREEN}✅ 報告已生成: $latest_report${NC}"
            echo ""
            echo "預覽前 20 行:"
            head -20 "$latest_report"
        fi
    fi
}

export_csv() {
    echo -e "${BLUE}=== 導出 CSV (30天) ===${NC}"
    python3 tools/remotasks_report_generator.py --type csv --days 30
    
    if [ $? -eq 0 ]; then
        latest_csv=$(ls -t reports/remotasks_*_export.csv 2>/dev/null | head -1)
        if [ -n "$latest_csv" ]; then
            echo ""
            echo -e "${GREEN}✅ CSV 已導出: $latest_csv${NC}"
            echo ""
            echo "可用 Excel 或 Google Sheets 開啟此檔案"
        fi
    fi
}

# 主命令處理
case "${1:-help}" in
    add)
        add_entry
        ;;
    list)
        list_entries
        ;;
    summary)
        show_summary
        ;;
    daily)
        generate_daily
        ;;
    weekly)
        generate_weekly
        ;;
    export)
        export_csv
        ;;
    help|*)
        show_help
        ;;
esac
