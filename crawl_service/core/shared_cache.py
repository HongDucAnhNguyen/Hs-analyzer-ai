"""Shared cache for rewritten queries between crawl_service and hs_database"""

import hashlib
import json
import logging
from typing import List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# In-memory cache with TTL
_query_cache = {}
CACHE_TTL = timedelta(hours=24)  # Cache for 24 hours


def _get_cache_key(
    product_name: str,
    science_name: str = "",
    product_description: str = "",
    function: str = "",
    material: str = "",
    structure: str = "",
    specifications: str = ""
) -> str:
    """Generate a unique cache key from product attributes"""
    data = {
        "product_name": product_name,
        "science_name": science_name,
        "product_description": product_description,
        "function": function,
        "material": material,
        "structure": structure,
        "specifications": specifications
    }
    # Sort keys for consistent hashing
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.md5(json_str.encode()).hexdigest()


def get_cached_queries(
    product_name: str,
    science_name: str = "",
    product_description: str = "",
    function: str = "",
    material: str = "",
    structure: str = "",
    specifications: str = ""
) -> Optional[List[str]]:
    """Get cached rewritten queries if available and not expired"""
    cache_key = _get_cache_key(
        product_name, science_name, product_description,
        function, material, structure, specifications
    )
    
    if cache_key in _query_cache:
        cached_data = _query_cache[cache_key]
        timestamp = cached_data["timestamp"]
        
        # Check if cache is still valid
        if datetime.now() - timestamp < CACHE_TTL:
            logger.info(f"Cache HIT for product: {product_name}")
            return cached_data["queries"]
        else:
            # Remove expired cache
            logger.info(f"Cache EXPIRED for product: {product_name}")
            del _query_cache[cache_key]
    
    logger.info(f"Cache MISS for product: {product_name}")
    return None


def cache_queries(
    queries: List[str],
    product_name: str,
    science_name: str = "",
    product_description: str = "",
    function: str = "",
    material: str = "",
    structure: str = "",
    specifications: str = ""
) -> None:
    """Cache rewritten queries"""
    cache_key = _get_cache_key(
        product_name, science_name, product_description,
        function, material, structure, specifications
    )
    
    _query_cache[cache_key] = {
        "queries": queries,
        "timestamp": datetime.now()
    }
    
    logger.info(f"Cached queries for product: {product_name}")


def clear_cache():
    """Clear all cached queries (useful for testing)"""
    global _query_cache
    _query_cache = {}
    logger.info("Query cache cleared")
