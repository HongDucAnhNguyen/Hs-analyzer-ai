#!/bin/bash

# ============================================
# CONFIGURATION - Adjust these settings here
# ============================================
DEFAULT_UVICORN_WORKERS=3     # Number of Uvicorn worker processes (CPU-bound, recommend CPU cores)
DEFAULT_CELERY_CONCURRENCY=3   # Number of concurrent Celery workers (I/O-bound, can be higher)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Starting Classification System ===${NC}"
echo ""
echo "⚠️  Prerequisites: Redis and RabbitMQ must be running!"
echo "   Start infrastructure: docker-compose -f ../docker-compose.base.yml up -d"
echo ""

# Step 1: Check if Redis and RabbitMQ are accessible
echo -e "${YELLOW}[1/3] Checking infrastructure...${NC}"
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}

if nc -z $REDIS_HOST $REDIS_PORT 2>/dev/null; then
    echo -e "${GREEN}✓ Redis is accessible at $REDIS_HOST:$REDIS_PORT${NC}"
else
    echo -e "${RED}✗ Redis is not accessible at $REDIS_HOST:$REDIS_PORT${NC}"
    echo "  Please start Redis first: docker-compose -f ../docker-compose.base.yml up -d"
    exit 1
fi

# Step 2: Start FastAPI in background
echo -e "${YELLOW}[2/3] Starting FastAPI API...${NC}"

# Kill existing processes if any
pkill -f "uvicorn classifier_service.main:app" 2>/dev/null

# Get absolute path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_PATH="$SCRIPT_DIR/.venv"
LOG_DIR="$SCRIPT_DIR/logs"

# Configure Uvicorn workers (can be overridden with environment variable)
UVICORN_WORKERS=${UVICORN_WORKERS:-$DEFAULT_UVICORN_WORKERS}

echo "Starting FastAPI with $UVICORN_WORKERS workers"

# Start API with multiple workers for better concurrency
nohup bash -c "source $VENV_PATH/bin/activate && cd $(dirname $SCRIPT_DIR) && uvicorn classifier_service.main:app --host 0.0.0.0 --port 3333 --workers $UVICORN_WORKERS" > $LOG_DIR/api.log 2>&1 &
API_PID=$!
echo $API_PID > $LOG_DIR/api.pid
echo -e "${GREEN}✓ FastAPI started (PID: $API_PID)${NC}"

# Wait a bit for API to start
sleep 3

# Step 3: Start Celery Worker in background
echo -e "${YELLOW}[3/3] Starting Celery Worker...${NC}"

# Kill existing workers if any
pkill -f "celery.*classifier_service.core.celery_app.*worker" 2>/dev/null

# Configure concurrency (can be overridden with environment variable)
# Default set at top of script, or use: CELERY_CONCURRENCY=8 ./start_all.sh
CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-$DEFAULT_CELERY_CONCURRENCY}

echo "Starting Celery with concurrency: $CELERY_CONCURRENCY"

# Start worker with higher concurrency for better throughput
nohup bash -c "source $VENV_PATH/bin/activate && cd $(dirname $SCRIPT_DIR) && celery -A classifier_service.core.celery_app worker --loglevel=info --concurrency=$CELERY_CONCURRENCY --pool=prefork" > $LOG_DIR/worker.log 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > $LOG_DIR/worker.pid
echo -e "${GREEN}✓ Celery Worker started (PID: $WORKER_PID)${NC}"

echo ""
echo -e "${GREEN}=== All Services Started ===${NC}"
echo ""
echo "📊 Service Status:"
echo "   Redis:        Running (docker ps | grep redis)"
echo "   FastAPI:      http://localhost:3333 with $UVICORN_WORKERS workers (PID: $API_PID)"
echo "   Celery:       Running with $CELERY_CONCURRENCY workers (PID: $WORKER_PID)"
echo ""
echo "📝 Logs:"
echo "   API:          tail -f classifier_service/logs/api.log"
echo "   Worker:       tail -f classifier_service/logs/worker.log"
echo ""
echo "🔗 Quick Links:"
echo "   API Docs:     http://localhost:3333/docs"
echo "   Health:       curl http://localhost:3333/"
echo ""
echo "🛑 To stop all services:"
echo "   cd classifier_service && ./stop_all.sh"
echo ""
echo "⚙️  To adjust workers:"
echo "   UVICORN_WORKERS=4 CELERY_CONCURRENCY=8 ./start_all.sh"
echo ""
