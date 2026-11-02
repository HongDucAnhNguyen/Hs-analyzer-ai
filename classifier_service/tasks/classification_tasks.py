"""
Celery Tasks for Product Classification
"""
import logging
from typing import Dict, Any
from celery import Task
from celery.exceptions import Retry
from redis.exceptions import ConnectionError, TimeoutError, ResponseError
from classifier_service.core.celery_app import celery_app
from classifier_service.services.classification_service import get_classification
from classifier_service.utils.cache import classification_cache, generate_cache_key
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True, 
    name="classifier_service.tasks.classify_product",
    autoretry_for=(ConnectionError, TimeoutError, ResponseError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def classify_product_task(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async task to classify a product through the entire workflow.
    Updates task state with partial results as they become available.
    
    Args:
        query_data: Product information dictionary
        
    Returns:
        Classification results dictionary
    """
    try:
        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Starting classification...'})
        
        # Check cache first (with error handling)
        cache_key = generate_cache_key(query_data)
        try:
            if cache_key in classification_cache:
                logger.info(f"✓ CACHE HIT for task {self.request.id}")
                cached_result = classification_cache.get(cache_key)
                if cached_result:
                    result = cached_result.copy()
                    result["cache_hit"] = True
                    result["task_id"] = self.request.id
                    return result
            
            logger.info(f"✗ CACHE MISS for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Cache check failed, continuing without cache: {e}")
            # Continue without cache if Redis is unavailable
        
        # Store partial results as we progress
        partial_results = {}
        
        def progress_callback(step: str, data: Dict[str, Any]):
            """Callback to update task state with partial results"""
            # Store the result if available
            if 'result' in data:
                partial_results[step] = data['result']
            
            # Update Celery task state with current progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': data.get('status', f'Processing {step}...'),
                    'current_step': step,
                    'partial_results': partial_results.copy()
                }
            )
            logger.info(f"Task {self.request.id}: {step} - {data.get('status')}")
        
        # Perform classification with progress callback
        try:
            result = get_classification(query_data, progress_callback=progress_callback)
        except Exception as exc:
            if is_quota_error(exc):
                message = quota_error_detail()
                logger.error("Classification failed due to quota: %s", exc)
                self.update_state(
                    state='FAILURE',
                    meta={
                        'status': 'Classification failed',
                        'error': message
                    }
                )
                raise RuntimeError(message) from exc
            raise
        
        # Cache the result (with error handling)
        result["cache_hit"] = False
        result["task_id"] = self.request.id
        try:
            classification_cache.set(cache_key, result)
            logger.info(f"✓ Cached result for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Failed to cache result, but task succeeded: {e}")
            # Don't fail the task if caching fails
        
        return result
        
    except (ConnectionError, TimeoutError, ResponseError) as e:
        logger.error(f"Redis connection error in task {self.request.id}: {str(e)}")
        # Let Celery's autoretry handle this
        raise
    except Exception as e:
        logger.error(f"Error in classification task {self.request.id}: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Classification failed',
                'error': str(e)
            }
        )
        raise
