"""
Heading Classifier
Handles classification for Headings within a Chapter
"""
from typing import Dict, Any, Optional
import logfire

from ...api.v1.schemas import HeadingClassification
from ..prompts import (
    get_heading_prompt_template,
    format_query
)
from ...utils.data_loader import load_heading_knowledge_base
from .base import create_agent


def classify_heading(
    query_data: Dict[str, Any],
    chapter_id: str,
    knowledge_base_folder: str
) -> Optional[HeadingClassification]:
    """
    Classify query into appropriate Heading within a given Chapter.
    Supports multiple LLM providers via pydantic-ai.
    """
    with logfire.span(
        "Classify Heading",
        classification_level="heading",
        chapter_id=chapter_id,
        product_name=query_data.get('product_name', 'N/A')
    ):
        heading_knowledge = load_heading_knowledge_base(knowledge_base_folder, chapter_id)
        if not heading_knowledge:
            logfire.warn(f"Heading information not found for Chapter {chapter_id}")
            return None

        agent = create_agent(HeadingClassification, "HeadingClassifier")

        query_details = format_query(query_data)
        prompt_template = get_heading_prompt_template()
        prompt = prompt_template.format(
            chapter_id=chapter_id,
            heading_knowledge=heading_knowledge,
            query_details=query_details
        )

        try:
            result = agent.run_sync(prompt)
            logfire.info(
                "Heading classified",
                heading_id=result.output.selected_heading.heading_id,
                heading_title=result.output.selected_heading.heading_title
            )
            return result.output
        except Exception as e:
            logfire.error(f"Error calling LLM (Heading): {e}")
            return None
