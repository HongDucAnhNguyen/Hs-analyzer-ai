import os
import json
import copy
import logging
from typing import Dict, List, Optional, Any, Union

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Body, Request, Response
from pydantic import BaseModel

from rag_service.core.service.hs_code_search import hscode_search
from rag_service.api.http.v1.schemas import ProductSearchQuery
from rag_service.utils.cache import rag_cache, generate_cache_key
from rag_service.utils.suspicious_detection import detect_suspicious_request
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)

try:
    import logfire
    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False

router = APIRouter(prefix="/search", tags=["Search Service"])


@router.post("/asean")
async def asean_search_endpoint(query: ProductSearchQuery, response: Response) -> List[Dict[str, Any]]:
    """
    Search for HS Codes in ASEAN database (Vietnamese + English content).
    Accepts JSON body format compatible with classify service.
    Results are cached (exact match 1 hour) to improve performance.
    """
    # Check cache first
    query_data = query.dict()
    detect_suspicious_request(query_data, endpoint="/search/asean", collection_name="asean")
    cache_key = generate_cache_key(query_data, collection_name="asean")
    
    if cache_key in rag_cache:
        logger.info(f"✓ CACHE HIT for key: {cache_key[:16]}...")
        response.headers["X-Cache-Status"] = "HIT"
        response.headers["X-Cache-Mode"] = "EXACT"
        cached_result = rag_cache.get(cache_key)
        if cached_result:
            return cached_result

    logger.info(f"✗ CACHE MISS for key: {cache_key[:16]}...")
    response.headers["X-Cache-Status"] = "MISS"
    response.headers["X-Cache-Mode"] = "NONE"
    
    try:
        if LOGFIRE_AVAILABLE:
            with logfire.span(
                "asean_search_request",
                product_name=query.product_name,
                science_name=query.science_name or "",
                product_description=query.product_description or "",
                function=query.function or "",
                material=query.material or "",
                structure=query.structure or "",
                specifications=query.specifications or "",
                other_information=query.other_information or "",
            ):
                output = await hscode_search(
                    product_name=query.product_name,
                    science_name=query.science_name or "",
                    product_description=query.product_description or "",
                    function=query.function,
                    material=query.material,
                    structure=query.structure,
                    specifications=query.specifications,
                    other_information=query.other_information,
                    image_paths=[],
                    collection_name="asean",
                )
                logfire.info(
                    "ASEAN search completed",
                    product_name=query.product_name,
                    result_count=len(output) if output else 0
                )
        else:
            output = await hscode_search(
                product_name=query.product_name,
                science_name=query.science_name or "",
                product_description=query.product_description or "",
                function=query.function,
                material=query.material,
                structure=query.structure,
                specifications=query.specifications,
                other_information=query.other_information,
                image_paths=[],
                collection_name="asean",
            )
        
        # Cache the result
        rag_cache.set(cache_key, output)
        logger.info(f"✓ Cached result for key: {cache_key[:16]}...")
        
        return output
    except Exception as e:
        if LOGFIRE_AVAILABLE:
            logfire.error(f"ASEAN search failed for product: {query.product_name}", error=str(e))
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/compendium")
async def compendium_search_endpoint(query: ProductSearchQuery, response: Response) -> List[Dict[str, Any]]:
    """
    Search for HS Codes in WCO Compendium database (French + English content).
    Accepts JSON body format compatible with classify service.
    Results are cached (exact match 1 hour) to improve performance.
    """
    # Check cache first
    query_data = query.dict()
    detect_suspicious_request(
        query_data,
        endpoint="/search/compendium",
        collection_name="compendium",
    )
    cache_key = generate_cache_key(query_data, collection_name="compendium")
    
    if cache_key in rag_cache:
        logger.info(f"✓ CACHE HIT for key: {cache_key[:16]}...")
        response.headers["X-Cache-Status"] = "HIT"
        response.headers["X-Cache-Mode"] = "EXACT"
        cached_result = rag_cache.get(cache_key)
        if cached_result:
            return cached_result

    logger.info(f"✗ CACHE MISS for key: {cache_key[:16]}...")
    response.headers["X-Cache-Status"] = "MISS"
    response.headers["X-Cache-Mode"] = "NONE"
    
    try:
        if LOGFIRE_AVAILABLE:
            with logfire.span(
                "compendium_search_request",
                product_name=query.product_name,
                science_name=query.science_name or "",
                product_description=query.product_description or "",
                function=query.function or "",
                material=query.material or "",
                structure=query.structure or "",
                specifications=query.specifications or "",
                other_information=query.other_information or "",
            ):
                output = await hscode_search(
                    product_name=query.product_name,
                    science_name=query.science_name or "",
                    product_description=query.product_description or "",
                    function=query.function,
                    material=query.material,
                    structure=query.structure,
                    specifications=query.specifications,
                    other_information=query.other_information,
                    image_paths=[],
                    collection_name="compendium",
                )
                logfire.info(
                    "Compendium search completed",
                    product_name=query.product_name,
                    result_count=len(output) if output else 0
                )
        else:
            output = await hscode_search(
                product_name=query.product_name,
                science_name=query.science_name or "",
                product_description=query.product_description or "",
                function=query.function,
                material=query.material,
                structure=query.structure,
                specifications=query.specifications,
                other_information=query.other_information,
                image_paths=[],
                collection_name="compendium",
            )
        
        # Cache the result
        rag_cache.set(cache_key, output)
        logger.info(f"✓ Cached result for key: {cache_key[:16]}...")
        
        return output
    except Exception as e:
        if LOGFIRE_AVAILABLE:
            logfire.error(f"Compendium search failed for product: {query.product_name}", error=str(e))
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/cache/stats", tags=["Search Service"])
def get_cache_stats():
    """
    Get statistics about the current Redis cache for Search Service.
    """
    cache_keys = rag_cache.keys(limit=5)
    return {
        "cache_size": rag_cache.size(),
        "ttl_seconds": rag_cache.ttl,
        "cache_backend": "Redis",
        "cache_keys_preview": [key[:16] + "..." for key in cache_keys],
    }


@router.post("/cache/clear", tags=["Search Service"])
def clear_cache():
    """
    Clear all Search Service cache.
    """
    rag_cache.clear()
    return {"message": "RAG cache cleared successfully"}
