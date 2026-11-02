"""Shared cache for rewritten queries between /hs-ruling and /hs_database endpoints

This module provides a distributed locking mechanism to ensure that when both endpoints
are called concurrently, only ONE generates the rewritten queries, and the other waits
and uses the cached result. This guarantees consistent technical_name across both endpoints.
"""

import logging
import hashlib
import json
import asyncio
from typing import List, Optional, Tuple
from .cache import redis_client, CACHE_TTL

logger = logging.getLogger(__name__)

# Cache prefix for rewritten queries
REWRITE_CACHE_PREFIX = "crawl:rewrite:"
REWRITE_LOCK_PREFIX = "crawl:rewrite:lock:"

# Lock configuration
LOCK_TTL = 60  # Lock expires after 60 seconds (safety timeout)
LOCK_WAIT_INTERVAL = 0.1  # Check every 100ms
LOCK_MAX_WAIT_TIME = 55  # Maximum wait time for lock (slightly less than LOCK_TTL)


class SharedQueryCache:
    """
    Shared cache for rewritten queries with distributed locking.
    
    When multiple endpoints call get_or_generate_queries concurrently:
    1. First caller acquires the lock and generates queries
    2. Other callers wait for the lock to be released
    3. Once released, they read from cache
    
    This ensures consistent technical_name across all endpoints.
    """
    
    def __init__(self, redis_client, ttl: int = CACHE_TTL):
        self.redis_client = redis_client
        self.ttl = ttl
        self.prefix = REWRITE_CACHE_PREFIX
        self.lock_prefix = REWRITE_LOCK_PREFIX
    
    def _generate_key(self, product_info: dict) -> str:
        """
        Generate cache key from product information
        Uses only the core product fields for caching rewritten queries
        """
        # Only use relevant fields for query rewriting
        cache_data = {
            "product_name": product_info.get("product_name", ""),
            "science_name": product_info.get("science_name"),
            "product_description": product_info.get("product_description"),
            "function": product_info.get("function"),
            "structure": product_info.get("structure"),
            "material": product_info.get("material"),
            "specifications": product_info.get("specifications"),
        }
        
        # Remove None values
        cache_data = {k: v for k, v in cache_data.items() if v is not None}
        
        # Generate hash
        sorted_json = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
        key_hash = hashlib.sha256(sorted_json.encode('utf-8')).hexdigest()
        
        return key_hash
    
    def _get_cache_key(self, key_hash: str) -> str:
        """Get full cache key"""
        return f"{self.prefix}{key_hash}"
    
    def _get_lock_key(self, key_hash: str) -> str:
        """Get lock key for distributed locking"""
        return f"{self.lock_prefix}{key_hash}"
    
    def _acquire_lock(self, key_hash: str) -> bool:
        """
        Try to acquire distributed lock using Redis SETNX
        
        Returns:
            True if lock acquired, False if already locked by another process
        """
        if not self.redis_client:
            return True  # No Redis = no locking, proceed normally
        
        try:
            lock_key = self._get_lock_key(key_hash)
            # SETNX with TTL - atomic operation
            acquired = self.redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL)
            if acquired:
                logger.info(f"🔒 Lock acquired for key: {key_hash[:16]}...")
            return bool(acquired)
        except Exception as e:
            logger.error(f"Error acquiring lock: {e}")
            return True  # On error, proceed without locking
    
    def _release_lock(self, key_hash: str) -> bool:
        """Release distributed lock"""
        if not self.redis_client:
            return True
        
        try:
            lock_key = self._get_lock_key(key_hash)
            self.redis_client.delete(lock_key)
            logger.info(f"🔓 Lock released for key: {key_hash[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")
            return False
    
    def _is_locked(self, key_hash: str) -> bool:
        """Check if key is locked"""
        if not self.redis_client:
            return False
        
        try:
            lock_key = self._get_lock_key(key_hash)
            return bool(self.redis_client.exists(lock_key))
        except Exception as e:
            logger.error(f"Error checking lock: {e}")
            return False
    
    def get_rewritten_queries(self, product_info: dict) -> Optional[List[str]]:
        """
        Get cached rewritten queries for product info (sync version)
        
        Args:
            product_info: Dictionary with product information
            
        Returns:
            List of rewritten queries if cached, None otherwise
        """
        if not self.redis_client:
            return None
        
        try:
            key_hash = self._generate_key(product_info)
            cache_key = self._get_cache_key(key_hash)
            value = self.redis_client.get(cache_key)
            
            if value:
                queries = json.loads(value)
                logger.info(f"✓ Cache HIT for rewritten queries: {key_hash[:16]}...")
                return queries
            
            logger.info(f"✗ Cache MISS for rewritten queries: {key_hash[:16]}...")
            return None
            
        except Exception as e:
            logger.error(f"Error getting rewritten queries from cache: {e}")
            return None
    
    def set_rewritten_queries(self, product_info: dict, queries: List[str]) -> bool:
        """
        Cache rewritten queries for product info (sync version)
        
        Args:
            product_info: Dictionary with product information
            queries: List of rewritten queries to cache
            
        Returns:
            True if cached successfully, False otherwise
        """
        if not self.redis_client:
            return False
        
        try:
            key_hash = self._generate_key(product_info)
            cache_key = self._get_cache_key(key_hash)
            json_value = json.dumps(queries, ensure_ascii=False)
            self.redis_client.setex(cache_key, self.ttl, json_value)
            logger.info(f"✓ Cached rewritten queries: {key_hash[:16]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error caching rewritten queries: {e}")
            return False
    
    async def get_or_generate_queries(
        self, 
        product_info: dict, 
        generator_func
    ) -> Tuple[List[str], bool]:
        """
        Get cached queries or generate new ones with distributed locking.
        
        This is the KEY method for solving concurrent access issues.
        When multiple endpoints call this method simultaneously:
        1. First caller acquires lock, generates queries, caches them, releases lock
        2. Other callers wait for cache to be populated, then use cached result
        
        Args:
            product_info: Dictionary with product information
            generator_func: Async function to generate queries if not cached
                           Should be: async def func() -> List[str]
        
        Returns:
            Tuple of (queries, was_generated)
            - queries: List of rewritten queries
            - was_generated: True if generated by this call, False if from cache
        """
        key_hash = self._generate_key(product_info)
        
        # Step 1: Try to get from cache first
        cached = self.get_rewritten_queries(product_info)
        if cached:
            logger.info(f"✓ Using cached queries (no lock needed): {key_hash[:16]}...")
            return cached, False
        
        # Step 2: Try to acquire lock
        if self._acquire_lock(key_hash):
            # We got the lock - we're responsible for generating queries
            try:
                # Double-check cache (another process might have just finished)
                cached = self.get_rewritten_queries(product_info)
                if cached:
                    logger.info(f"✓ Cache populated while waiting for lock: {key_hash[:16]}...")
                    return cached, False
                
                # Generate new queries
                logger.info(f"🔄 Generating new queries (holding lock): {key_hash[:16]}...")
                queries = await generator_func()
                
                # Cache the result
                self.set_rewritten_queries(product_info, queries)
                
                return queries, True
            finally:
                # Always release lock
                self._release_lock(key_hash)
        else:
            # Another process has the lock - wait for cache to be populated
            logger.info(f"⏳ Waiting for another process to generate queries: {key_hash[:16]}...")
            
            waited = 0.0
            while waited < LOCK_MAX_WAIT_TIME:
                await asyncio.sleep(LOCK_WAIT_INTERVAL)
                waited += LOCK_WAIT_INTERVAL
                
                # Check if cache is now populated
                cached = self.get_rewritten_queries(product_info)
                if cached:
                    logger.info(f"✓ Got cached queries after waiting {waited:.1f}s: {key_hash[:16]}...")
                    return cached, False
                
                # Check if lock was released (error case or timeout)
                if not self._is_locked(key_hash):
                    # Lock released but no cache - something went wrong
                    # Try to acquire lock ourselves
                    if self._acquire_lock(key_hash):
                        try:
                            # Double-check cache one more time
                            cached = self.get_rewritten_queries(product_info)
                            if cached:
                                return cached, False
                            
                            # Generate ourselves
                            logger.info(f"🔄 Generating queries after lock released: {key_hash[:16]}...")
                            queries = await generator_func()
                            self.set_rewritten_queries(product_info, queries)
                            return queries, True
                        finally:
                            self._release_lock(key_hash)
                    else:
                        # Someone else got the lock, continue waiting
                        continue
            
            # Timeout - generate our own (fallback)
            logger.warning(f"⚠️ Lock wait timeout, generating own queries: {key_hash[:16]}...")
            queries = await generator_func()
            # Don't cache - might conflict with another process
            return queries, True
    
    def clear(self) -> int:
        """Clear all cached rewritten queries and locks"""
        if not self.redis_client:
            return 0
        
        try:
            # Clear cache entries
            cache_pattern = f"{self.prefix}*"
            cache_keys = self.redis_client.keys(cache_pattern)
            
            # Clear lock entries
            lock_pattern = f"{self.lock_prefix}*"
            lock_keys = self.redis_client.keys(lock_pattern)
            
            all_keys = (cache_keys or []) + (lock_keys or [])
            if all_keys:
                return self.redis_client.delete(*all_keys)
            return 0
        except Exception as e:
            logger.error(f"Error clearing rewritten query cache: {e}")
            return 0
    
    def size(self) -> int:
        """Get number of cached rewritten queries"""
        if not self.redis_client:
            return 0
        
        try:
            pattern = f"{self.prefix}*"
            keys = self.redis_client.keys(pattern)
            # Exclude lock keys
            cache_keys = [k for k in keys if self.lock_prefix not in k]
            return len(cache_keys)
        except Exception as e:
            logger.error(f"Error getting cache size: {e}")
            return 0


# Initialize shared query cache
shared_query_cache = SharedQueryCache(redis_client, ttl=CACHE_TTL)
