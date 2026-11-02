# HS Code Unified API

Unified API for HS Code search, classification, and web crawling using AI/ML technologies.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│      Unified API (Port 8081) - Single FastAPI        │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ RAG Service │  │ Classifier  │  │    Crawl    │   │
│  │  /search/*  │  │ /classify/* │  │   /crawl/*  │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└──────────┬──────────────────┬────────────────────────┘
           │                  │
           ▼                  ▼
    ┌─────────────┐    ┌──────────────────┐
    │   Qdrant    │    │ Redis + RabbitMQ │
    │  (Vector)   │    │     + Celery     │
    └─────────────┘    └──────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ with UV (for local development)
- 8GB+ RAM

### Option 1: Full Local Deployment

Start all services locally using docker-compose-full.yml:

```bash
make start-all-local
```

This starts:
- Unified API (Port 8081)
- Qdrant Vector DB (Port 6333)
- Redis, RabbitMQ, Celery Workers, Flower

**Access:**
- API: http://localhost:8081/docs
- Qdrant: http://localhost:6333/dashboard
- Flower: http://localhost:5555

### Option 2: Deploy to Remote Server

```bash
make deploy-dev
```

Deploys to development server (34.143.173.34).

### Configuration

Create `.env` file:

```bash
# Required API Keys
GEMINI_API_KEY=your-key
OPENAI_API_KEY=your-key

# Qdrant Configuration
QDRANT_HOST=localhost       # or remote IP
QDRANT_PORT=6333
# Collections: asean_openai, compendium_openai, asean_gemini, compendium_gemini

# LLM Configuration (switch between OpenAI and Gemini)
LLM_PROVIDER="openai"       # or "gemini"
LLM_MODEL="gpt-5.1"        # or "gemini-2.5-flash"
LLM_MODEL_NAME="gpt-5.1"   # Used by Classifier
LLM_TEMPERATURE="0.0"

# Infrastructure
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://admin:admin123@localhost:5672/
```

## 📡 Services

### 1. RAG Service - Semantic Search

Vector-based semantic search using Qdrant + LLM reasoning.

**ASEAN Search:** `POST /api/v1/search/asean`

```bash
curl -X POST http://localhost:8081/api/v1/search/asean \
  -F "product_name=laptop computer"
```

**Compendium Search:** `POST /api/v1/search/compendium`

```bash
curl -X POST http://localhost:8081/api/v1/search/compendium \
  -F "product_name=laptop computer"
```

### 2. Classifier Service - Hierarchical Classification

**Sync:** `POST /api/v1/classify/`
**Async:** `POST /api/v1/classify/async`

Step-by-step classification: Section → Chapter → Heading → Subheading.

```bash
curl -X POST http://localhost:8081/api/v1/classify/ \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "plastic chair",
    "material": "polypropylene"
  }'
```

### 3. Crawl Service - Web Data Extraction

#### A. HS Code Ruling Websites

**Endpoint:** `POST /api/v1/crawl/hs-ruling`

Searches official customs rulings from CBSA Canada, CARM Canada, US CBP, UK HMRC.

```bash
curl -X POST http://localhost:8081/api/v1/crawl/hs-ruling \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "coffee maker",
    "material": "plastic and metal"
  }'
```

#### B. HS Code Trade Databases

**Endpoint:** `POST /api/v1/crawl/hs_database`

Searches trade data from UK Trade Tariff, The Trade Vision, Zauba Shipment, Zauba USA.

```bash
curl -X POST http://localhost:8081/api/v1/crawl/hs_database \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "laptop computer",
    "material": "plastic and electronics"
  }'
```

## 🔧 Development

### Local Development

```bash
# Install dependencies
make install

# Run in dev mode (hot reload)
make dev

# Or start specific components
docker compose up -d redis rabbitmq
./start.sh dev
```

### Managing Qdrant Data

**Download from remote:**
```bash
make sync-qdrant-from-remote h=34.143.173.34 dir=/home/truong95k58/unified_api
```

**Upload to remote:**
```bash
make sync-qdrant-to-remote h=34.143.173.34 dir=/home/truong95k58/unified_api
```

### Data Ingestion

Ingest HS code data into Qdrant using scripts in `rag_service/core/db_builder/vector_db/ingestion/`:

```bash
# ASEAN data with OpenAI embeddings
python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_openai.py

# ASEAN data with Gemini embeddings
python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_gemini.py

# Compendium data with OpenAI embeddings
python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py

# Compendium data with Gemini embeddings
python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
```

## 📁 Project Structure

```
unified_api/
├── main.py                    # Main FastAPI application
├── Makefile                   # Build and deployment commands
├── docker-compose-full.yml    # Full stack (includes Qdrant)
├── docker-compose.server.yml  # Server deployment (remote Qdrant)
│
├── rag_service/               # RAG semantic search
│   ├── api/v1/
│   ├── core/
│   │   ├── service/           # Search logic
│   │   ├── db_builder/
│   │   │   └── vector_db/ingestion/  # Data ingestion scripts
│   │   └── embeddings/        # Gemini/OpenAI embeddings
│
├── classifier_service/        # Hierarchical classification
│   ├── api/v1/
│   ├── services/
│   └── core/celery_app.py     # Async task processing
│
└── crawl_service/             # Web crawling
    ├── api/v1/
    ├── core/
    │   ├── orchestrator.py            # Ruling websites
    │   └── hs_database_orchestrator.py # Trade databases
    ├── crawlers/
    │   ├── cbsa_canada.py
    │   ├── us_cbp.py
    │   └── hs_databases/
    │       ├── zauba_shipment.py
    │       └── uk_trade_tariff.py
    └── tests/                  # Test files and docs
```

## 📋 Makefile Commands

```bash
# Local Development
make start-all-local          # Start full stack locally
make dev                      # Run API in dev mode
make install                  # Install dependencies

# Deployment
make deploy-dev               # Deploy to dev server
make deploy h=<host> dir=<dir> # Deploy to custom server

# Qdrant Sync
make sync-qdrant-from-remote h=<host> dir=<dir>
make sync-qdrant-to-remote h=<host> dir=<dir>

# Docker
make build                    # Build images
make up                       # Start services
make down                     # Stop services
make logs                     # View logs
```

## ⚙️ Important Notes

### LLM Provider Configuration

Switch between OpenAI and Gemini by changing `LLM_PROVIDER`:

**For OpenAI:**
```bash
LLM_PROVIDER="openai"
LLM_MODEL="gpt-5.1"
LLM_MODEL_NAME="gpt-5.1"
```

**For Gemini:**
```bash
LLM_PROVIDER="gemini"
LLM_MODEL="gemini-2.5-flash"
LLM_MODEL_NAME="gemini-2.5-flash"
```

All services (RAG, Classifier, Crawl) use `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_MODEL_NAME`.

### Qdrant Collections

Available collections on server:
- `asean_openai` / `asean_gemini`
- `compendium_openai` / `compendium_gemini`

Choose collection based on your embedding model (OpenAI or Gemini).

### Cloudflare Bypass

Crawl service uses Botasaurus with Xvfb for browser automation.
Browser profiles stored in `profiles/` directory.

## 🔗 Service URLs

- **API Documentation**: http://localhost:8081/docs
- **Qdrant Dashboard**: http://localhost:6333/dashboard
- **Celery Flower**: http://localhost:5555
- **RabbitMQ**: http://localhost:15672
