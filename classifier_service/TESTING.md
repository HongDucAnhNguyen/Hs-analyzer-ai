# Testing Infrastructure Connections

This guide explains how to test Redis and RabbitMQ connections separately before deploying the full application.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+
- uv package manager

## Step 1: Start Infrastructure Services Only

Use the `docker-compose.base.yml` file to start only Redis and RabbitMQ without the application:

```bash
# Start Redis and RabbitMQ
docker-compose -f docker-compose.base.yml up -d

# Check services are running
docker-compose -f docker-compose.base.yml ps

# View logs
docker-compose -f docker-compose.base.yml logs -f
```

Expected output:
```
NAME                        COMMAND                  SERVICE      STATUS       PORTS
classification-rabbitmq     "docker-entrypoint.s…"   rabbitmq     running      0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
classification-redis        "docker-entrypoint.s…"   redis        running      0.0.0.0:6379->6379/tcp
```

## Step 2: Set Up Environment Variables

Make sure your `.env` file has the correct connection URLs:

```bash
# For local testing with Docker infrastructure
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://admin:admin123@localhost:5672/
```

## Step 3: Install Test Dependencies

Navigate to the `classifier_service` directory and install dependencies:

```bash
cd classifier_service

# Install dependencies with uv
uv sync

# Or install specific test dependencies
uv pip install pytest redis pika python-dotenv
```

## Step 4: Run Connection Tests

### Run All Connection Tests

```bash
# Run both Redis and RabbitMQ tests
cd classifier_service
uv run pytest tests/test_redis_connection.py tests/test_rabbitmq_connection.py -v -s

# Or run individually
uv run pytest tests/test_redis_connection.py -v -s
uv run pytest tests/test_rabbitmq_connection.py -v -s
```

### Run Specific Tests

```bash
# Test only Redis connection
uv run pytest tests/test_redis_connection.py::test_redis_connection -v -s

# Test only RabbitMQ connection
uv run pytest tests/test_rabbitmq_connection.py::test_rabbitmq_connection -v -s

# Test Redis operations
uv run pytest tests/test_redis_connection.py::test_redis_set_get -v -s

# Test RabbitMQ publish/consume
uv run pytest tests/test_rabbitmq_connection.py::test_rabbitmq_publish_consume -v -s
```

### Run Tests Directly (Alternative)

```bash
cd classifier_service

# Run Redis tests directly
python tests/test_redis_connection.py

# Run RabbitMQ tests directly
python tests/test_rabbitmq_connection.py
```

## Expected Test Output

### Redis Tests

```
tests/test_redis_connection.py::test_redis_connection PASSED
✅ Redis connection successful

tests/test_redis_connection.py::test_redis_set_get PASSED
✅ Redis SET/GET operations successful

tests/test_redis_connection.py::test_redis_hash_operations PASSED
✅ Redis hash operations successful

tests/test_redis_connection.py::test_redis_list_operations PASSED
✅ Redis list operations successful

tests/test_redis_connection.py::test_redis_expiration PASSED
✅ Redis expiration test successful

tests/test_redis_connection.py::test_redis_info PASSED
✅ Redis INFO successful
   Redis Version: 7.x.x
   Used Memory: xxxMB
   Connected Clients: x
```

### RabbitMQ Tests

```
tests/test_rabbitmq_connection.py::test_rabbitmq_connection PASSED
✅ RabbitMQ connection successful

tests/test_rabbitmq_connection.py::test_rabbitmq_channel_creation PASSED
✅ RabbitMQ channel creation successful

tests/test_rabbitmq_connection.py::test_rabbitmq_queue_declare PASSED
✅ RabbitMQ queue declaration successful

tests/test_rabbitmq_connection.py::test_rabbitmq_publish_consume PASSED
✅ Message published to queue: test_publish_consume
✅ Message consumed from queue: Hello RabbitMQ!

tests/test_rabbitmq_connection.py::test_rabbitmq_exchange_declare PASSED
✅ RabbitMQ exchange declaration successful

tests/test_rabbitmq_connection.py::test_rabbitmq_queue_binding PASSED
✅ Queue binding successful
✅ Message routing successful

tests/test_rabbitmq_connection.py::test_rabbitmq_multiple_messages PASSED
✅ Published 5 messages
✅ Consumed 5 messages

tests/test_rabbitmq_connection.py::test_rabbitmq_connection_info PASSED
✅ RabbitMQ connection info:
   Host: localhost
   Port: 5672
   Virtual Host: /
   Connection State: Open
```

## Troubleshooting

### Redis Connection Failed

```bash
# Check if Redis is running
docker-compose -f docker-compose.base.yml ps redis

# Check Redis logs
docker-compose -f docker-compose.base.yml logs redis

# Test Redis connection manually
docker exec classification-redis redis-cli ping

# Verify port is accessible
telnet localhost 6379
```

### RabbitMQ Connection Failed

```bash
# Check if RabbitMQ is running
docker-compose -f docker-compose.base.yml ps rabbitmq

# Check RabbitMQ logs
docker-compose -f docker-compose.base.yml logs rabbitmq

# Test RabbitMQ connection manually
curl -u admin:admin123 http://localhost:15672/api/overview

# Access RabbitMQ Management UI
open http://localhost:15672
# Login: admin / admin123
```

### Port Already in Use

If you get port binding errors:

```bash
# Check what's using the port
lsof -i :6379  # Redis
lsof -i :5672  # RabbitMQ
lsof -i :15672 # RabbitMQ Management

# Stop existing services
docker-compose -f docker-compose.base.yml down

# Or change ports in docker-compose.base.yml
```

### Test Environment Issues

```bash
# Make sure you're in the correct directory
cd /path/to/smart-hs-code-search-ai/classifier_service

# Check environment variables
cat ../.env | grep -E "REDIS|RABBITMQ"

# Reinstall dependencies
uv sync --reinstall
```

## Manual Connection Testing

### Test Redis Manually

```python
import redis
from dotenv import load_dotenv
import os

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
client = redis.from_url(redis_url)

# Test connection
print(client.ping())  # Should return True

# Set and get value
client.set("test", "value")
print(client.get("test"))  # Should return b'value'
```

### Test RabbitMQ Manually

```python
import pika
from dotenv import load_dotenv
import os

load_dotenv()

rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://admin:admin123@localhost:5672/")
parameters = pika.URLParameters(rabbitmq_url)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()

# Test connection
print(f"Connection open: {connection.is_open}")  # Should return True

# Declare queue and publish message
channel.queue_declare(queue='test_queue')
channel.basic_publish(exchange='', routing_key='test_queue', body='Hello')
print("Message published!")

connection.close()
```

## Clean Up

Stop infrastructure services when done:

```bash
# Stop services
docker-compose -f docker-compose.base.yml down

# Remove volumes (caution: deletes all data)
docker-compose -f docker-compose.base.yml down -v
```

## Next Steps

Once all tests pass:

1. Deploy the full application stack:
   ```bash
   docker-compose up -d
   ```

2. Monitor services:
   - RabbitMQ UI: http://localhost:15672
   - Flower (Celery): http://localhost:5555
   - API: http://localhost:8000/docs

3. Check application logs:
   ```bash
   docker-compose logs -f app
   docker-compose logs -f celery_worker
   ```

## Integration Testing

After infrastructure tests pass, you can test Celery integration:

```bash
# Start all services
docker-compose up -d

# Check Celery worker is connected
docker-compose exec celery_worker celery -A classifier_service.core.celery_app inspect active

# Check registered tasks
docker-compose exec celery_worker celery -A classifier_service.core.celery_app inspect registered

# Monitor tasks in Flower
open http://localhost:5555
