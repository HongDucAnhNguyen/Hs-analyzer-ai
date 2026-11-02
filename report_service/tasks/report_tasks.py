"""
Celery Tasks for Report Service - Excel Analysis
"""
import logging
import asyncio
from typing import Dict, Any, List
from redis.exceptions import ConnectionError, TimeoutError, ResponseError
from report_service.core.celery_app import celery_app
from report_service.utils.filename_validation import validate_chc_filename
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
    name="report_service.tasks.process_excel_from_minio",
    autoretry_for=(ConnectionError, TimeoutError, ResponseError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def process_excel_from_minio_task(self, object_name: str, input_sections: List[str] = None, prefill_mode: str = "none") -> Dict[str, Any]:
    """
    Async task to process an Excel file from MinIO.
    Downloads, processes, and uploads result back to MinIO.
    
    Args:
        object_name: Object name of the uploaded file in MinIO
        input_sections: Optional list of input sections to fill. Options: tariff_classification,
                   customs_valuation, non_tariff_measures, exim_statistics. Default: all sections.
        prefill_mode: Pre-fill mode for missing Mã NPL/SP. Options: 'none' (default),
                     'rule_based' (pattern matching), 'llm' (rule_based + LLM generation).
        
    Returns:
        Dict with download_url for the result file
    """
    from report_service.utils.minio_client import (
        download_file,
        upload_result_file,
        check_file_exists,
        is_minio_available
    )
    from report_service.utils.excel_processor import (
        parse_excel_file,
        generate_hs_consistency_reports,
        generate_value_variance_report,
        generate_ntm_report,
        generate_combined_excel,
    )
    
    # Convert input_sections to enabled_sections set
    # Mapping: tariff_classification -> "1", customs_valuation -> "2", non_tariff_measures -> "3",
    # exim_statistics -> "exim"
    INPUT_SECTION_MAPPING = {
        "tariff_classification": "1",
        "customs_valuation": "2",
        "non_tariff_measures": "3",
        "exim_statistics": "exim",
    }
    if input_sections is None:
        enabled_sections = {"1", "2", "3", "exim"}  # All enabled by default
    else:
        enabled_sections = {INPUT_SECTION_MAPPING.get(s, s) for s in input_sections}
    
    try:
        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Starting Excel processing...', 'input_sections': input_sections or 'all'})
        
        # Check if MinIO is available
        if not is_minio_available():
            raise Exception("MinIO storage service is not available")
        
        validate_chc_filename(object_name)

        # Check if file exists
        if not check_file_exists(object_name):
            raise Exception(f"File not found in storage: {object_name}")
        
        # Update state: Downloading
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Downloading file from storage...',
                'current_step': 'downloading',
                'input_sections': input_sections or 'all'
            }
        )
        
        # Download file from MinIO
        content = download_file(object_name)
        
        if len(content) == 0:
            raise Exception("Empty file")
        
        logger.info(f"Downloaded file: {object_name}, size: {len(content)} bytes")
        
        # Update state: Parsing
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Parsing Excel file...',
                'current_step': 'parsing',
                'input_sections': input_sections or 'all'
            }
        )
        
        # Parse Excel file
        rows, parse_errors, original_df, original_sheet_name = parse_excel_file(content)
        
        if not rows and parse_errors:
            raise Exception(f"Failed to parse Excel file: {parse_errors[:5]}")
        
        if not rows:
            raise Exception("No valid data rows found in Excel file")
        
        logger.info(f"Parsed {len(rows)} rows from Excel, generating reports for sections: {enabled_sections}...")
        
        # Pre-fill missing Mã NPL/SP based on selected mode
        rule_filled = 0
        llm_filled = 0
        if prefill_mode in ("rule_based", "llm"):
            from report_service.utils.item_code_filler import prefill_item_codes, prefill_item_codes_llm
            
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': f'Pre-filling missing Mã NPL/SP ({prefill_mode})...',
                    'current_step': 'prefilling_item_codes',
                    'prefill_mode': prefill_mode,
                    'rows_parsed': len(rows),
                    'input_sections': input_sections or 'all'
                }
            )
            
            if prefill_mode == "rule_based":
                rows, rule_filled = prefill_item_codes(rows)
                logger.info(f"Pre-filled {rule_filled} missing Mã NPL/SP (rule_based)")
            elif prefill_mode == "llm":
                try:
                    rows, rule_filled, llm_filled = run_async(prefill_item_codes_llm(rows))
                    logger.info(
                        "Pre-filled Mã NPL/SP: %s rule-based + %s LLM",
                        rule_filled,
                        llm_filled
                    )
                except Exception as exc:
                    if is_quota_error(exc):
                        message = quota_error_detail()
                        logger.error("Prefill failed due to quota: %s", exc)
                        raise RuntimeError(message) from exc
                    raise
        
        # Update state: Generating reports
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Generating reports from {len(rows)} rows...',
                'current_step': 'generating_reports',
                'rows_parsed': len(rows),
                'rule_filled_item_codes': rule_filled,
                'llm_filled_item_codes': llm_filled,
                'input_sections': input_sections or 'all'
            }
        )
        
        # Only generate reports for selected sections
        hs_consistency = None
        value_variance = None
        ntm_report = None
        
        # Section 1 (Tariff Classification) -> HS Inconsistency reports
        if "1" in enabled_sections:
            hs_consistency = generate_hs_consistency_reports(rows)
        
        # Section 2 (Customs Valuation) -> Value Variance reports
        if "2" in enabled_sections:
            value_variance = generate_value_variance_report(rows)
        
        # Section 3 (Non-Tariff Measures) -> NTM reports
        if "3" in enabled_sections:
            ntm_report = generate_ntm_report(rows)
        
        # Fetch Train Links for NTM data - only if NTM is generated
        if ntm_report:
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'Fetching Train Links for NTM data...',
                    'current_step': 'fetching_train_links',
                    'rows_parsed': len(rows),
                    'hs_consistency_items': hs_consistency.total_items if hs_consistency else 0,
                    'value_variance_items': value_variance.total_items if value_variance else 0,
                    'input_sections': input_sections or 'all'
                }
            )
            
            # Fetch Train Links (async)
            train_links = run_async(_fetch_train_links(ntm_report.items))
            
            if train_links:
                ntm_report = generate_ntm_report(rows, train_links)
        
        logger.info(
            f"Generated reports: HS Consistency={hs_consistency.total_items if hs_consistency else 0} items, "
            f"Value Variance={value_variance.total_items if value_variance else 0} items, "
            f"NTM={ntm_report.total_items if ntm_report else 0} items"
        )
        
        # Update state: Generating Excel
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Generating combined Excel file...',
                'current_step': 'generating_excel',
                'rows_parsed': len(rows),
                'hs_consistency_items': hs_consistency.total_items if hs_consistency else 0,
                'value_variance_items': value_variance.total_items if value_variance else 0,
                'ntm_items': ntm_report.total_items if ntm_report else 0,
                'input_sections': input_sections or 'all'
            }
        )
        
        # Generate combined Excel file with all sheets, fill columns based on enabled_sections
        excel_buffer = generate_combined_excel(
            hs_consistency, value_variance, ntm_report,
            original_rows=rows, original_df=original_df,
            original_file_content=content,
            original_sheet_name=original_sheet_name,
            enabled_sections=enabled_sections,
        )
        
        # Update state: Uploading result
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Uploading result to storage...',
                'current_step': 'uploading_result',
                'input_sections': input_sections or 'all'
            }
        )
        
        # Upload result to MinIO
        result_content = excel_buffer.getvalue()
        result = upload_result_file(result_content, object_name)
        
        logger.info(f"Uploaded result to MinIO: {result['object_name']}")
        
        return {
            "status": "success",
            "object_name": result["object_name"],
            "download_url": result["download_url"],
            "expires_in_seconds": result["expires_in_seconds"],
            "rows_processed": len(rows),
            "hs_consistency_items": hs_consistency.total_items if hs_consistency else 0,
            "value_variance_items": value_variance.total_items if value_variance else 0,
            "ntm_items": ntm_report.total_items if ntm_report else 0,
            "prefill_mode": prefill_mode,
            "rule_filled_item_codes": rule_filled,
            "llm_filled_item_codes": llm_filled,
            "input_sections_enabled": list(enabled_sections),
            "task_id": self.request.id
        }
        
    except (ConnectionError, TimeoutError, ResponseError) as e:
        logger.error(f"Redis/MinIO connection error in task {self.request.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in Excel processing task {self.request.id}: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Excel processing failed',
                'error': str(e)
            }
        )
        raise


async def _fetch_train_links(ntm_items) -> dict:
    """Fetch Train Links for NTM items"""
    from report_service.core.crawler import TrainsOnlineCrawler
    from report_service.utils.excel_processor import convert_flow_to_lookup_key
    
    train_links = {}
    
    # Prepare unique search items
    items_to_search = []
    seen = set()
    
    for item in ntm_items:
        hs_code_6 = item.hs_code[:6] if item.hs_code else ""
        decision = convert_flow_to_lookup_key(item.qd_1357)
        
        search_key = f"{hs_code_6}:{decision}"
        if search_key not in seen and hs_code_6:
            seen.add(search_key)
            items_to_search.append({
                "hs_code": hs_code_6,
                "decision_1357": decision
            })
    
    if not items_to_search:
        return {}
    
    logger.info(f"Fetching Train Links for {len(items_to_search)} unique HS code + decision combinations...")
    
    try:
        async with TrainsOnlineCrawler() as crawler:
            results = await crawler.batch_search(
                items_to_search,
                max_concurrent=5,
                delay_between_requests=0.3
            )
            
            for search_key, link in results.items():
                if link and link != "NA":
                    train_links[search_key] = link
        
        logger.info(f"Fetched {len(train_links)} Train Links successfully")
        
    except Exception as e:
        logger.error(f"Error fetching Train Links: {e}")
    
    return train_links
