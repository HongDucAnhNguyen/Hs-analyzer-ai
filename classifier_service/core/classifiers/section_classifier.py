"""
Section Classifier
Handles pre-classification and classification for Sections
"""
from typing import Dict, Any, Optional, Literal
import logfire

from ...api.v1.schemas import (
    SectionPreClassification,
    SectionClassification
)
from ..prompts import (
    get_section_pre_classify_prompt_template,
    get_section_prompt_template,
    format_query
)
from .base import create_agent
from .section_rerank import pre_classify_section_with_rerank


def pre_classify_section(
    query_data: Dict[str, Any], 
    section_summaries: str = None,
    method: Literal["llm", "rerank"] = "rerank"
) -> Optional[SectionPreClassification]:
    """
    Step 1: Pre-classify to identify potentially relevant sections (maximum 3).
    
    Args:
        query_data: Dictionary with product information
        section_summaries: Summary information for LLM method (required if method="llm")
        method: Classification method - "llm" (default) or "rerank"
    
    Returns:
        SectionPreClassification with candidate section IDs
    
    Methods:
        - llm: Uses LLM with prompt-based classification (slower, more accurate for nuanced cases)
        - rerank: Uses Cohere Rerank (faster, good for most cases)
    """
    if method == "rerank":
        # Use Cohere Rerank method
        logfire.info("Using rerank method for section pre-classification")
        result = pre_classify_section_with_rerank(query_data, top_n=3)
        
        if result is None:
            logfire.warning(
                "Rerank returned no suitable sections (all scores below threshold 0.1)",
                product_name=query_data.get('product_name', 'N/A')
            )
            # Fall back to LLM method if summaries are available
            if section_summaries:
                logfire.info("Falling back to LLM pre-classification")
                return pre_classify_section(query_data, section_summaries, method="llm")
		
        return result
    
    # Use LLM method (default)
    with logfire.span(
        "Pre-Classify Section",
        classification_level="section_pre",
        product_name=query_data.get('product_name', 'N/A')
    ):
        if not section_summaries:
            logfire.error("Section summaries is empty")
            return None

        agent = create_agent(SectionPreClassification, "SectionPreClassifier")

        query_details = format_query(query_data)
        prompt_template = get_section_pre_classify_prompt_template()
        prompt = prompt_template.format(
            section_summaries=section_summaries,
            query_details=query_details
        )

        try:
            result = agent.run_sync(prompt)
            recommended_ids = [
                item.section_id
                for item in (result.output.recommended_sections or [])
                if item.section_id
            ]
            logfire.info(
                "Section pre-classified",
                recommended_section_ids=recommended_ids
            )
            return result.output
        except Exception as e:
            logfire.error(f"Error during section pre-classification: {e}")
            return None


def classify_section(query_data: Dict[str, Any], knowledge_base: str) -> Optional[SectionClassification]:
    """
    Step 2: Classify query into appropriate Section with detailed information.
    Supports multiple LLM providers via pydantic-ai.
    """
    with logfire.span(
        "Classify Section",
        classification_level="section",
        product_name=query_data.get('product_name', 'N/A')
    ):
        if not knowledge_base:
            logfire.error("Knowledge base is empty, cannot classify section")
            return None

        agent = create_agent(SectionClassification, "SectionClassifier")

        query_details = format_query(query_data)
        prompt_template = get_section_prompt_template()
        prompt = prompt_template.format(
            knowledge_base=knowledge_base,
            query_details=query_details
        )

        try:
            result = agent.run_sync(prompt)
            selected_section = result.output.selected_section
            logfire.info(
                "Section classified",
                section_id=selected_section.section_id,
                section_title=selected_section.section_title
            )
            return result.output
        except Exception as e:
            logfire.error(f"Error calling LLM (Section): {e}")
            return None
