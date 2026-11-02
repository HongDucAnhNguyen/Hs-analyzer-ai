#!/bin/bash

# Start script for Unified API

echo "🚀 Starting HS Code Unified API..."
echo "=================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ Created .env file. Please configure it with your API keys."
        echo "  Edit .env and add your API keys before starting."
        exit 1
    else
        echo "❌ .env.example not found!"
        exit 1
    fi
fi

# Check if running in development or production mode
MODE=${1:-prod}

if [ "$MODE" = "dev" ]; then
    echo "📦 Running in DEVELOPMENT mode with hot reload..."
    export DEBUG=True
    uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
else
    echo "🏭 Running in PRODUCTION mode..."
    uv run uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4
fi
