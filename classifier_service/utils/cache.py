import hashlib
import json
import logging
import unicodedata
import os
import redis
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = 3600  # 1 hour
CACHE_KEY_PREFIX = "classification:cache:"

# Initialize Redis client with connection pool and retry settings
try:
    # Configure connection pool with retries and timeouts
    redis_client = redis.from_url(
        REDIS_URL, 
        decode_responses=True,
        socket_keepalive=True,
        socket_keepalive_options={},
        socket_connect_timeout=5,  # 5 seconds to connect
        socket_timeout=5,  # 5 seconds for operations
        retry_on_timeout=True,
        health_check_interval=30,  # Check connection health every 30 seconds
        max_connections=50  # Connection pool size
    )
    redis_client.ping()
    logger.info(f"✓ Connected to Redis for caching")
except Exception as e:
    logger.error(f"✗ Failed to connect to Redis: {e}")
    redis_client = None


class RedisCache:
    """
    Redis-based cache for classification results.
    Provides shared cache between API server and Celery workers.
    """
    
    def __init__(self, redis_client, ttl: int = CACHE_TTL, key_prefix: str = CACHE_KEY_PREFIX):
        self.redis_client = redis_client
        self.ttl = ttl
        self.key_prefix = key_prefix
    
    def _make_key(self, key: str) -> str:
        """Add prefix to cache key"""
        return f"{self.key_prefix}{key}"
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache"""
        if not self.redis_client:
            return None
        
        try:
            full_key = self._make_key(key)
            value = self.redis_client.get(full_key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Set value in cache with TTL"""
        if not self.redis_client:
            return False
        
        try:
            full_key = self._make_key(key)
            json_value = json.dumps(value, ensure_ascii=False)
            self.redis_client.setex(full_key, self.ttl, json_value)
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis_client:
            return False
        
        try:
            full_key = self._make_key(key)
            return self.redis_client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all cache entries with the prefix"""
        if not self.redis_client:
            return 0
        
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0
    
    def size(self) -> int:
        """Get number of cached entries"""
        if not self.redis_client:
            return 0
        
        try:
            pattern = f"{self.key_prefix}*"
            return len(self.redis_client.keys(pattern))
        except Exception as e:
            logger.error(f"Error getting cache size: {e}")
            return 0
    
    def keys(self, limit: int = 100):
        """Get cache keys (for preview)"""
        if not self.redis_client:
            return []
        
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis_client.keys(pattern)
            # Remove prefix for display
            return [k.replace(self.key_prefix, "") for k in keys[:limit]]
        except Exception as e:
            logger.error(f"Error getting cache keys: {e}")
            return []


# Initialize Redis cache
classification_cache = RedisCache(redis_client, ttl=CACHE_TTL, key_prefix=CACHE_KEY_PREFIX)

def normalize_unicode_dict(data: dict) -> dict:
    """
    Normalize all string values in a dictionary to NFC form.
    This ensures consistent Unicode representation for Vietnamese text with diacritics.
    """
    normalized = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Normalize to NFC (Canonical Composition)
            normalized[key] = unicodedata.normalize('NFC', value)
        else:
            normalized[key] = value
    return normalized

def generate_cache_key(query_data: dict) -> str:
    """
    Generate a unique cache key based on query data.
    Normalizes Unicode strings to ensure consistent caching for Vietnamese text.
    """
    # Remove None values to ensure consistent caching
    filtered_data = {k: v for k, v in query_data.items() if v is not None}
    
    # Normalize Unicode strings (important for Vietnamese text with diacritics)
    normalized_data = normalize_unicode_dict(filtered_data)
    
    # Create a sorted JSON string to ensure consistent keys
    sorted_query = json.dumps(normalized_data, sort_keys=True, ensure_ascii=False)
    
    # Generate SHA256 hash for the key
    cache_key = hashlib.sha256(sorted_query.encode('utf-8')).hexdigest()
    
    logger.info(f"Generated cache key: {cache_key[:16]}... for query: {normalized_data.get('product_name', 'N/A')}")
    return cache_key
