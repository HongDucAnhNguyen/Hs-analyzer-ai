# Async Classification với Celery

## Tổng quan

Hệ thống phân loại sản phẩm hiện hỗ trợ phân loại bất đồng bộ (async) sử dụng Celery và Redis. Điều này cho phép xử lý các yêu cầu phân loại mà không làm chặn API, cải thiện trải nghiệm người dùng khi xử lý nhiều sản phẩm hoặc khi quá trình phân loại mất nhiều thời gian.

## Kiến trúc

```
Client → FastAPI → Celery Task Queue → Redis
                         ↓
                    Celery Worker(s)
                         ↓
                   LLM Processing
                         ↓
                    Result Storage
```

## Yêu cầu

### 1. Redis Server

Redis được sử dụng làm message broker và result backend cho Celery.

#### Option A: Sử dụng Docker Compose (Khuyến nghị)

**Lần đầu sử dụng Docker? Fix permissions:**
```bash
# Thêm user vào docker group
sudo usermod -aG docker $USER

# Apply changes (logout/login hoặc chạy command sau)
newgrp docker
```

**Khởi động Redis với Docker Compose:**
```bash
cd classification
docker compose up -d
```

**Kiểm tra Redis đang chạy:**
```bash
docker compose ps
# Hoặc
docker exec classification-redis redis-cli ping
# Should return: PONG
```

**Dừng Redis:**
```bash
docker compose down
```

**Xóa data và restart:**
```bash
docker compose down -v
docker compose up -d
```

**Note:** Sử dụng `docker compose` (2 từ) cho Docker Compose V2. Nếu dùng version cũ, dùng `docker-compose` (có dấu gạch ngang).

#### Option B: Cài đặt Redis local

**Cài đặt Redis:**
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis

# Khởi động Redis
redis-server
```

**Kiểm tra Redis đang chạy:**
```bash
redis-cli ping
# Should return: PONG
```

### 2. Python Dependencies

Đã được cài đặt trong `pyproject.toml`:
- `celery>=5.3.0`
- `redis>=5.0.0`

## Sử dụng

### 1. Khởi động các service

**Terminal 1 - FastAPI Server:**
```bash
cd classification
./run.sh
```

**Terminal 2 - Celery Worker:**
```bash
cd classification
./run_worker.sh
```

**Terminal 3 - Redis (nếu chưa chạy):**
```bash
redis-server
```

### 2. API Endpoints

#### A. Submit Async Classification Task

**Endpoint:** `POST /api/v1/classify/async`

**Request Body:**
```json
{
  "product_name": "Máy biến áp điện",
  "product_description": "Máy biến áp dùng trong công nghiệp",
  "material": "Thép và đồng",
  "function": "Chuyển đổi điện áp"
}
```

**Response:**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "PENDING",
  "message": "Classification task submitted successfully. Use /classify/async/{task_id} to check status."
}
```

#### B. Check Task Status

**Endpoint:** `GET /api/v1/classify/async/{task_id}`

**Các trạng thái có thể:**

1. **PENDING** - Task đang chờ xử lý
```json
{
  "task_id": "a1b2c3d4...",
  "status": "PENDING",
  "progress": {
    "status": "Task is waiting in queue..."
  }
}
```

2. **STARTED** - Task đã bắt đầu
```json
{
  "task_id": "a1b2c3d4...",
  "status": "STARTED",
  "progress": {
    "status": "Task has started..."
  }
}
```

3. **PROGRESS** - Task đang xử lý
```json
{
  "task_id": "a1b2c3d4...",
  "status": "PROGRESS",
  "progress": {
    "status": "Classifying Section...",
    "step": 1,
    "total_steps": 4
  }
}
```

4. **SUCCESS** - Task hoàn thành
```json
{
  "task_id": "a1b2c3d4...",
  "status": "SUCCESS",
  "result": {
    "section_classification": {...},
    "chapter_classification": {...},
    "heading_classification": {...},
    "subheading_classification": {...},
    "cache_hit": false,
    "task_id": "a1b2c3d4..."
  }
}
```

5. **FAILURE** - Task thất bại
```json
{
  "task_id": "a1b2c3d4...",
  "status": "FAILURE",
  "error": "Error message here"
}
```

### 3. Python Client Example

```python
import requests
import time

# 1. Submit task
response = requests.post(
    "http://localhost:3333/api/v1/classify/async",
    json={
        "product_name": "Máy biến áp",
        "product_description": "Máy biến áp công nghiệp"
    }
)
task_id = response.json()["task_id"]
print(f"Task submitted: {task_id}")

# 2. Poll for status
while True:
    response = requests.get(
        f"http://localhost:3333/api/v1/classify/async/{task_id}"
    )
    data = response.json()
    
    print(f"Status: {data['status']}")
    
    if data["status"] == "SUCCESS":
        print("Result:", data["result"])
        break
    elif data["status"] == "FAILURE":
        print("Error:", data["error"])
        break
    
    time.sleep(2)  # Wait 2 seconds before checking again
```

## So sánh Sync vs Async

| Feature | Sync API (`/classify/`) | Async API (`/classify/async`) |
|---------|------------------------|-------------------------------|
| Response Time | Chờ đến khi xong | Trả về ngay lập tức |
| Blocking | Có | Không |
| Use Case | Request đơn lẻ | Batch processing, nhiều request |
| Timeout Risk | Cao (5 phút) | Thấp |
| Monitoring | Không | Có (theo dõi progress) |

## Configuration

### Environment Variables (`.env`)

```bash
# Redis URL for Celery
REDIS_URL="redis://localhost:6379/0"
```

### Celery Configuration

Trong `classification/core/celery_app.py`:

```python
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)
```

## Monitoring

### Celery Flower (Optional)

Cài đặt Flower để monitor tasks:

```bash
pip install flower
celery -A classification.core.celery_app flower
```

Truy cập: http://localhost:5555

## Troubleshooting

### Issue: "Connection refused to Redis"

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not, start Redis
redis-server
```

### Issue: "Task always PENDING"

**Solution:**
- Đảm bảo Celery worker đang chạy
- Kiểm tra logs của worker để xem errors

### Issue: "Import errors in worker"

**Solution:**
- Đảm bảo chạy worker từ đúng directory
- Đảm bảo package đã được install trong editable mode:
```bash
cd classification
uv pip install -e .
```

## Best Practices

1. **Use async for batch processing**: Khi cần phân loại nhiều sản phẩm
2. **Cache still works**: Async API vẫn sử dụng cache
3. **Monitor workers**: Luôn giám sát Celery workers trong production
4. **Set timeouts**: Đặt timeout phù hợp cho tasks
5. **Scale workers**: Tăng số lượng workers khi cần:
   ```bash
   celery -A classification.core.celery_app worker --loglevel=info --concurrency=4
   ```

## Production Deployment

### Using systemd (Linux)

1. **FastAPI service** (`/etc/systemd/system/classification-api.service`)
2. **Celery worker service** (`/etc/systemd/system/classification-worker.service`)
3. **Redis service** (usually pre-configured)

### Using Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  api:
    build: .
    command: uvicorn classification.main:app --host 0.0.0.0 --port 3333
    ports:
      - "3333:3333"
    depends_on:
      - redis
  
  worker:
    build: .
    command: celery -A classification.core.celery_app worker --loglevel=info
    depends_on:
      - redis
```

## Tài liệu tham khảo

- [Celery Documentation](https://docs.celeryq.dev/)
- [Redis Documentation](https://redis.io/documentation)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
