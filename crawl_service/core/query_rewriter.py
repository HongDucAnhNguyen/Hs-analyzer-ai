"""Query rewriting service for crawl"""

import os
import json
import logging
import re
from typing import List
from llama_index.core.llms import ChatMessage

from crawl_service.core.prompts import CRAWL_QUERY_REWRITE_PROMPT

logger = logging.getLogger(__name__)

# Import LLM wrapper from RAG service
try:
    from rag_service.core.llm_wrapper import get_llm
    LLM_AVAILABLE = True
except ImportError as exc:
    # log explicit error for debugging
    logger.warning(
        "RAG service LLM wrapper not available, query rewriting will use fallback. Error: %s",
        exc,
    )
    LLM_AVAILABLE = False


def _get_llm():
    """Get LLM instance with fallback - uses same config as RAG service"""
    if not LLM_AVAILABLE:
        raise ImportError("LLM dependencies not available")
    
    # Use same LLM configuration as RAG service
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    temperature = 0.0  # Use 0 for consistent results like RAG service
    
    logger.info(f"Crawl service using LLM: {provider}/{model} (temp={temperature})")
    return get_llm(provider=provider, model=model, temperature=temperature)


async def rewrite_product_to_queries(
    product_name: str,
    science_name: str = "",
    product_description: str = "",
    function: str = "",
    material: str = "",
    structure: str = "",
    specifications: str = "",
    predicted_heading: str = ""
) -> List[str]:
    """
    Rewrite product information into 3 distinct search queries. (new schema)
    
    Args:
        product_name: Main product name
        science_name: Scientific or technical name
        product_description: Product description
        function: Primary function
        material: Main material
        structure: Physical structure
        specifications: Key specifications
        predicted_heading: Predicted heading
        
    Returns:
        List of 3 search queries
    """
    try:
        llm = _get_llm()
        
        # Format prompt with product information
        prompt_content = CRAWL_QUERY_REWRITE_PROMPT.format(
            product_name=product_name or "",
            science_name=science_name or "",
            product_description=product_description or "",
            function=function or "",
            material=material or "",
            structure=structure or "",
            specifications=specifications or "",
            predicted_heading=predicted_heading or ""
        )
        
        # Call LLM
        message = ChatMessage(role="user", content=prompt_content)
        response = await llm.achat([message])
        result = response.message.content.strip()
        
        # Parse response - prefer JSON array, fallback to line parsing
        queries: List[str] = []
        cleaned_result = result.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(cleaned_result)
            if isinstance(parsed, list):
                queries = [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", cleaned_result)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list):
                        queries = [
                            str(item).strip() for item in parsed if str(item).strip()
                        ]
                except json.JSONDecodeError:
                    queries = []
            if not queries:
                queries = [q.strip() for q in cleaned_result.split('\n') if q.strip()]
        
        # Ensure we have exactly 3 queries
        if len(queries) < 3:
            # Fallback: use product name variations
            logger.warning(f"LLM returned {len(queries)} queries, using fallback")
            queries = _fallback_queries(product_name, science_name, product_description)
        elif len(queries) > 3:
            # Take first 3
            queries = queries[:3]
        
        logger.info(f"Rewritten queries: {queries}")
        return queries
        
    except Exception as e:
        logger.error(f"Error rewriting queries: {e}")
        # Fallback to simple query generation
        return _fallback_queries(product_name, science_name, product_description)


def _fallback_queries(product_name: str, science_name: str = "", product_description: str = "") -> List[str]:
    """
    Fallback query generation when LLM is not available.
    
    Args:
        product_name: Main product name
        science_name: Scientific name
        product_description: Product description
        
    Returns:
        List of 3 queries
    """
    queries = []
    
    # Query 1: Use product name
    if product_name:
        queries.append(product_name.strip())
    
    # Query 2: Use science name if available
    if science_name and science_name.strip():
        queries.append(science_name.strip())
    
    # Query 3: Extract key terms from description
    if product_description and len(queries) < 3:
        # Simple extraction: take first few meaningful words
        words = product_description.split()[:5]
        if words:
            queries.append(' '.join(words))
    
    # Ensure we have at least 3 queries (duplicate if needed)
    while len(queries) < 3:
        if queries:
            queries.append(queries[0])
        else:
            queries.append(product_name or "product")
    
    return queries[:3]
