# Deployment Guide

This guide explains how to deploy the HS Code Classification system with Redis and RabbitMQ for Celery, using `uv` for dependency management.

## Architecture

The deployment consists of the following services:

1. **Redis** - Result backend for Celery tasks
2. **RabbitMQ** - Message broker for Celery tasks
3. **App** - Main FastAPI application (managed with uv)
4. **Celery Worker** - Background task processor (managed with uv)
5. **Celery Flower** - Monitoring dashboard for Celery (managed with uv)

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- Ports 5672, 6379, 8000, 5555, and 15672 available
- Python 3.11+ (for local development)
- uv package manager (for local development)

## Configuration

1. Copy the example environment file:
```bash
cp example.env .env
```

2. Update the `.env` file with your configuration:
```bash
# Celery and Message Queue Configuration
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://admin:admin123@rabbitmq:5672/

# Other configurations...
```

## Deployment Options

### Option 1: Full Stack Deployment

Deploy all services including the application:

```bash
docker-compose up -d
```

This will start:
- Redis (port 6379)
- RabbitMQ (ports 5672, 15672)
- Application (port 8000)
- Celery Worker
- Celery Flower (port 5555)

### Option 2: Infrastructure Only

Deploy only Redis and RabbitMQ using the base configuration:

```bash
docker-compose -f docker-compose.base.yml up -d
```

This is useful for development when you want to run the application locally but use containerized infrastructure.

## Accessing Services

### Application
- URL: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### RabbitMQ Management UI
- URL: http://localhost:15672
- Username: admin
- Password: admin123

### Celery Flower (Monitoring)
- URL: http://localhost:5555

### Redis
- Host: localhost
- Port: 6379

## Service Management

### Start all services
```bash
docker-compose up -d
```

### Stop all services
```bash
docker-compose down
```

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f celery_worker
docker-compose logs -f app
docker-compose logs -f rabbitmq
```

### Restart a service
```bash
docker-compose restart celery_worker
```

### Scale Celery workers
```bash
docker-compose up -d --scale celery_worker=3
```

## Monitoring

### Check service health
```bash
docker-compose ps
```

### Monitor Celery tasks
Visit http://localhost:5555 to access Flower dashboard where you can:
- View active tasks
- Monitor worker status
- Check task history
- View task execution time

### Monitor RabbitMQ
Visit http://localhost:15672 to access RabbitMQ Management UI where you can:
- View queue status
- Monitor message rates
- Check connections
- View consumer details

## Troubleshooting

### Celery worker not connecting
1. Check if RabbitMQ is running:
```bash
docker-compose ps rabbitmq
```

2. View RabbitMQ logs:
```bash
docker-compose logs rabbitmq
```

3. Verify connection URL in `.env` file

### Tasks not executing
1. Check Celery worker logs:
```bash
docker-compose logs -f celery_worker
```

2. Verify task is registered:
```bash
docker-compose exec celery_worker celery -A classifier_service.core.celery_app inspect registered
```

### Redis connection issues
1. Test Redis connection:
```bash
docker-compose exec redis redis-cli ping
```

2. Check Redis logs:
```bash
docker-compose logs redis
```

## Security Recommendations for Production

1. **Change default passwords**: Update RabbitMQ credentials in both docker-compose.yml and .env
2. **Use environment variables**: Don't hardcode credentials
3. **Enable TLS**: Configure RabbitMQ and Redis with TLS certificates
4. **Restrict network access**: Use firewall rules to limit access to services
5. **Use secrets management**: Consider using Docker secrets or external secret managers

## Data Persistence

Data is persisted using Docker volumes:
- `redis_data`: Redis database
- `rabbitmq_data`: RabbitMQ data

To backup data:
```bash
docker run --rm -v classification_redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_backup.tar.gz -C /data .
docker run --rm -v classification_rabbitmq_data:/data -v $(pwd):/backup alpine tar czf /backup/rabbitmq_backup.tar.gz -C /data .
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| REDIS_URL | Redis connection URL | redis://redis:6379/0 |
| RABBITMQ_URL | RabbitMQ connection URL | amqp://admin:admin123@rabbitmq:5672/ |
| RABBITMQ_USER | RabbitMQ username | admin |
| RABBITMQ_PASS | RabbitMQ password | admin123 |

## Performance Tuning

### Celery Worker Concurrency
Adjust the `--concurrency` parameter in docker-compose.yml:
```yaml
command: celery -A classifier_service.core.celery_app worker --loglevel=info --concurrency=8
```

### RabbitMQ Memory Limits
Add memory configuration to RabbitMQ service:
```yaml
environment:
  RABBITMQ_VM_MEMORY_HIGH_WATERMARK: 1GB
```

### Redis Memory Limits
Configure Redis maxmemory:
```yaml
command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
