"""
Chapter Classifier
Handles classification for Chapters within a Section
"""
from typing import Dict, Any, Optional
import logfire

from ...api.v1.schemas import ChapterClassification
from ..prompts import (
    get_chapter_prompt_template,
    format_query
)
from ...utils.data_loader import load_chapter_knowledge_base
from .base import create_agent


def classify_chapter(
    query_data: Dict[str, Any],
    section_id: str,
    knowledge_base_folder: str,
    file_name: str,
    file_path: str
) -> Optional[ChapterClassification]:
    """
    Classify query into appropriate Chapter within a given Section.
    Supports multiple LLM providers via pydantic-ai.
    """
    from pathlib import Path
    
    with logfire.span(
        "Classify Chapter",
        classification_level="chapter",
        section_id=section_id,
        product_name=query_data.get('product_name', 'N/A')
    ):
        # Extract chapter IDs from files matching the section
        folder = Path(knowledge_base_folder)
        chapter_ids = []
        
        if folder.exists() and folder.is_dir():
            for json_file in folder.glob(f'Chapter_*_Section_{section_id}_Knowledge_Base.json'):
                # Extract chapter ID from filename (e.g., Chapter_39_Section_VII_Knowledge_Base.json -> 39)
                filename = json_file.stem
                parts = filename.split('_')
                if len(parts) >= 2:
                    chapter_id = parts[1].strip()
                    chapter_ids.append(chapter_id)
        
        if not chapter_ids:
            logfire.warn(f"No chapters found for Section {section_id} in folder {knowledge_base_folder}")
            return None
        
        logfire.info(f"Found {len(chapter_ids)} chapters for Section {section_id}: {chapter_ids}")
        
        chapter_knowledge = load_chapter_knowledge_base(knowledge_base_folder, chapter_ids)
        if not chapter_knowledge:
            logfire.warn(f"Chapter information not found for Section {section_id}. Chapter IDs: {chapter_ids}")
            return None

        agent = create_agent(ChapterClassification, "ChapterClassifier")

        query_details = format_query(query_data)
        prompt_template = get_chapter_prompt_template()
        prompt = prompt_template.format(
            section_id=section_id,
            chapter_knowledge=chapter_knowledge,
            query_details=query_details,
            file_name=file_name,
            file_path=file_path
        )

        try:
            result = agent.run_sync(prompt)
            logfire.info(
                "Chapter classified",
                chapter_id=result.output.selected_chapter.chapter_id,
                chapter_title=result.output.selected_chapter.chapter_title
            )
            return result.output
        except Exception as e:
            logfire.error(f"Error calling LLM (Chapter): {e}")
            return None
