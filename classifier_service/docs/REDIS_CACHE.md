# Redis Cache Implementation

## Overview

The classification system now uses Redis as a shared cache backend instead of in-memory TTLCache. This change enables cache sharing between the FastAPI server and Celery workers.

## Problem Solved

**Previous Issue:**
- The old implementation used `cachetools.TTLCache` (in-memory cache)
- Cache was only accessible within a single process
- API server and Celery workers had separate cache instances
- Async tasks (`/classify/async`) couldn't benefit from cached results
- Duplicate classifications were performed even when results existed in cache

**New Solution:**
- Redis-based distributed cache
- Shared cache between API server and Celery worker processes
- Both sync (`/classify/`) and async (`/classify/async`) endpoints use the same cache
- Significant performance improvement for async operations

## Architecture

```
┌─────────────┐
│  API Server │─┐
└─────────────┘ │
                ├──→ ┌───────┐
┌─────────────┐ │    │ Redis │
│   Workers   │─┘    │ Cache │
└─────────────┘      └───────┘
```

## Implementation Details

### Cache Class: `RedisCache`

Located in `classification/utils/cache.py`

**Key Features:**
- Automatic key prefixing: `classification:cache:{hash}`
- TTL (Time To Live): 3600 seconds (1 hour)
- JSON serialization for Python dictionaries
- Graceful error handling if Redis is unavailable

**Methods:**
- `get(key)` - Retrieve cached value
- `set(key, value)` - Store value with TTL
- `__contains__(key)` - Check if key exists
- `clear()` - Remove all cached entries
- `size()` - Get number of cached items
- `keys(limit)` - List cache keys for preview

### Usage in API Endpoints

**Synchronous Classification** (`/classify/`):
```python
cache_key = generate_cache_key(query_data)
if cache_key in classification_cache:
    cached_result = classification_cache.get(cache_key)
    # Use cached result
else:
    result = get_classification(query_data)
    classification_cache.set(cache_key, result)
```

**Asynchronous Classification** (`/classify/async`):
The Celery worker checks Redis cache before classification:
```python
cache_key = generate_cache_key(query_data)
if cache_key in classification_cache:
    # Return cached result immediately
    return classification_cache.get(cache_key)
# Perform classification and cache result
```

### Cache Management APIs

**Get Cache Statistics** (`GET /cache/stats`):
```json
{
  "cache_size": 42,
  "ttl_seconds": 3600,
  "cache_backend": "Redis",
  "cache_keys_preview": ["abc123...", "def456..."]
}
```

**Clear Cache** (`POST /cache/clear`):
Removes all cached classification results from Redis.

## Configuration

### Environment Variables

Set `REDIS_URL` in your `.env` file:
```env
REDIS_URL=redis://localhost:6379/0
```

Default: `redis://localhost:6379/0` if not specified

### Cache Settings

Defined in `classification/utils/cache.py`:
- `CACHE_TTL = 3600` - Cache duration (1 hour)
- `CACHE_KEY_PREFIX = "classification:cache:"` - Redis key prefix

## Benefits

1. **Performance**: 
   - Async tasks now benefit from cache
   - No duplicate LLM calls for the same query
   - Faster response times for cached requests

2. **Scalability**:
   - Multiple API server instances can share cache
   - Multiple worker instances share cache
   - Horizontal scaling support

3. **Cost Reduction**:
   - Fewer LLM API calls
   - Reduced processing time
   - Lower infrastructure costs

4. **Consistency**:
   - Same results for identical queries
   - Cache shared across all system components

## Cache Key Generation

Cache keys are generated using SHA256 hash of normalized query data:

```python
def generate_cache_key(query_data: dict) -> str:
    # Remove None values
    filtered_data = {k: v for k, v in query_data.items() if v is not None}
    
    # Normalize Unicode (important for Vietnamese text)
    normalized_data = normalize_unicode_dict(filtered_data)
    
    # Create sorted JSON string
    sorted_query = json.dumps(normalized_data, sort_keys=True, ensure_ascii=False)
    
    # Generate SHA256 hash
    cache_key = hashlib.sha256(sorted_query.encode('utf-8')).hexdigest()
    
    return cache_key
```

**Features:**
- Deterministic: Same query → Same key
- Unicode normalization for Vietnamese diacritics
- Sorted JSON ensures order independence
- SHA256 provides good distribution

## Error Handling

If Redis is unavailable:
- System logs warning but continues to operate
- Cache operations return `None` or `False`
- Classification proceeds without caching
- No system failures due to cache issues

## Monitoring

**Check Cache Status:**
```bash
# Via API
curl http://localhost:8000/cache/stats

# Via Redis CLI
redis-cli
> KEYS classification:cache:*
> GET classification:cache:abc123...
```

**Clear Cache:**
```bash
# Via API
curl -X POST http://localhost:8000/cache/clear

# Via Redis CLI
redis-cli
> DEL classification:cache:*
```

## Migration Notes

**From TTLCache to Redis:**
- No data migration needed (cache is ephemeral)
- Previous in-memory cache automatically cleared on restart
- Redis must be running before starting services
- Check Docker Compose configuration includes Redis service

## Testing

Verify cache is working:

1. **Start services:**
   ```bash
   ./start_all.sh
   ```

2. **Test sync endpoint:**
   ```bash
   curl -X POST http://localhost:8000/classify/ \
     -H "Content-Type: application/json" \
     -d '{"product_name": "test product"}'
   # Check response header: X-Cache-Status: MISS
   
   # Call again
   curl -X POST http://localhost:8000/classify/ \
     -H "Content-Type: application/json" \
     -d '{"product_name": "test product"}'
   # Check response header: X-Cache-Status: HIT
   ```

3. **Test async endpoint:**
   ```bash
   # Submit task
   curl -X POST http://localhost:8000/classify/async \
     -H "Content-Type: application/json" \
     -d '{"product_name": "test product"}'
   # Response: {"task_id": "xxx", ...}
   
   # Check status (should use cache from previous call)
   curl http://localhost:8000/classify/async/{task_id}
   # Result should show cache_hit: true
   ```

## Troubleshooting

**Cache Not Working:**
1. Check Redis is running: `docker ps | grep redis`
2. Test Redis connection: `redis-cli ping`
3. Check logs: `docker logs classification_redis`
4. Verify REDIS_URL environment variable

**Cache Keys Not Matching:**
1. Ensure Unicode normalization is working
2. Check query data is consistent
3. Verify JSON serialization order (should be sorted)

**High Memory Usage:**
1. Adjust TTL to lower value
2. Implement cache size limits in Redis
3. Monitor with: `redis-cli INFO memory`
