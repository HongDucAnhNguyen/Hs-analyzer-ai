"""Service for generating reasons with relevance scoring using LLM"""

import os
import logging
import json
from typing import Dict, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.models.gemini import GeminiModel

from crawl_service.core.prompts import CRAWL_REASON_GENERATION_PROMPT

logger = logging.getLogger(__name__)


class ReasonWithScore(BaseModel):
    """Structured output for reason generation with relevance scoring"""
    relevance_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Relevance score from 0.0 (not relevant) to 1.0 (highly relevant)"
    )
    reason: str = Field(
        ...,
        min_length=10,
        description="Vietnamese explanation (1-2 sentences) of why the ruling is relevant"
    )


def _get_llm_model():
    """Get LLM model - uses same config as RAG and Classifier services"""
    provider = os.getenv("LLM_PROVIDER", "openai")
    model_name = os.getenv("LLM_MODEL", "gpt-4o")
    
    if provider == "openai":
        return OpenAIModel(model_name)
    elif provider == "gemini":
        return GeminiModel(model_name)
    else:
        # Default to OpenAI
        return OpenAIModel(model_name)


# Create agent for reason generation with structured output
reason_agent = Agent(
    model=_get_llm_model(),
    output_type=ReasonWithScore,
    system_prompt="You are an expert at analyzing customs rulings and evaluating their relevance with scoring in Vietnamese.",
)


async def generate_reason_with_score(
    technical_name: str,
    ruling_content: str,
    product_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate a Vietnamese reason with relevance score explaining why a ruling is relevant.
    
    Args:
        technical_name: The search query/technical name used
        ruling_content: Full content of the ruling
        product_info: Full product information dict containing:
            - product_name: Product name
            - science_name: Scientific/technical name
            - product_description: Product description
            - function: Product function
            - material: Material composition
            - structure: Product structure
            - specifications: Technical specifications
        
    Returns:
        Dict with 'relevance_score' (float 0.0-1.0) and 'reason' (str)
    """
    import logfire
    
    with logfire.span("generate_reason_with_score", technical_name=technical_name):
        try:
            # Truncate ruling content if too long (keep first 3000 chars for better context)
            truncated_content = ruling_content[:3000] if len(ruling_content) > 3000 else ruling_content
            
            # Format prompt with full product information
            prompt_content = CRAWL_REASON_GENERATION_PROMPT.format(
                product_name=product_info.get("product_name", ""),
                science_name=product_info.get("science_name", ""),
                product_description=product_info.get("product_description", ""),
                function=product_info.get("function", ""),
                material=product_info.get("material", ""),
                structure=product_info.get("structure", ""),
                specifications=product_info.get("specifications", ""),
                technical_name=technical_name,
                ruling_content=truncated_content
            )
            
            # Call LLM using Pydantic AI with structured output (automatically tracked by logfire)
            result = await reason_agent.run(prompt_content)
            reason_data = result.output  # Get the structured ReasonWithScore object
            
            output = {
                "relevance_score": reason_data.relevance_score,
                "reason": reason_data.reason.strip()
            }
            
            logfire.info(
                f"Generated reason with score",
                score=output["relevance_score"],
                reason_length=len(output["reason"])
            )
            logger.info(
                f"Generated reason for '{technical_name}': "
                f"score={output['relevance_score']:.2f}, "
                f"reason={output['reason'][:80]}..."
            )
            return output
            
        except Exception as e:
            logger.error(f"Error generating reason with score: {e}")
            # Fallback to simple reason with low score
            return _fallback_reason(technical_name, ruling_content)


# Legacy function for backward compatibility (now calls new version)
async def generate_reason(
    technical_name: str,
    ruling_content: str,
    product_name: str = "",
    science_name: str = "",
    product_description: str = ""
) -> str:
    """
    Legacy function - generates reason without score.
    Use generate_reason_with_score for new code.
    
    Returns:
        A short Vietnamese explanation (1-2 sentences)
    """
    product_info = {
        "product_name": product_name,
        "science_name": science_name,
        "product_description": product_description,
        "function": "",
        "material": "",
        "structure": "",
        "specifications": ""
    }
    
    result = await generate_reason_with_score(technical_name, ruling_content, product_info)
    return result["reason"]


def _fallback_reason(technical_name: str, ruling_content: str) -> Dict[str, Any]:
    """
    Fallback reason generation when LLM is not available.
    Extracts key info from ruling content.
    
    Args:
        technical_name: The search query used
        ruling_content: Full content of the ruling
        
    Returns:
        Dict with 'relevance_score' (float) and 'reason' (str)
    """
    # Try to extract HS code from content
    import re
    hs_codes = re.findall(r'\d{4}\.\d{2}(?:\.\d{2})?(?:\.\d{2})?', ruling_content[:1000])
    
    if hs_codes:
        return {
            "relevance_score": 0.5,  # Default medium relevance
            "reason": f"Quyết định liên quan đến '{technical_name}', đề cập mã phân loại {hs_codes[0]}."
        }
    else:
        return {
            "relevance_score": 0.4,  # Default low-medium relevance
            "reason": f"Quyết định hải quan liên quan đến '{technical_name}'."
        }
