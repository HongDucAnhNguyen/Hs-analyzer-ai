
# Smart HS Code Search AI

An intelligent API for searching Harmonized System (HS) codes using AI.

## Prerequisites

* [Docker](https://www.docker.com/get-started)
* [Docker Compose](https://docs.docker.com/compose/install/)
* **External Services**: This application requires connections to the following services. Please ensure they are running and accessible from your Docker environment.

  * **Qdrant** (Vector Database)
  * **Elasticsearch** (Full-text Search)
  * **Neo4j** (Graph Database)

## Installation and Running with Docker

This project is configured to run easily using Docker and Docker Compose.

### Quick Start

```bash
# 1. Create environment file
cp example.env .env

# 2. Edit .env with your API keys and configuration
nano .env  # or use your preferred editor

# 3. Build and start services
docker-compose up --build -d

# 4. Check health
curl http://localhost:8386/health

# 5. View logs
docker-compose logs -f api
```

### 1. Prepare the Environment File

Copy the `example.env` file to a new file named `.env` and customize the variables as needed. This file will store all the necessary configurations for the application.

```bash
cp example.env .env
```

**Required Configuration:**

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8386
API_WORKERS=4

# Required API Keys
OPENAI_API_KEY=sk-your-actual-key
COHERE_API_KEY=your-cohere-key

# Database Connections
QDRANT_HOST=qdrant  # Use 'qdrant' for Docker Compose service
QDRANT_PORT=6333
ES_URL=http://your-elasticsearch:9200
GRAPH_DB_URL=bolt://your-neo4j:7687
GRAPH_USER=neo4j
GRAPH_PASSWORD=your-password

# Logfire Configuration (Optional but recommended)
LOGFIRE_TOKEN=pylf_v1_your-token
LOGFIRE_ENVIRONMENT=production
```

**Note on Logfire**: Logfire is used for monitoring, token usage tracking, and observability. Get your token from [logfire.pydantic.dev](https://logfire.pydantic.dev). If not configured, the application will run normally but without monitoring capabilities.

### 2. Build and Run Containers

Use Docker Compose to build the images and start the services (API and Qdrant database).

**Start all services:**
```bash
docker-compose up --build
```

**Run in detached mode (background):**
```bash
docker-compose up --build -d
```

**Start only the API (if using external Qdrant):**
```bash
docker-compose up --build api
```

Once successfully started, the API will be accessible at:
- **API**: http://localhost:8386
- **API Docs**: http://localhost:8386/docs
- **Health Check**: http://localhost:8386/health

### 3. Manage Containers

**View logs:**
```bash
docker-compose logs -f api
```

**Check status:**
```bash
docker-compose ps
```

**Restart services:**
```bash
docker-compose restart api
```

**Stop containers:**
```bash
docker-compose down
```

**Stop and remove volumes:**
```bash
docker-compose down -v
```

### 4. Scaling

**Scale API workers (horizontal):**
```bash
docker-compose up -d --scale api=3
```

**Increase workers per container (vertical):**
Edit `.env`:
```env
API_WORKERS=8
```
Then restart:
```bash
docker-compose restart api
```

### 📚 Detailed Documentation

For comprehensive deployment instructions, troubleshooting, and production configuration, see:
- **[DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)** - Complete Docker deployment guide
- **[LOGFIRE_SETUP.md](LOGFIRE_SETUP.md)** - Monitoring and observability setup

## Monitoring with Logfire

This application is instrumented with [Pydantic Logfire](https://logfire.pydantic.dev) for comprehensive monitoring and observability.

### Features

- **Token Usage Tracking**: Automatically tracks OpenAI API token usage for all LLM calls
- **Request Tracing**: Full tracing of API requests from endpoint to LLM calls
- **Performance Monitoring**: Track latency and performance of each component
- **Error Tracking**: Automatic capture of errors and exceptions with context
- **Async Operations**: Monitoring of all async operations and concurrent tasks

### Setup

1. Sign up at [logfire.pydantic.dev](https://logfire.pydantic.dev)
2. Create a project and get your token
3. Add the token to your `.env` file:
   ```env
   LOGFIRE_TOKEN=pylf_v1_your_token_here
   LOGFIRE_ENVIRONMENT=development
   ```

### What's Instrumented

- **FastAPI**: All API endpoints and middleware
- **OpenAI**: Token usage, prompts, and responses for all LLM calls
- **Async Operations**: All async tasks and concurrent operations
- **HTTP Requests**: External API calls via httpx
- **Custom Spans**: Query rewriting, semantic search, reranking, and synthesis steps

### Viewing Logs

Access your Logfire dashboard at [logfire.pydantic.dev](https://logfire.pydantic.dev) to view:
- Real-time request traces
- Token usage statistics
- Performance metrics
- Error logs and stack traces