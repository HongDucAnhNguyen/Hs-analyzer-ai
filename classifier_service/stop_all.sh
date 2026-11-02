#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Stopping Classification System ===${NC}"

# Get absolute path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$SCRIPT_DIR/logs"

# Stop FastAPI
echo -e "${YELLOW}[1/2] Stopping FastAPI...${NC}"
if [ -f $LOG_DIR/api.pid ]; then
    API_PID=$(cat $LOG_DIR/api.pid)
    if kill -0 $API_PID 2>/dev/null; then
        kill $API_PID
        echo -e "${GREEN}✓ FastAPI stopped (PID: $API_PID)${NC}"
    else
        echo "FastAPI not running"
    fi
    rm $LOG_DIR/api.pid
else
    # Try to kill by process name
    pkill -f "uvicorn classifier_service.main:app" 2>/dev/null
    echo -e "${GREEN}✓ FastAPI stopped${NC}"
fi

# Stop Celery Worker
echo -e "${YELLOW}[2/2] Stopping Celery Worker...${NC}"
if [ -f $LOG_DIR/worker.pid ]; then
    WORKER_PID=$(cat $LOG_DIR/worker.pid)
    if kill -0 $WORKER_PID 2>/dev/null; then
        kill $WORKER_PID
        echo -e "${GREEN}✓ Celery Worker stopped (PID: $WORKER_PID)${NC}"
    else
        echo "Celery Worker not running"
    fi
    rm $LOG_DIR/worker.pid
else
    # Try to kill by process name
    pkill -f "celery.*classifier_service.core.celery_app.*worker" 2>/dev/null
    echo -e "${GREEN}✓ Celery Worker stopped${NC}"
fi

echo ""
echo -e "${GREEN}=== All Services Stopped ===${NC}"
echo ""
echo "ℹ️  Redis and RabbitMQ are still running (managed by docker-compose)"
echo "   To stop infrastructure: docker-compose -f ../docker-compose.base.yml down"
echo ""
echo "To start again: cd classifier_service && ./start_all.sh"
echo ""
