"""API endpoints for Report Service v1

Report Endpoints:
- POST /report/analyze - Upload Excel file → Return Excel file (direct)
- GET /report/upload-url - Get presigned URL for uploading large files to MinIO
- POST /report/process - Process file from MinIO and return download URL
- POST /report/process/async - Process file asynchronously (task-based)
- GET /report/task/{task_id} - Check task status
"""

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from report_service.utils.excel_processor import (
    parse_excel_file,
    generate_hs_consistency_reports,
    generate_value_variance_report,
    generate_ntm_report, 
    generate_combined_excel,
    convert_flow_to_lookup_key,
)
from report_service.utils.item_code_filler import prefill_item_codes, prefill_item_codes_llm
from report_service.core.crawler import TrainsOnlineCrawler
from report_service.utils.filename_validation import validate_chc_filename
from report_service.api.v1.schemas import (
    TaskStatusResponse,
    ProcessAsyncRequest,
    ProcessAsyncResponse,
    DatasetProcessAsyncRequest,
    DatasetProcessAsyncResponse,
    ManualInputExportRequest,
    InputSheetOptionsResponse,
    INPUT_SHEET_OPTIONS,
    InputSection,
    PrefillMode,
    get_enabled_sections,
)
from report_service.tasks.report_tasks import process_excel_from_minio_task
from report_service.core.celery_app import celery_app
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["Report Service - Excel Analysis"])


# ============================================================================
# Pydantic models for MinIO API
# ============================================================================

class UploadUrlResponse(BaseModel):
    """Response for upload URL request"""
    upload_url: str
    object_name: str
    bucket: str
    expires_in_seconds: int
    content_type: str


class ProcessRequest(BaseModel):
    """Request to process a file from MinIO"""
    object_name: str
    input_sections: Optional[List[InputSection]] = None  # None = all sections
    prefill_mode: PrefillMode = PrefillMode.NONE  # Pre-fill mode for missing Mã NPL/SP


class ProcessResponse(BaseModel):
    """Response after processing file"""
    status: str
    object_name: str
    download_url: str
    expires_in_seconds: int
    message: Optional[str] = None


async def fetch_train_links(ntm_items) -> dict:
    """Fetch Train Links for NTM items
    
    Args:
        ntm_items: List of NTMItem objects with qd_1357 and hs_code
        
    Returns:
        Dict mapping "hs_code_6:import/export" to train_link URL
    """
    train_links = {}
    
    # Prepare unique search items
    items_to_search = []
    seen = set()
    
    for item in ntm_items:
        hs_code_6 = item.hs_code[:6] if item.hs_code else ""
        # Convert Vietnamese flow (Nhập/Xuất) to lookup key (import/export)
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
            
            # Map results to our format
            for search_key, link in results.items():
                if link and link != "NA":
                    train_links[search_key] = link
        
        logger.info(f"Fetched {len(train_links)} Train Links successfully")
        
    except Exception as e:
        logger.error(f"Error fetching Train Links: {e}")
    
    return train_links


@router.post("/analyze")
async def analyze_excel(
    file: UploadFile = File(..., description="Excel file (.xlsx, .xls, .xlsb) to analyze"),
    input_sections: Optional[List[InputSection]] = Query(
        default=None,
        description="Input sections to fill in input_data: tariff_classification, customs_valuation, non_tariff_measures, exim_statistics. Default: all sections."
    ),
    prefill_mode: PrefillMode = Query(
        default=PrefillMode.NONE,
        description="Pre-fill mode for missing Mã NPL/SP: 'none' (default), 'rule_based' (fast), 'llm' (rule_based + LLM)."
    )
):
    """
    Input: Excel file (.xlsx, .xls, .xlsb)
    
    Output: Excel file with all report sheets:
    - Input Data: Original data with impact references (columns filled based on input_sections)
    - HS Inconsistency: Group by Flow → Mã loại hình → Mã NPL/SP → Mã HS
    - HS Inconsistency (to collect): Top 10 NPL/SP for data collection
    - Value Variance: Group by Flow → Điều kiện giá hóa đơn → Mã NPL/SP
    - Non-Tariff Measures: Group by QĐ 1357 → HS Code, with Train Links
    
    Query params:
    - input_sections: List of input sections to fill. Options: tariff_classification, customs_valuation, non_tariff_measures, exim_statistics
    - prefill_mode: Pre-fill mode for missing Mã NPL/SP. Options: none (default), rule_based, llm
    """
    enabled_sections = get_enabled_sections(input_sections)
    
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    valid_extensions = ('.xlsx', '.xls', '.xlsb')
    if not file.filename.lower().endswith(valid_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Please upload an Excel file ({', '.join(valid_extensions)})"
        )

    try:
        validate_chc_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
    try:
        # Read file content
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        logger.info(f"Received Excel file: {file.filename}, size: {len(content)} bytes")
        
        # Parse Excel file
        rows, parse_errors, original_df, original_sheet_name = parse_excel_file(content)
        logger.info(f"Original sheet name: {original_sheet_name}")
        
        if not rows and parse_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Failed to parse Excel file",
                    "errors": parse_errors[:10]
                }
            )
        
        if not rows:
            raise HTTPException(
                status_code=400,
                detail="No valid data rows found in Excel file"
            )
        
        logger.info(f"Parsed {len(rows)} rows from Excel, generating reports for sections: {enabled_sections}...")
        
        # Pre-fill missing Mã NPL/SP based on selected mode
        rule_filled = 0
        llm_filled = 0
        if prefill_mode == PrefillMode.RULE_BASED:
            rows, rule_filled = await asyncio.to_thread(prefill_item_codes, rows)
            logger.info(f"Pre-filled {rule_filled} missing Mã NPL/SP (rule_based)")
        elif prefill_mode == PrefillMode.LLM:
            rows, rule_filled, llm_filled = await prefill_item_codes_llm(rows)
            logger.info(f"Pre-filled Mã NPL/SP: {rule_filled} rule-based + {llm_filled} LLM")
        
        # Only generate reports for selected sections
        hs_consistency = None
        value_variance = None
        ntm_report = None
        tasks = []
        task_names = []
        
        # Section 1 (Tariff Classification) -> HS Inconsistency reports
        if "1" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_hs_consistency_reports, rows))
            task_names.append('hs')
        
        # Section 2 (Customs Valuation) -> Value Variance reports
        if "2" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_value_variance_report, rows))
            task_names.append('vv')
        
        # Section 3 (Non-Tariff Measures) -> NTM reports
        if "3" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_ntm_report, rows))
            task_names.append('ntm')
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for name, result in zip(task_names, results):
                if name == 'hs':
                    hs_consistency = result
                elif name == 'vv':
                    value_variance = result
                elif name == 'ntm':
                    ntm_report = result

        # Fetch Train Links from TRAINS service (async) - only if NTM is generated
        if ntm_report:
            train_links = await fetch_train_links(ntm_report.items)
            
            # Regenerate NTM report with train links if any
            if train_links:
                ntm_report = await asyncio.to_thread(generate_ntm_report, rows, train_links)
        
        logger.info(
            f"Generated reports: HS Consistency={hs_consistency.total_items if hs_consistency else 0} items, "
            f"Value Variance={value_variance.total_items if value_variance else 0} items, "
            f"NTM={ntm_report.total_items if ntm_report else 0} items"
        )

        # Generate combined Excel file with selected sheets only
        excel_buffer = generate_combined_excel(
            hs_consistency,
            value_variance,
            ntm_report,
            original_rows=rows,
            original_df=original_df,
            original_file_content=content,
            original_sheet_name=original_sheet_name,
            enabled_sections=enabled_sections,
        )
        
        # Generate output filename from input filename
        base_name = file.filename.rsplit('.', 1)[0] if file.filename else "report"
        output_filename = f"{base_name}_analysis.xlsx"
        
        logger.info(f"Returning Excel file: {output_filename}, enabled_sections={enabled_sections}, prefill_mode={prefill_mode.value}, rule_filled={rule_filled}, llm_filled={llm_filled}")
        
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{output_filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing Excel file: {e}")
        import traceback
        logger.error(traceback.format_exc())
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


# ============================================================================
# MinIO-based APIs for large file handling
# ============================================================================

@router.get("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    filename: str = Query(..., description="Original filename (e.g., 'report.xlsx')")
):
    """
    Get a presigned URL for uploading a large Excel file to MinIO.
    
    Flow:
    1. Frontend calls this API with filename
    2. Backend returns presigned URL
    3. Frontend uploads file directly to MinIO using the URL
    4. Frontend calls /process with object_name to process the file
    
    Args:
        filename: Original filename for the Excel file
        
    Returns:
        UploadUrlResponse with presigned URL and metadata
    """
    try:
        from report_service.utils.minio_client import generate_upload_url, is_minio_available
        
        # Check if MinIO is available
        if not is_minio_available():
            raise HTTPException(
                status_code=503,
                detail="MinIO storage service is not available. Please start MinIO first or use /analyze endpoint for direct upload."
            )

        result = generate_upload_url(filename)
        
        logger.info(f"Generated upload URL for: {filename} -> {result['object_name']}")
        
        return UploadUrlResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating upload URL: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating upload URL: {str(e)}")


@router.post("/process", response_model=ProcessResponse)
async def process_uploaded_file(request: ProcessRequest):
    """
    Process an Excel file that was uploaded to MinIO.
    
    Flow:
    1. Download file from MinIO
    2. Process (parse, generate reports)
    3. Upload result to MinIO
    4. Return download URL
    
    Args:
        request: ProcessRequest with object_name, optional input_sections, and prefill_mode
        
    Returns:
        ProcessResponse with download URL for the result
    """
    enabled_sections = get_enabled_sections(request.input_sections)
    prefill_mode = request.prefill_mode
    
    try:
        from report_service.utils.minio_client import (
            download_file,
            upload_result_file,
            check_file_exists,
            is_minio_available
        )
        
        # Check if MinIO is available
        if not is_minio_available():
            raise HTTPException(
                status_code=503,
                detail="MinIO storage service is not available. Please start MinIO first."
            )
        
        object_name = request.object_name

        try:
            validate_chc_filename(object_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        
        # Check if file exists
        if not check_file_exists(object_name):
            raise HTTPException(
                status_code=404,
                detail=f"File not found in storage: {object_name}"
            )
        
        logger.info(f"Processing file from MinIO: {object_name}")
        
        # Download file from MinIO
        content = download_file(object_name)
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        logger.info(f"Downloaded file: {object_name}, size: {len(content)} bytes")
        
        # Parse Excel file
        rows, parse_errors, original_df, original_sheet_name = parse_excel_file(content)
        logger.info(f"Original sheet name: {original_sheet_name}")
        
        if not rows and parse_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Failed to parse Excel file",
                    "errors": parse_errors[:10]
                }
            )
        
        if not rows:
            raise HTTPException(
                status_code=400,
                detail="No valid data rows found in Excel file"
            )
        
        logger.info(f"Parsed {len(rows)} rows from Excel, generating reports for sections: {enabled_sections}...")
        
        # Pre-fill missing Mã NPL/SP based on selected mode
        rule_filled = 0
        llm_filled = 0
        if prefill_mode == PrefillMode.RULE_BASED:
            rows, rule_filled = await asyncio.to_thread(prefill_item_codes, rows)
            logger.info(f"Pre-filled {rule_filled} missing Mã NPL/SP (rule_based)")
        elif prefill_mode == PrefillMode.LLM:
            rows, rule_filled, llm_filled = await prefill_item_codes_llm(rows)
            logger.info(f"Pre-filled Mã NPL/SP: {rule_filled} rule-based + {llm_filled} LLM")
        
        # Only generate reports for selected sections
        hs_consistency = None
        value_variance = None
        ntm_report = None
        
        tasks = []
        task_names = []
        
        # Section 1 (Tariff Classification) -> HS Inconsistency reports
        if "1" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_hs_consistency_reports, rows))
            task_names.append('hs')
        
        # Section 2 (Customs Valuation) -> Value Variance reports
        if "2" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_value_variance_report, rows))
            task_names.append('vv')
        
        # Section 3 (Non-Tariff Measures) -> NTM reports
        if "3" in enabled_sections:
            tasks.append(asyncio.to_thread(generate_ntm_report, rows))
            task_names.append('ntm')
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for name, result in zip(task_names, results):
                if name == 'hs':
                    hs_consistency = result
                elif name == 'vv':
                    value_variance = result
                elif name == 'ntm':
                    ntm_report = result
        
        # Fetch Train Links from TRAINS service (async) - only if NTM is generated
        if ntm_report:
            train_links = await fetch_train_links(ntm_report.items)
            
            # Regenerate NTM report with train links if any
            if train_links:
                ntm_report = await asyncio.to_thread(generate_ntm_report, rows, train_links)
        
        logger.info(
            f"Generated reports: HS Consistency={hs_consistency.total_items if hs_consistency else 0} items, "
            f"Value Variance={value_variance.total_items if value_variance else 0} items, "
            f"NTM={ntm_report.total_items if ntm_report else 0} items"
        )
        
        # Generate combined Excel file with selected sheets only
        excel_buffer = generate_combined_excel(
            hs_consistency,
            value_variance,
            ntm_report,
            original_rows=rows,
            original_df=original_df,
            original_file_content=content,
            original_sheet_name=original_sheet_name,
            enabled_sections=enabled_sections,
        )
        
        # Upload result to MinIO
        result_content = excel_buffer.getvalue()
        result = upload_result_file(result_content, object_name)
        
        logger.info(f"Uploaded result to MinIO: {result['object_name']}, enabled_sections={enabled_sections}, prefill_mode={prefill_mode.value}, rule_filled={rule_filled}, llm_filled={llm_filled}")
        
        return ProcessResponse(
            status="success",
            object_name=result["object_name"],
            download_url=result["download_url"],
            expires_in_seconds=result["expires_in_seconds"],
            message=f"Processed {len(rows)} rows successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        import traceback
        logger.error(traceback.format_exc())
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/manual-input/export")
async def export_manual_input(request: ManualInputExportRequest):
    """Build and return a styled manual input export Excel file."""
    from report_service.services.manual_input_export import build_manual_input_export

    payload = request.model_dump()
    excel_content = build_manual_input_export(payload)
    file_name = f"e-tariff-manual-input-{datetime.utcnow().strftime('%Y-%m-%d')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )


# ============================================================================
# Async Task-based APIs for Report Service (Polling Pattern)
# ============================================================================

@router.post("/process/async", response_model=ProcessAsyncResponse, tags=["Report Service - Excel Analysis"])
async def process_uploaded_file_async(request: ProcessAsyncRequest):
    """
    Submit an asynchronous Excel processing task.
    
    Use this endpoint for large files or when you don't want to wait for processing.
    
    Flow:
    1. Upload file to MinIO using /report/upload-url
    2. Call this endpoint with the object_name and optional input_sections
    3. Poll /report/task/{task_id} for status
    4. When SUCCESS, get download_url from result
    
    Args:
        request: ProcessAsyncRequest with object_name and optional input_sections
        
    Returns:
        ProcessAsyncResponse with task_id for polling
    """
    # Convert input_sections to list of strings for Celery serialization
    input_sections_list = [s.value for s in request.input_sections] if request.input_sections else None
    prefill_mode_str = request.prefill_mode.value  # Serialize enum to string for Celery
    
    try:
        from report_service.utils.minio_client import check_file_exists, is_minio_available
        
        # Check if MinIO is available
        if not is_minio_available():
            raise HTTPException(
                status_code=503,
                detail="MinIO storage service is not available. Please start MinIO first."
            )
        
        # Check if file exists
        if not check_file_exists(request.object_name):
            raise HTTPException(
                status_code=404,
                detail=f"File not found in storage: {request.object_name}"
            )

        try:
            validate_chc_filename(request.object_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        
        # Submit task to Celery with input_sections and prefill_mode parameters
        task = process_excel_from_minio_task.delay(request.object_name, input_sections_list, prefill_mode_str)
        
        logger.info(f"✓ Submitted async Excel processing task {task.id} for {request.object_name}, input_sections: {input_sections_list or 'all'}, prefill_mode: {prefill_mode_str}")
        
        return ProcessAsyncResponse(
            task_id=task.id,
            status="PENDING",
            message="Excel processing task submitted successfully. Use /report/task/{task_id} to check status."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting async processing task: {e}")
        raise HTTPException(status_code=500, detail=f"Error submitting task: {str(e)}")


@router.get("/task/{task_id}", response_model=TaskStatusResponse, tags=["Report Service - Excel Analysis"])
def get_report_task_status(task_id: str):
    """
    Check the status of an asynchronous Excel processing task.
    
    Status values:
    - PENDING: Task is waiting in queue
    - STARTED: Task has started processing
    - PROGRESS: Task is in progress (progress info available)
    - SUCCESS: Task completed successfully (result contains download_url)
    - FAILURE: Task failed (error contains error message)
    
    When SUCCESS, the result contains:
    - download_url: Presigned URL to download the processed Excel file
    - object_name: Object name in MinIO
    - rows_processed: Number of rows processed
    - hs_consistency_items, value_variance_items, ntm_items: Report counts
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
            "current_step": info.get("current_step", "unknown"),
            "rows_parsed": info.get("rows_parsed"),
            "hs_consistency_items": info.get("hs_consistency_items"),
            "value_variance_items": info.get("value_variance_items"),
            "ntm_items": info.get("ntm_items"),
        }
    
    elif task_result.status == "SUCCESS":
        result = task_result.result
        response_data["result"] = result
    
    elif task_result.status == "FAILURE":
        response_data["error"] = str(task_result.info)
    
    return TaskStatusResponse(**response_data)




# ============================================================================
# Async Task-based APIs for E-tariff Dataset Input
# ============================================================================

@router.post(
    "/e-tariff/process/async",
    response_model=DatasetProcessAsyncResponse,
    tags=["Report Service - E-tariff Dataset"]
)
async def process_etariff_dataset_async(request: DatasetProcessAsyncRequest):
    """
    Submit an asynchronous E-tariff dataset processing task.

    Flow:
    1. Upload file to MinIO using /report/upload-url
    2. Call this endpoint with object_name
    3. Poll /report/e-tariff/task/{task_id} for status
    """
    try:
        from report_service.utils.minio_client import check_file_exists, is_minio_available

        if not is_minio_available():
            raise HTTPException(
                status_code=503,
                detail="MinIO storage service is not available. Please start MinIO first."
            )

        if not check_file_exists(request.object_name):
            raise HTTPException(
                status_code=404,
                detail=f"File not found in storage: {request.object_name}"
            )

        from report_service.tasks.etariff_dataset_tasks import (
            process_etariff_dataset_task
        )

        task = process_etariff_dataset_task.delay(request.object_name)
        logger.info(
            "✓ Submitted E-tariff dataset task %s for %s",
            task.id,
            request.object_name
        )

        return DatasetProcessAsyncResponse(
            task_id=task.id,
            status="PENDING",
            message=(
                "Dataset processing task submitted successfully. "
                "Use /report/e-tariff/task/{task_id} to check status."
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error submitting dataset task: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Error submitting dataset task: {str(exc)}"
        ) from exc


@router.get(
    "/e-tariff/task/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Report Service - E-tariff Dataset"]
)
def get_etariff_dataset_task_status(task_id: str):
    """Check the status of an E-tariff dataset processing task."""
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
            "current_step": info.get("current_step", "unknown"),
            "rows_processed": info.get("rows_processed"),
            "total_rows": info.get("total_rows")
        }
    elif task_result.status == "SUCCESS":
        response_data["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response_data["error"] = str(task_result.info)

    return TaskStatusResponse(**response_data)


# ============================================================================
# Input Sheet Options API
# ============================================================================

@router.get("/input-sheets", response_model=InputSheetOptionsResponse, tags=["Report Configuration"])
def get_input_sheet_options():
    """
    Get available input sheet options for report generation.
    
    Returns a list of sheet option names that can be selected for processing:
    
    - Tariff Classification: sections 1.1 + 1.2 (Consistency & Accuracy test)
    - Customs Valuation: sections 2.1 + 2.2 + 2.3 (RPT, Variance, Additions/deductions check)
    - Non-Tariff Measures check: sections 3.1 + 3.2 (Chemical & Non-chemical goods)
    - EXIM Statistics: section 1.0 (EXIM overview)

    When selected:
    - Only the corresponding sheets will be created
    - Results will be filled in the input_data sheet columns
    - Unselected sections will have empty columns (headers still present)
    
    Returns:
        InputSheetOptionsResponse with list of input_sections values
    """
    return InputSheetOptionsResponse(input_sections=INPUT_SHEET_OPTIONS)
