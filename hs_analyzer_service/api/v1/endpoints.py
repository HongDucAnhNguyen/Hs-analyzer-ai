"""API endpoints for HS Code Analyzer Service"""

import logging
from fastapi import APIRouter, HTTPException

from hs_analyzer_service.api.v1.schemas import (
    HSCodeAnalyzeRequest,
    HSCodeAnalyzeResponse
)
from hs_analyzer_service.services.analyzer_service import analyze_hs_codes
from shared.llm_error_utils import is_quota_error, quota_error_detail

router = APIRouter(prefix="/analyze", tags=["HS Analyzer Service"])
logger = logging.getLogger(__name__)


@router.post(
    "/hs-codes",
    response_model=HSCodeAnalyzeResponse,
    summary="Analyze HS code compatibility with product",
    description="""
    Use LLM to analyze and evaluate the compatibility of HS codes with the input product information.
    
    **Input:**
    - Product information (name, description, function, material, etc.)
    - List of HS codes with their occurrence counts in search results
    
    **Output:**
    - Compatibility score (0.0-1.0) for each HS code
    - Legal reasoning and applied GIR rules for each HS code
    - Section and Chapter information for each HS code
    - Recommended HS code (most suitable)
    - Executive summary
    """
)
async def analyze_hs_codes_endpoint(request: HSCodeAnalyzeRequest) -> HSCodeAnalyzeResponse:
    """
    Analyze HS code compatibility with product information.
    
    The LLM will use its knowledge of the HS (Harmonized System) classification
    to evaluate how well each HS code matches the given product.
    """
    try:
        logger.info(f"Received analysis request for product: {request.product.product_name}")
        logger.info(f"Number of HS codes to analyze: {len(request.hs_codes)}")
        
        result = await analyze_hs_codes(
            product=request.product,
            hs_codes=request.hs_codes
        )
        
        return result
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing HS codes: {e}")
        if is_quota_error(e):
            raise HTTPException(status_code=402, detail=quota_error_detail())
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing HS codes: {str(e)}"
        )
