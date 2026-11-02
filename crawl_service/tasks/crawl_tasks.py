"""
Celery Tasks for Crawl Service - HS Database and Rulings Search
"""
import logging
import asyncio
from typing import Dict, Any
from redis.exceptions import ConnectionError, TimeoutError, ResponseError
from crawl_service.core.celery_app import celery_app
from crawl_service.utils.cache import crawl_cache, generate_cache_key
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="crawl_service.tasks.search_hs_database",
    autoretry_for=(ConnectionError, TimeoutError, ResponseError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def search_hs_database_task(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async task to search HS code databases.
    Updates task state with progress information.
    
    Args:
        query_data: ProductCrawlQuery dictionary
        
    Returns:
        HSCodeDatabaseResponse dictionary
    """
    from crawl_service.core.models import ProductCrawlQuery
    from crawl_service.core.hs_database_orchestrator import HSCodeDatabaseOrchestrator
    
    try:
        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Starting HS database search...'})
        
        # Check cache first
        cache_key = generate_cache_key(query_data, endpoint="hs_database")
        try:
            if cache_key in crawl_cache:
                logger.info(f"✓ CACHE HIT for task {self.request.id}")
                cached_result = crawl_cache.get(cache_key)
                if cached_result:
                    result = cached_result.copy()
                    result["cache_hit"] = True
                    result["task_id"] = self.request.id
                    return result
            
            logger.info(f"✗ CACHE MISS for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Cache check failed, continuing without cache: {e}")
        
        # Update state: Rewriting queries
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Rewriting product information into technical queries...',
                'current_step': 'query_rewriting',
                'product_name': query_data.get('product_name', '')
            }
        )
        
        # Create request object
        request = ProductCrawlQuery(**query_data)
        
        # Update state: Searching databases
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Searching HS code databases...',
                'current_step': 'searching_databases',
                'product_name': query_data.get('product_name', '')
            }
        )
        
        # Create orchestrator and run search
        orchestrator = HSCodeDatabaseOrchestrator()
        try:
            result = run_async(orchestrator.search_hs_codes(request))
        except Exception as exc:
            if is_quota_error(exc):
                message = quota_error_detail()
                logger.error("HS database search failed due to quota: %s", exc)
                self.update_state(
                    state='FAILURE',
                    meta={
                        'status': 'HS database search failed',
                        'error': message
                    }
                )
                raise RuntimeError(message) from exc
            raise
        
        # Convert to dict
        result_dict = result.dict() if hasattr(result, 'dict') else result.model_dump()
        result_dict["cache_hit"] = False
        result_dict["task_id"] = self.request.id
        
        # Cache the result
        try:
            crawl_cache.set(cache_key, result_dict)
            logger.info(f"✓ Cached result for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Failed to cache result: {e}")
        
        return result_dict
        
    except (ConnectionError, TimeoutError, ResponseError) as e:
        logger.error(f"Redis connection error in task {self.request.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in HS database search task {self.request.id}: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'HS database search failed',
                'error': str(e)
            }
        )
        raise


@celery_app.task(
    bind=True,
    name="crawl_service.tasks.search_rulings",
    autoretry_for=(ConnectionError, TimeoutError, ResponseError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def search_rulings_task(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async task to search HS code rulings from multiple sources.
    Updates task state with progress information.
    
    Args:
        query_data: ProductCrawlQuery dictionary
        
    Returns:
        CrawlResponseGrouped dictionary
    """
    from crawl_service.core.models import ProductCrawlQuery
    from crawl_service.core.orchestrator import CrawlOrchestrator
    
    try:
        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Starting rulings search...'})
        
        # Check cache first
        cache_key = generate_cache_key(query_data, endpoint="hs-ruling")
        try:
            if cache_key in crawl_cache:
                logger.info(f"✓ CACHE HIT for task {self.request.id}")
                cached_result = crawl_cache.get(cache_key)
                if cached_result:
                    result = cached_result.copy()
                    result["cache_hit"] = True
                    result["task_id"] = self.request.id
                    return result
            
            logger.info(f"✗ CACHE MISS for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Cache check failed, continuing without cache: {e}")
        
        # Update state: Rewriting queries
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Rewriting product information into search queries...',
                'current_step': 'query_rewriting',
                'product_name': query_data.get('product_name', '')
            }
        )
        
        # Create request object
        request = ProductCrawlQuery(**query_data)
        
        # Update state: Searching rulings
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Searching HS code rulings from multiple sources...',
                'current_step': 'searching_rulings',
                'product_name': query_data.get('product_name', '')
            }
        )
        
        # Create orchestrator and run search
        orchestrator = CrawlOrchestrator()
        try:
            result = run_async(orchestrator.crawl_with_product_info_grouped(request))
        except Exception as exc:
            if is_quota_error(exc):
                message = quota_error_detail()
                logger.error("Rulings search failed due to quota: %s", exc)
                self.update_state(
                    state='FAILURE',
                    meta={
                        'status': 'Rulings search failed',
                        'error': message
                    }
                )
                raise RuntimeError(message) from exc
            raise
        
        # Convert to dict
        result_dict = result.dict() if hasattr(result, 'dict') else result.model_dump()
        result_dict["cache_hit"] = False
        result_dict["task_id"] = self.request.id
        
        # Cache the result
        try:
            crawl_cache.set(cache_key, result_dict)
            logger.info(f"✓ Cached result for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Failed to cache result: {e}")
        
        return result_dict
        
    except (ConnectionError, TimeoutError, ResponseError) as e:
        logger.error(f"Redis connection error in task {self.request.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in rulings search task {self.request.id}: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Rulings search failed',
                'error': str(e)
            }
        )
        raise


@celery_app.task(
    bind=True,
    name="crawl_service.tasks.simple_search",
    autoretry_for=(ConnectionError, TimeoutError, ResponseError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def simple_search_task(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async task to perform simple search across all ruling sources.
    
    Args:
        query_data: CrawlRequest dictionary
        
    Returns:
        CrawlResponse dictionary
    """
    from crawl_service.core.models import CrawlRequest
    from crawl_service.core.orchestrator import CrawlOrchestrator
    
    try:
        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Starting simple search...'})
        
        # Check cache first
        cache_key = generate_cache_key(query_data, endpoint="search")
        try:
            if cache_key in crawl_cache:
                logger.info(f"✓ CACHE HIT for task {self.request.id}")
                cached_result = crawl_cache.get(cache_key)
                if cached_result:
                    result = cached_result.copy()
                    result["cache_hit"] = True
                    result["task_id"] = self.request.id
                    return result
            
            logger.info(f"✗ CACHE MISS for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Cache check failed, continuing without cache: {e}")
        
        # Update state
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f"Searching for: {query_data.get('query', '')}...",
                'current_step': 'searching'
            }
        )
        
        # Create request object
        request = CrawlRequest(**query_data)
        
        # Create orchestrator and run search
        orchestrator = CrawlOrchestrator()
        try:
            result = run_async(orchestrator.crawl_all(request))
        except Exception as exc:
            if is_quota_error(exc):
                message = quota_error_detail()
                logger.error("Simple search failed due to quota: %s", exc)
                self.update_state(
                    state='FAILURE',
                    meta={
                        'status': 'Simple search failed',
                        'error': message
                    }
                )
                raise RuntimeError(message) from exc
            raise
        
        # Convert to dict
        result_dict = result.dict() if hasattr(result, 'dict') else result.model_dump()
        result_dict["cache_hit"] = False
        result_dict["task_id"] = self.request.id
        
        # Cache the result
        try:
            crawl_cache.set(cache_key, result_dict)
            logger.info(f"✓ Cached result for task {self.request.id}")
        except (ConnectionError, TimeoutError, ResponseError) as e:
            logger.warning(f"Failed to cache result: {e}")
        
        return result_dict
        
    except (ConnectionError, TimeoutError, ResponseError) as e:
        logger.error(f"Redis connection error in task {self.request.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in simple search task {self.request.id}: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Simple search failed',
                'error': str(e)
            }
        )
        raise

