"""
Subheading Classifier
Handles classification for Subheadings within a Heading
"""
from typing import Dict, Any, Optional
import logfire

from ...api.v1.schemas import SubheadingClassification
from ..prompts import (
    get_subheading_prompt_template,
    format_query
)
from ...utils.data_loader import load_subheading_knowledge_base
from .base import create_agent


def classify_subheading(
    query_data: Dict[str, Any],
    heading_id: str,
    knowledge_base_file: str
) -> Optional[SubheadingClassification]:
    """
    Classify query into appropriate Subheading within a given Heading.
    Supports multiple LLM providers via pydantic-ai.
    """
    with logfire.span(
        "Classify Subheading",
        classification_level="subheading",
        heading_id=heading_id,
        product_name=query_data.get('product_name', 'N/A')
    ):
        subheading_knowledge = load_subheading_knowledge_base(knowledge_base_file, heading_id)
        if not subheading_knowledge:
            logfire.warn(f"Subheading information not found for Heading {heading_id}")
            return None

        agent = create_agent(SubheadingClassification, "SubheadingClassifier")

        query_details = format_query(query_data)
        prompt_template = get_subheading_prompt_template()
        prompt = prompt_template.format(
            heading_id=heading_id,
            subheading_knowledge=subheading_knowledge,
            query_details=query_details
        )

        try:
            result = agent.run_sync(prompt)
            logfire.info(
                "Subheading classified",
                subheading_id=result.output.selected_subheading.subheading_id,
                subheading_title=result.output.selected_subheading.subheading_title
            )
            return result.output
        except Exception as e:
            logfire.error(f"Error calling LLM (Subheading): {e}")
            return None
