#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$SCRIPT_DIR/logs"

echo -e "${GREEN}=== Viewing Classification System Logs ===${NC}"
echo ""
echo "Chọn log muốn xem:"
echo "  1) API logs"
echo "  2) Worker logs"
echo "  3) Both (split screen)"
echo ""
read -p "Nhập lựa chọn (1-3): " choice

case $choice in
    1)
        echo -e "${YELLOW}Đang xem API logs... (Ctrl+C để thoát)${NC}"
        tail -f $LOG_DIR/api.log
        ;;
    2)
        echo -e "${YELLOW}Đang xem Worker logs... (Ctrl+C để thoát)${NC}"
        tail -f $LOG_DIR/worker.log
        ;;
    3)
        echo -e "${YELLOW}Đang xem cả 2 logs... (Ctrl+C để thoát)${NC}"
        echo ""
        # Using multitail if available, otherwise tail both
        if command -v multitail &> /dev/null; then
            multitail -s 2 -l "tail -f $LOG_DIR/api.log" -l "tail -f $LOG_DIR/worker.log"
        else
            # Split terminal view
            tail -f $LOG_DIR/api.log $LOG_DIR/worker.log
        fi
        ;;
    *)
        echo "Lựa chọn không hợp lệ!"
        exit 1
        ;;
esac
