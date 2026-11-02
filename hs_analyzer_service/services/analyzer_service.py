"""HS Code Analyzer Service - Uses LLM to analyze HS code compatibility"""

import os
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from hs_analyzer_service.core.prompts import HS_CODE_ANALYSIS_PROMPT
from hs_analyzer_service.api.v1.schemas import (
    ProductInfo,
    HSCodeCandidate,
    HSCodeAnalysisResult,
    HSCodeAnalyzeResponse,
)

logger = logging.getLogger(__name__)


class HSCodeAnalysisResultLLM(BaseModel):
    """Structured output for single HS code analysis from LLM"""
    hs_code: str = Field(..., description="HS code")
    compatibility_score: float = Field(..., ge=0.0, le=1.0, description="Compatibility score from 0.0 to 1.0")
    hs_code_description: Optional[str] = Field(
        None, 
        description="Description of the HS code according to the Harmonized System"
    )
    section_info: Optional[str] = Field(
        None,
        description="Section information the HS code belongs to"
    )
    chapter_info: Optional[str] = Field(
        None,
        description="Chapter information the HS code belongs to"
    )
    gir_applied: Optional[str] = Field(
        None,
        description="GIR rules applied for this evaluation"
    )
    legal_reasoning: str = Field(
        ...,
        min_length=10,
        description="Legal reasoning for the score (3-5 sentences)"
    )


class HSCodeAnalysisOutputLLM(BaseModel):
    """Structured output for full HS code analysis from LLM"""
    results: List[HSCodeAnalysisResultLLM] = Field(..., description="Analysis results for each HS code")
    recommended_hs_code: Optional[str] = Field(None, description="Recommended HS code")
    executive_summary: str = Field(..., description="Executive summary of the decision")


# Lazy initialization for agent
_hs_analyzer_agent = None


def _get_hs_analyzer_agent():
    """Get or create the HS analyzer agent (lazy initialization)"""
    global _hs_analyzer_agent
    
    if _hs_analyzer_agent is None:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.models.gemini import GeminiModel
        
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        model_name = os.getenv("LLM_MODEL", "gpt-4o")
        
        if provider == "gemini":
            gemini_model = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash-lite")
            model = GeminiModel(gemini_model)
        else:
            # Default to OpenAI
            model = OpenAIModel(model_name)
        
        _hs_analyzer_agent = Agent(
            model=model,
            output_type=HSCodeAnalysisOutputLLM,
            system_prompt="You are an expert in international customs classification (HS System). You analyze products and evaluate HS code compatibility with detailed reasoning in Vietnamese.",
        )
        
        logger.info(f"HS Analyzer Agent initialized with provider: {provider}, model: {model_name}")
    
    return _hs_analyzer_agent


async def analyze_hs_codes(
    product: ProductInfo,
    hs_codes: List[HSCodeCandidate]
) -> HSCodeAnalyzeResponse:
    """
    Analyze and rank HS codes for a given product using LLM.
    
    Args:
        product: Product information
        hs_codes: List of HS code candidates with occurrence counts
        
    Returns:
        HSCodeAnalyzeResponse with analysis results for each HS code
    """
    try:
        # Format HS codes list for prompt
        hs_codes_formatted = "\n".join([
            f"- HS Code: {hc.hs_code} (occurrences: {hc.number_of_occurrences})"
            for hc in hs_codes
        ])
        
        # Build prompt with product info
        prompt_content = HS_CODE_ANALYSIS_PROMPT.format(
            product_name=product.product_name or "",
            science_name=product.science_name or "N/A",
            product_description=product.product_description or "N/A",
            function=product.function or "N/A",
            material=product.material or "N/A",
            structure=product.structure or "N/A",
            specifications=product.specifications or "N/A",
            other_information=product.other_information or "N/A",
            hs_codes_list=hs_codes_formatted
        )
        
        logger.info(f"Analyzing {len(hs_codes)} HS codes for product: {product.product_name}")
        
        # Get agent (lazy initialization) and call LLM with structured output
        agent = _get_hs_analyzer_agent()
        result = await agent.run(prompt_content)
        llm_output = result.output
        
        # Create a map of HS codes to occurrences for quick lookup
        occurrence_map = {hc.hs_code: hc.number_of_occurrences for hc in hs_codes}
        
        # Convert LLM output to API response format
        analysis_results = []
        for res in llm_output.results:
            # Normalize HS code for lookup
            normalized_code = res.hs_code.replace(".", "").replace(" ", "")
            occurrences = occurrence_map.get(normalized_code, 0)
            
            analysis_results.append(HSCodeAnalysisResult(
                hs_code=res.hs_code,
                number_of_occurrences=occurrences,
                compatibility_score=res.compatibility_score,
                hs_code_description=res.hs_code_description,
                section_info=res.section_info,
                chapter_info=res.chapter_info,
                gir_applied=res.gir_applied,
                legal_reasoning=res.legal_reasoning
            ))
        
        # Sort results by compatibility score (descending)
        analysis_results.sort(key=lambda x: x.compatibility_score, reverse=True)
        
        response = HSCodeAnalyzeResponse(
            product_name=product.product_name,
            total_hs_codes_analyzed=len(analysis_results),
            recommended_hs_code=llm_output.recommended_hs_code,
            results=analysis_results,
            executive_summary=llm_output.executive_summary
        )
        
        logger.info(
            f"Analysis complete: {len(analysis_results)} codes analyzed, "
            f"recommended: {llm_output.recommended_hs_code}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error analyzing HS codes: {e}")
        raise


async def analyze_hs_codes_simple(
    product_name: str,
    hs_codes_data: List[Dict[str, Any]]
) -> HSCodeAnalyzeResponse:
    """
    Simplified interface for HS code analysis.
    
    Args:
        product_name: Product name
        hs_codes_data: List of dicts with 'hs_code' and 'number_of_occurrences'
        
    Returns:
        HSCodeAnalyzeResponse with analysis results
    """
    product = ProductInfo(product_name=product_name)
    hs_codes = [
        HSCodeCandidate(
            hs_code=item["hs_code"],
            number_of_occurrences=item.get("number_of_occurrences", 0)
        )
        for item in hs_codes_data
    ]
    
    return await analyze_hs_codes(product, hs_codes)
