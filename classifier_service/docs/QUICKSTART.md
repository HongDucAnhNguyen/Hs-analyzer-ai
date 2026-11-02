# Quick Start Guide - Async Classification

## 🚀 Bắt đầu nhanh - CHỈ 1 LỆNH!

### Cách 1: Start tất cả (Khuyến nghị) ⚡

```bash
cd classification
./start_all.sh
```

**Dừng tất cả:**
```bash
cd classification
./stop_all.sh
```

---

### Cách 2: Start từng service riêng

**Bước 1: Khởi động Redis với Docker Compose**

Lần đầu sử dụng Docker? Fix permissions:
```bash
sudo usermod -aG docker $USER
newgrp docker  # hoặc logout/login
```

Khởi động Redis:
```bash
cd classification
docker compose up -d
```

**Bước 2: Terminal 1 - FastAPI Server**
```bash
cd classification
./run.sh
```

**Bước 3: Terminal 2 - Celery Worker**
```bash
cd classification
./run_worker.sh
```

### Bước 3: Test API

**Gửi yêu cầu phân loại:**
```bash
curl -X POST http://localhost:3333/api/v1/classify/async \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Máy biến áp điện",
    "product_description": "Máy biến áp công nghiệp 220V",
    "material": "Thép và đồng",
    "function": "Chuyển đổi điện áp"
  }'
```

**Kết quả sẽ trả về task_id:**
```json
{
  "task_id": "abc123-def456-...",
  "status": "PENDING",
  "message": "Classification task submitted..."
}
```

**Kiểm tra kết quả:**
```bash
curl http://localhost:3333/api/v1/classify/async/{task_id}
```

---

## 📊 API Endpoints

### 1. Sync API (Blocking)
```bash
POST /api/v1/classify/
```
Chờ đến khi có kết quả (30-120 giây)

### 2. Async API (Non-blocking)
```bash
POST /api/v1/classify/async
GET /api/v1/classify/async/{task_id}
```
Trả về ngay lập tức, theo dõi tiến trình

### 3. Cache Management
```bash
GET /api/v1/cache/stats
POST /api/v1/cache/clear
```

---

## 🐍 Python Example

```python
import requests
import time

# Submit task
response = requests.post(
    "http://localhost:3333/api/v1/classify/async",
    json={"product_name": "Máy biến áp"}
)
task_id = response.json()["task_id"]

# Poll for result
while True:
    status = requests.get(
        f"http://localhost:3333/api/v1/classify/async/{task_id}"
    ).json()
    
    if status["status"] == "SUCCESS":
        print(status["result"])
        break
    
    print(f"Status: {status['status']}")
    time.sleep(2)
```

---

## 📝 Xem Logs Realtime

**Cách 1: Sử dụng script (Dễ nhất)**
```bash
cd classification
./view_logs.sh
```

Chọn log muốn xem:
- `1` - API logs only
- `2` - Worker logs only  
- `3` - Cả 2 logs (split screen)

**Cách 2: Xem trực tiếp**
```bash
# Xem API logs
tail -f classification/logs/api.log

# Xem Worker logs
tail -f classification/logs/worker.log

# Xem cả 2 cùng lúc
tail -f classification/logs/api.log classification/logs/worker.log
```

**Cách 3: Theo dõi lỗi (errors only)**
```bash
# Chỉ xem errors trong API
tail -f classification/logs/api.log | grep -i error

# Chỉ xem errors trong Worker
tail -f classification/logs/worker.log | grep -i error
```

---

## 🔧 Troubleshooting

### Redis không kết nối được?
```bash
docker-compose restart
```

### Worker không chạy?
```bash
# Kiểm tra logs
docker-compose logs redis

# Reinstall package
cd classification
uv pip install -e .
```

### API docs
Truy cập: http://localhost:3333/docs

---

## 📚 Tài liệu đầy đủ

Xem file `docs/ASYNC_CLASSIFICATION.md` để biết chi tiết về:
- Kiến trúc hệ thống
- Configuration
- Monitoring với Flower
- Production deployment
- Best practices

---

## 🛑 Dừng các services

```bash
# Dừng Redis
docker-compose down

# Dừng FastAPI và Worker
# Ctrl+C trong terminals đang chạy
```

---

## ✅ Checklist

- [ ] Docker đã cài đặt
- [ ] Redis đang chạy (`docker-compose ps`)
- [ ] FastAPI đang chạy (http://localhost:3333/docs)
- [ ] Celery worker đang chạy
- [ ] Test API thành công

Chúc mừng! Bạn đã sẵn sàng sử dụng async classification! 🎉
