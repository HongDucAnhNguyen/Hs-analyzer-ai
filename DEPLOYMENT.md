# Unified API Deployment Guide

This guide explains how to deploy and run the unified HS Code API that combines both RAG and Classifier services into a single application.

## Overview

The unified API (`main.py`) imports and combines endpoints from both services:
- **RAG Service**: HS Code search using Retrieval-Augmented Generation
- **Classifier Service**: Product classification into HS Code hierarchy

## Architecture

```
main.py (Port 8081)
├── /api/v1/search/*        → RAG Service endpoints
├── /api/v1/classify/*      → Classifier Service endpoints
└── /api/v1/cache/*         → Classifier cache endpoints
```

## Prerequisites

- Python 3.11+
- UV package manager
- Docker & Docker Compose (for containerized deployment)
- Redis (for caching)
- RabbitMQ (for async tasks)

## Quick Start

### Option 1: Full Stack with Docker Compose (Recommended)

1. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env and add your API keys
```

2. **Start all services (including Qdrant):**
```bash
make start-all-local
# or
docker compose -f docker-compose-full.yml up -d
```

3. **Access the API:**
- API: http://localhost:8081
- Documentation: http://localhost:8081/docs
- Flower UI: http://localhost:5555
- Qdrant: http://localhost:6333
- RabbitMQ Management: http://localhost:15672 (admin/admin123)

### Option 2: Local Development

1. **Install dependencies:**
```bash
make install
# or
uv sync
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Start Redis and RabbitMQ:**
```bash
docker-compose up -d redis rabbitmq
```

4. **Run the API:**
```bash
# Development mode (with hot reload)
make dev

# Production mode
make run
```

## Available Make Commands

### Local Development
```bash
make install          # Install dependencies with uv
make dev              # Run in development mode (hot reload)
make run              # Run in production mode
make build            # Build Docker image
make up               # Start all services with docker-compose
make down             # Stop all services
make logs             # View logs
make clean            # Clean up containers and volumes
make test             # Test API endpoints
make start-all-local  # Start all services locally (including Qdrant)
```

### Remote Deployment
```bash
make deploy h=<host> dir=<remote_dir>                    # Deploy code to remote server
make restart-app h=<host> dir=<remote_dir>               # Restart app only (preserves Qdrant)
make deploy-dev                                           # Deploy to dev server (34.143.173.34)
make deploy-prod                                          # Deploy to production server
make start-all-remote h=<host> dir=<remote_dir>          # Start all services including Qdrant
make sync-qdrant-from-remote h=<host> dir=<remote_dir>   # Download Qdrant data from remote
make sync-qdrant-to-remote h=<host> dir=<remote_dir>     # Upload Qdrant data to remote
```

## API Endpoints

### General Endpoints
- `GET /` - Welcome message with service info
- `GET /health` - Health check for all services
- `GET /services` - List all available endpoints
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

### RAG Service Endpoints
- `POST /api/v1/search/hscode` - Search for HS codes using natural language

### Classifier Service Endpoints
- `POST /api/v1/classify/` - Synchronous classification
- `POST /api/v1/classify/async` - Asynchronous classification
- `GET /api/v1/classify/async/{task_id}` - Get async task status
- `GET /api/v1/cache/stats` - Get cache statistics
- `POST /api/v1/cache/clear` - Clear cache

## Environment Variables

### Core Configuration
- `API_HOST` - API host (default: 0.0.0.0)
- `API_PORT` - API port (default: 8081)
- `API_WORKERS` - Number of workers (default: 4)
- `DEBUG` - Debug mode (default: False)

### LLM Configuration
- `OPENAI_API_KEY` - OpenAI API key
- `GEMINI_API_KEY` - Google Gemini API key
- `ANTHROPIC_API_KEY` - Anthropic Claude API key
- `COHERE_API_KEY` - Cohere API key
- `LLM_PROVIDER` - LLM provider (gemini, openai, anthropic)
- `LLM_MODEL` - Model name for RAG service
- `CLASSIFIER_LLM_MODEL` - Model name for classifier service

### Database Configuration
- `QDRANT_HOST` - Qdrant vector DB host
- `QDRANT_PORT` - Qdrant port (default: 6333)
- `QDRANT_COLLECTION` - Collection name
- `REDIS_URL` - Redis connection URL
- `RABBITMQ_URL` - RabbitMQ connection URL

## Docker Services

### Full Stack (`docker-compose-full.yml`)

1. **qdrant**: Vector database (ports 6333, 6334)
   - Persistent storage: `./qdrant_data`
2. **redis**: Cache and Celery backend (port 6379)
   - Persistent storage: Docker volume `redis_data`
3. **rabbitmq**: Message broker (ports 5672, 15672)
   - Persistent storage: Docker volume `rabbitmq_data`
4. **unified-api**: Main API gateway (port 8081)
5. **classifier-worker**: Celery worker for async tasks
6. **classifier-flower**: Celery monitoring UI (port 5555)

### App Only (`docker-compose.server.yml`)

1. **unified-api**: Main API gateway (port 8081)
   - Connects to existing Qdrant, Redis, RabbitMQ on host
2. **classifier-worker**: Celery worker for async tasks
3. **classifier-flower**: Celery monitoring UI (port 5555)

## Monitoring

### Application Logs
```bash
# All services
docker-compose logs -f

# Unified API only
docker-compose logs -f unified-api

# Worker only
docker-compose logs -f classifier-worker
```

### Celery Tasks
- Access Flower UI at http://localhost:5555
- Monitor task execution, success/failure rates
- View worker status and active tasks

### RabbitMQ
- Management UI: http://localhost:15672
- Default credentials: admin/admin123
- Monitor queues, exchanges, and connections

## Testing

### Manual Testing
```bash
# Test root endpoint
curl http://localhost:8081/

# Test health check
curl http://localhost:8081/health

# Test RAG search
curl -X POST http://localhost:8081/api/v1/search/hscode \
  -H "Content-Type: application/json" \
  -d '{"query": "laptop computer"}'

# Test classification
curl -X POST http://localhost:8081/api/v1/classify/ \
  -H "Content-Type: application/json" \
  -d '{"product_description": "laptop computer"}'
```

### Using Make
```bash
make test
```

## Troubleshooting

### Port Already in Use
```bash
# Check what's using port 8081
lsof -i :8081

# Stop existing services
make down
```

### Service Not Starting
```bash
# Check logs
docker-compose logs unified-api

# Rebuild
docker-compose build --no-cache
docker-compose up -d
```

### Missing Dependencies
```bash
# Reinstall with uv
uv sync --force
```

## Production Deployment

### Deployment Strategy

There are two Docker Compose files for different deployment scenarios:

#### 1. `docker-compose-full.yml` - Complete Stack
Use this for **initial setup** or when deploying to a **new server**. Includes ALL services:
- ✅ Qdrant (with persistent storage in `./qdrant_data`)
- ✅ Redis (with persistent volumes)
- ✅ RabbitMQ (with persistent volumes)
- ✅ Unified API
- ✅ Celery Worker
- ✅ Celery Flower

```bash
# Start all services locally
make start-all-local

# Start all services on remote server
make start-all-remote h=34.143.173.34 dir=/home/truong95k58/unified_api
```

#### 2. `docker-compose.server.yml` - App Only (for updates)
Use this for **regular deployments** when you want to update the API without restarting infrastructure services. This assumes Qdrant, Redis, and RabbitMQ are already running.

```bash
# Deploy and restart only the API and workers
make deploy-dev

# Or manually
make deploy h=34.143.173.34 dir=/home/truong95k58/unified_api
make restart-app h=34.143.173.34 dir=/home/truong95k58/unified_api
```

### Initial Server Setup

For a completely new server:

1. **Deploy code and start all services:**
```bash
# Option 1: Using Make commands
make deploy h=34.143.173.34 dir=/home/truong95k58/unified_api
make start-all-remote h=34.143.173.34 dir=/home/truong95k58/unified_api

# Option 2: Manual steps
ssh user@server
cd /home/truong95k58/unified_api
cp .env.example .env
# Edit .env with your API keys
docker compose -f docker-compose-full.yml up -d
```

2. **Initialize Qdrant collections (first time only):**
```bash
# SSH into the server
ssh user@server
cd /home/truong95k58/unified_api/rag_service

# Generate embeddings for your data
python3 core/db_builder/vector_db/ingestion/ingest_asean_gemini.py
python3 core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
```

3. **Verify services:**
```bash
# Check all services are running
docker compose -f docker-compose-full.yml ps

# Check Qdrant has collections
curl http://server-ip:6333/collections
```

### Regular Updates (Preserving Vector DB)

When you pull new changes from develop branch and want to deploy:

```bash
# This will:
# 1. Deploy your code to the server
# 2. Restart ONLY the API, worker, and flower containers
# 3. Keep Qdrant running (preserves your vector database)
make deploy-dev
```

**Important:** The `qdrant_data` directory is **NOT** excluded from deployment, so if you want to sync Qdrant data between environments, it will be copied. If you don't want this, the data will persist on the server in `./qdrant_data`.

### Qdrant Data Persistence

The Qdrant vector database stores all collections in `./qdrant_data` directory:
- ✅ Data persists across container restarts
- ✅ Data persists across code deployments
- ✅ No need to regenerate embeddings on every deployment
- ✅ Can backup/restore by copying `qdrant_data` directory

#### Syncing Qdrant Data Between Environments

**Download Qdrant data from remote server to local:**
```bash
# From dev server
make sync-qdrant-from-remote h=34.143.173.34 dir=/home/truong95k58/unified_api

# From custom server
make sync-qdrant-from-remote h=<host> dir=<remote_dir>
```

**Upload local Qdrant data to remote server:**
```bash
# To dev server
make sync-qdrant-to-remote h=34.143.173.34 dir=/home/truong95k58/unified_api

# To custom server
make sync-qdrant-to-remote h=<host> dir=<remote_dir>
```

**Note:** `sync-qdrant-to-remote` will temporarily stop Qdrant on the remote server during sync, then restart it automatically.

#### Manual Backup/Restore

```bash
# Backup Qdrant data
tar -czf qdrant_backup_$(date +%Y%m%d).tar.gz qdrant_data/

# Restore Qdrant data
tar -xzf qdrant_backup_20231209.tar.gz
```

### Deployment Workflow

**Scenario 1: First time deployment**
```bash
make deploy h=34.143.173.34 dir=/home/truong95k58/unified_api
make start-all-remote h=34.143.173.34 dir=/home/truong95k58/unified_api
# Then generate embeddings (one-time)
```

**Scenario 2: Code updates (most common)**
```bash
# Pull latest code locally
git pull origin develop

# Deploy (Qdrant stays running)
make deploy-dev
```

**Scenario 3: Infrastructure changes**
```bash
# If you need to update Qdrant/Redis/RabbitMQ versions
ssh user@server
cd /home/truong95k58/unified_api
docker compose -f docker-compose-full.yml down
docker compose -f docker-compose-full.yml up -d
```

### Security Considerations
1. Update CORS origins in `main.py`
2. Use environment variables for all secrets
3. Enable HTTPS/TLS
4. Set up proper firewall rules
5. Use strong passwords for RabbitMQ
6. Restrict Qdrant port (6333) to internal network only

### Scaling
- Increase `API_WORKERS` for more concurrent requests
- Scale Celery workers: `docker compose up -d --scale classifier-worker=4`
- Use external Redis/RabbitMQ for high availability
- Consider separate Qdrant cluster for production

### Performance
- Enable Redis persistence (already configured in docker-compose-full.yml)
- Configure Celery worker concurrency
- Adjust worker timeouts for long-running tasks
- Monitor memory usage
- Qdrant data is memory-mapped for fast access

## Differences from Nginx Setup

The previous setup used Nginx as a reverse proxy routing to separate service containers. This unified approach:

**Advantages:**
- ✅ Simpler deployment (one application instead of 3)
- ✅ No proxy overhead
- ✅ Direct service communication
- ✅ Easier debugging and logging
- ✅ Shared dependencies and configuration

**Considerations:**
- Services run in the same process
- Shared memory space (monitor resource usage)
- No service-level isolation

## Support

For issues or questions:
1. Check the logs: `make logs`
2. Review the API documentation: http://localhost:8081/docs
3. Test individual endpoints with the built-in Swagger UI
