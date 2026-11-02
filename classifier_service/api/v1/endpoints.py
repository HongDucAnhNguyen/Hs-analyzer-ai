import copy
import logging
from fastapi import APIRouter, Response, HTTPException
from classifier_service.services.classification_service import get_classification
from classifier_service.utils.cache import classification_cache, generate_cache_key
from classifier_service.api.v1.schemas import (
    ProductQuery,
    ClassificationResponse,
    TaskSubmitResponse,
    TaskStatusResponse
)
from classifier_service.tasks.classification_tasks import classify_product_task
from classifier_service.core.celery_app import celery_app
from shared.llm_error_utils import is_quota_error, quota_error_detail

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/classify/", response_model=ClassificationResponse, tags=["Classification Service"])
def classify_product(query: ProductQuery, response: Response):
    """
    Receive product information and return classification results for Section, Chapter, Heading, and Subheading.
    Results are cached for 1 hour to improve performance.
    """
    query_data = query.dict()
    
    cache_key = generate_cache_key(query_data)
    
    if cache_key in classification_cache:
        logger.info(f"✓ CACHE HIT for key: {cache_key[:16]}...")
        response.headers["X-Cache-Status"] = "HIT"
        cached_result = classification_cache.get(cache_key)
        if cached_result:
            cached_result = copy.deepcopy(cached_result)
            cached_result["cache_hit"] = True
            return cached_result
    
    logger.info(f"✗ CACHE MISS for key: {cache_key[:16]}...")
    response.headers["X-Cache-Status"] = "MISS"
    
    try:
        result = get_classification(query_data)
    except Exception as exc:
        if is_quota_error(exc):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise
    result["cache_hit"] = False
    
    classification_cache.set(cache_key, result)
    logger.info(f"✓ Cached result for key: {cache_key[:16]}...")
    
    return result

@router.get("/classify/cache/stats", tags=["Classification Service"])
def get_cache_stats():
    """
    Get statistics about the current Redis cache for Classification Service.
    """
    cache_keys = classification_cache.keys(limit=5)
    return {
        "cache_size": classification_cache.size(),
        "ttl_seconds": classification_cache.ttl,
        "cache_backend": "Redis",
        "cache_keys_preview": [key[:16] + "..." for key in cache_keys],
    }

@router.post("/classify/cache/clear", tags=["Classification Service"])
def clear_cache():
    """
    Clear all Classification cache.
    """
    classification_cache.clear()
    return {"message": "Cache cleared successfully"}


@router.post("/classify/async", response_model=TaskSubmitResponse, tags=["Classification Service"])
def classify_product_async(query: ProductQuery):
    """
    Submit an asynchronous product classification request.
    Returns task_id to track progress.
    """
    query_data = query.dict()
    
    # Submit task to Celery
    task = classify_product_task.delay(query_data)
    
    logger.info(f"✓ Submitted async task {task.id}")
    
    return TaskSubmitResponse(
        task_id=task.id,
        status="PENDING",
        message="Classification task submitted successfully. Use /classify/async/{task_id} to check status."
    )


@router.get("/classify/async/{task_id}", response_model=TaskStatusResponse, tags=["Classification Service"])
def get_task_status(task_id: str):
    """
    Check the status of an asynchronous classification task.
    Returns partial results as they become available during processing.
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
        # Get progress info from task metadata
        info = task_result.info or {}
        response_data["progress"] = {
            "status": info.get("status", "Processing..."),
            "current_step": info.get("current_step", "unknown")
        }
        
        # Include partial results if available
        partial_results = info.get("partial_results", {})
        if partial_results:
            response_data["partial_results"] = partial_results
    
    elif task_result.status == "SUCCESS":
        result = task_result.result
        response_data["result"] = result
        
        # Also populate partial_results for consistent format
        # Extract classification results from the full result
        partial_results = {}
        if result:
            if "pre_classification" in result and result["pre_classification"]:
                partial_results["pre_classification"] = result["pre_classification"]
            if "section_classification" in result and result["section_classification"]:
                partial_results["section_classification"] = result["section_classification"]
            if "chapter_classification" in result and result["chapter_classification"]:
                partial_results["chapter_classification"] = result["chapter_classification"]
            if "heading_classification" in result and result["heading_classification"]:
                partial_results["heading_classification"] = result["heading_classification"]
            if "subheading_classification" in result and result["subheading_classification"]:
                partial_results["subheading_classification"] = result["subheading_classification"]
        
        if partial_results:
            response_data["partial_results"] = partial_results
    
    elif task_result.status == "FAILURE":
        response_data["error"] = str(task_result.info)
    
    return TaskStatusResponse(**response_data)
