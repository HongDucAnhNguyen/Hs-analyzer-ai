"""API endpoints for crawl service v1"""

import logging
from fastapi import APIRouter, HTTPException, Response

from crawl_service.core.models import ProductCrawlQuery, CrawlResponseGrouped, HSCodeDatabaseResponse
from crawl_service.core.orchestrator import CrawlOrchestrator
from crawl_service.core.hs_database_orchestrator import HSCodeDatabaseOrchestrator
from crawl_service.utils.cache import crawl_cache, generate_cache_key
from crawl_service.utils.shared_query_cache import shared_query_cache
from crawl_service.api.v1.schemas import TaskSubmitResponse, TaskStatusResponse
from crawl_service.tasks.crawl_tasks import (
    search_hs_database_task,
    search_rulings_task,
)
from crawl_service.core.celery_app import celery_app
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawl", tags=["Crawl Service"])

# Initialize orchestrators
orchestrator = CrawlOrchestrator()
hs_database_orchestrator = HSCodeDatabaseOrchestrator()


@router.post("/hs-ruling", response_model=CrawlResponseGrouped)
async def search_hs_rulings(request: ProductCrawlQuery, response: Response):
    """
    Crawl all HS code ruling websites using detailed product information
    
    This endpoint:
    1. Uses LLM to rewrite product information into 3 technical search queries
    2. Searches across all sources with each technical query
    3. Generates Vietnamese reasons explaining relevance using LLM
    4. Groups results by technical name
    5. Returns structured response with reasons
    
    Sources queried:
    - CBSA Canada Trade Decisions
    - CARM Canada National Rulings
    - US CBP Rulings
    - UK HMRC Advance Tariff Rulings
    
    Results are cached for 1 hour to improve performance.
    
    Args:
        request: ProductCrawlQuery with detailed product information
        
    Returns:
        CrawlResponseGrouped with results grouped by technical name, 
        each with Vietnamese reasons
    """
    # Check cache first
    query_data = request.dict()
    cache_key = generate_cache_key(query_data, endpoint="hs-ruling")
    
    if cache_key in crawl_cache:
        logger.info(f"✓ CACHE HIT for key: {cache_key[:16]}...")
        response.headers["X-Cache-Status"] = "HIT"
        cached_result = crawl_cache.get(cache_key)
        if cached_result:
            return cached_result
    
    logger.info(f"✗ CACHE MISS for key: {cache_key[:16]}...")
    response.headers["X-Cache-Status"] = "MISS"
    
    try:
        logger.info(f"Received product crawl request for: '{request.product_name}'")
        result = await orchestrator.crawl_with_product_info_grouped(request)
        
        # Cache the result (convert to dict for caching)
        crawl_cache.set(cache_key, result.dict())
        logger.info(f"✓ Cached result for key: {cache_key[:16]}...")
        
        return result
    except Exception as e:
        logger.error(f"Error processing product crawl request: {e}")
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Error crawling sources: {str(e)}")


@router.post("/hs_database", response_model=HSCodeDatabaseResponse)
async def search_hs_database(request: ProductCrawlQuery, response: Response):
    """
    Search HS code databases using detailed product information
    
    This endpoint:
    1. Reuses or generates 3 technical search queries (shared cache with /hs-ruling)
    2. Searches across HS code databases:
       - UK Trade Tariff Service
       - The Trade Vision (Import & Export)
    3. Returns HS codes with counts and percentages (where applicable)
    4. Groups results by technical query
    
    Note: Zauba services temporarily disabled
    
    Results are cached for 1 hour to improve performance.
    Rewritten queries are shared with /hs-ruling endpoint.
    
    Args:
        request: ProductCrawlQuery with detailed product information
        
    Returns:
        HSCodeDatabaseResponse with HS codes grouped by technical query
    """
    # Check cache first
    query_data = request.dict()
    cache_key = generate_cache_key(query_data, endpoint="hs_database")
    
    if cache_key in crawl_cache:
        logger.info(f"✓ CACHE HIT for key: {cache_key[:16]}...")
        response.headers["X-Cache-Status"] = "HIT"
        cached_result = crawl_cache.get(cache_key)
        if cached_result:
            return cached_result
    
    logger.info(f"✗ CACHE MISS for key: {cache_key[:16]}...")
    response.headers["X-Cache-Status"] = "MISS"
    
    try:
        logger.info(f"Received HS database search request for: '{request.product_name}'")
        result = await hs_database_orchestrator.search_hs_codes(request)
        
        # Cache the result (convert to dict for caching)
        crawl_cache.set(cache_key, result.dict())
        logger.info(f"✓ Cached result for key: {cache_key[:16]}...")
        
        return result
    except Exception as e:
        logger.error(f"Error processing HS database search: {e}")
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Error searching HS databases: {str(e)}")


@router.get("/cache/stats", tags=["Crawl Service"])
def get_cache_stats():
    """
    Get cache statistics including size and sample keys.
    Shows stats for both main cache and shared query cache.
    """
    return {
        "main_cache": {
            "cache_size": crawl_cache.size(),
            "sample_keys": crawl_cache.keys(limit=10),
            "ttl_seconds": crawl_cache.ttl
        },
        "shared_query_cache": {
            "cache_size": shared_query_cache.size(),
            "ttl_seconds": shared_query_cache.ttl
        }
    }


@router.delete("/cache/clear", tags=["Crawl Service"])
def clear_cache():
    """
    Clear all Crawl Service cache (both main cache and shared query cache).
    """
    main_cleared = crawl_cache.clear()
    query_cleared = shared_query_cache.clear()
    return {
        "message": "All caches cleared successfully",
        "main_cache_cleared": main_cleared,
        "shared_query_cache_cleared": query_cleared,
        "total_cleared": main_cleared + query_cleared
    }


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for crawl service"""
    return {
        "status": "healthy",
        "service": "crawl_service",
        "sources": [
            "CBSA Canada",
            "CARM Canada",
            "US CBP",
            "UK HMRC"
        ]
    }


# ============================================================================
# Async Task-based APIs (Polling Pattern)
# ============================================================================

@router.post("/hs_database/async", response_model=TaskSubmitResponse, tags=["Crawl Service"])
async def search_hs_database_async(request: ProductCrawlQuery):
    """
    Submit an asynchronous HS database search task.
    Returns task_id to track progress.
    
    Use this for long-running searches to avoid timeout.
    Check status with GET /crawl/hs_database/async/{task_id}
    """
    query_data = request.dict()
    
    # Submit task to Celery
    task = search_hs_database_task.delay(query_data)
    
    logger.info(f"✓ Submitted async HS database search task {task.id}")
    
    return TaskSubmitResponse(
        task_id=task.id,
        status="PENDING",
        message="HS database search task submitted successfully. Use /crawl/hs_database/async/{task_id} to check status."
    )


@router.post("/hs-ruling/async", response_model=TaskSubmitResponse, tags=["Crawl Service"])
async def search_hs_rulings_async(request: ProductCrawlQuery):
    """
    Submit an asynchronous product rulings search task.
    Returns task_id to track progress.
    
    Use this for long-running searches to avoid timeout.
    Check status with GET /crawl/hs-ruling/async/{task_id}
    """
    query_data = request.dict()
    
    # Submit task to Celery
    task = search_rulings_task.delay(query_data)
    
    logger.info(f"✓ Submitted async rulings search task {task.id}")
    
    return TaskSubmitResponse(
        task_id=task.id,
        status="PENDING",
        message="Rulings search task submitted successfully. Use /crawl/hs-ruling/async/{task_id} to check status."
    )


@router.get("/hs-ruling/async/{task_id}", response_model=TaskStatusResponse, tags=["Crawl Service"])
def get_hs_ruling_task_status(task_id: str):
    """
    Check the status of an asynchronous product rulings search task.
    Returns partial results as they become available during processing.
    
    Status values:
    - PENDING: Task is waiting in queue
    - STARTED: Task has started processing
    - PROGRESS: Task is in progress (partial_results may be available)
    - SUCCESS: Task completed successfully (result contains full data)
    - FAILURE: Task failed (error contains error message)
    """
    task_result = celery_app.AsyncResult(task_id)
    
    response_data = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    if task_result.status == "PENDING":
        response_data["progress"] = {"status": "Task is waiting in queue..."}
    
    elif task_result.status == "STARTED":
        response_data["progress"] = {"status": "Task has started..."}
    
    elif task_result.status == "PROGRESS":
        info = task_result.info or {}
        response_data["progress"] = {
            "status": info.get("status", "Processing..."),
            "current_step": info.get("current_step", "unknown")
        }
        partial_results = info.get("partial_results", {})
        if partial_results:
            response_data["partial_results"] = partial_results
    
    elif task_result.status == "SUCCESS":
        result = task_result.result
        response_data["result"] = result
    
    elif task_result.status == "FAILURE":
        response_data["error"] = str(task_result.info)
    
    return TaskStatusResponse(**response_data)


@router.get("/hs_database/async/{task_id}", response_model=TaskStatusResponse, tags=["Crawl Service"])
def get_hs_database_task_status(task_id: str):
    """
    Check the status of an asynchronous HS database search task.
    Returns partial results as they become available during processing.
    
    Status values:
    - PENDING: Task is waiting in queue
    - STARTED: Task has started processing
    - PROGRESS: Task is in progress (partial_results may be available)
    - SUCCESS: Task completed successfully (result contains full data)
    - FAILURE: Task failed (error contains error message)
    """
    task_result = celery_app.AsyncResult(task_id)
    
    response_data = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    if task_result.status == "PENDING":
        response_data["progress"] = {"status": "Task is waiting in queue..."}
    
    elif task_result.status == "STARTED":
        response_data["progress"] = {"status": "Task has started..."}
    
    elif task_result.status == "PROGRESS":
        info = task_result.info or {}
        response_data["progress"] = {
            "status": info.get("status", "Processing..."),
            "current_step": info.get("current_step", "unknown")
        }
        partial_results = info.get("partial_results", {})
        if partial_results:
            response_data["partial_results"] = partial_results
    
    elif task_result.status == "SUCCESS":
        result = task_result.result
        response_data["result"] = result
    
    elif task_result.status == "FAILURE":
        response_data["error"] = str(task_result.info)
    
    return TaskStatusResponse(**response_data)
