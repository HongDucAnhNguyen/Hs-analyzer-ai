#!/bin/bash
# Run script for HS CODE API
# Provides easy commands to run the application in different modes

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
HOST=${API_HOST:-0.0.0.0}
PORT=${API_PORT:-8386}
WORKERS=${API_WORKERS:-4}
APP_MODULE="rag_service.main:app"

function show_help {
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start the application in production mode (single instance)"
    echo "  prod        Start the application in production mode with workers"
    echo "  dev         Start the application in development mode with auto-reload"
    echo "  test        Run tests"
    echo "  clean       Clean up cache files"
    echo "  help        Show this help message"
    echo ""
}

# Check if the script is being run with executable permissions
if [ ! -x "$0" ]; then
    chmod +x "$0"
    echo "Made script executable"
fi

case "$1" in
    prod)
        echo "Starting production server with $WORKERS workers on $HOST:$PORT..."
        gunicorn $APP_MODULE --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker --bind $HOST:$PORT
        ;;
    start)
        echo "Starting server on $HOST:$PORT..."
        uvicorn $APP_MODULE --host $HOST --port $PORT
        ;;
    dev)
        echo "Starting development server on $HOST:$PORT with auto-reload..."
        uvicorn $APP_MODULE --reload --host $HOST --port $PORT
        ;;
    test)
        echo "Running tests..."
        python -m pytest tests/
        ;;
    clean)
        echo "Cleaning up cache files..."
        find . -type d -name "__pycache__" -exec rm -rf {} +
        find . -type d -name ".pytest_cache" -exec rm -rf {} +
        find . -type d -name ".mypy_cache" -exec rm -rf {} +
        find . -type f -name "*.pyc" -delete
        echo "Clean complete"
        ;;
    help|*)
        show_help
        ;;
esac