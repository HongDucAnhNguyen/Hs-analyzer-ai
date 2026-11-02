import json
import logging
import os
from typing import Callable, Optional, Dict, Any, List
from classifier_service.core.classifiers import (
    pre_classify_section,
    classify_section,
    classify_chapter,
    classify_heading,
    classify_subheading
)
from classifier_service.utils.data_loader import (
    load_section_summaries_only,
    load_section_details
)

# Define paths relative to the project root
section_kb_folder = 'classifier_service/data/sections_knownledge_base'
chapter_kb_folder = 'classifier_service/data/chapters_knowledge_base'
heading_kb_folder = """classifier_service/data/headings_knowledge_base/Headings_Output_Chapter_{chapter_id}_Section_{section_id}"""
subheading_kb_file = """classifier_service/data/headings_knowledge_base/Headings_Output_Chapter_{chapter_id}_Section_{section_id}/Heading_{heading_id}_Chapter_{chapter_id}_Section_{section_id}_Knowledge_Base.json"""

# Load section summaries for pre-classification
section_summaries = load_section_summaries_only(section_kb_folder)

logger = logging.getLogger(__name__)

_CODE_PAGE_INDEX: Optional[Dict[str, List[int]]] = None


def _normalize_hs_code(code: Optional[str]) -> str:
    if not code:
        return ""
    return "".join(ch for ch in str(code) if ch.isdigit())


def _coerce_code_list(raw_codes: Any) -> List[str]:
    if not raw_codes:
        return []
    if isinstance(raw_codes, str):
        return [raw_codes]
    if isinstance(raw_codes, (list, tuple, set)):
        return [str(code) for code in raw_codes if code is not None]
    return [str(raw_codes)]


def _load_code_page_index() -> Dict[str, List[int]]:
    global _CODE_PAGE_INDEX
    if _CODE_PAGE_INDEX is not None:
        return _CODE_PAGE_INDEX

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_path = os.path.join(repo_root, "rag_service", "data", "structured_subheadings_v2_all.json")
    index: Dict[str, List[int]] = {}

    try:
        with open(data_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle) or {}
    except Exception as exc:
        logger.warning("Failed to load subheading index for WCO fallback: %s", exc)
        _CODE_PAGE_INDEX = {}
        return _CODE_PAGE_INDEX

    subheadings = payload.get("subheadings", []) if isinstance(payload, dict) else []
    for entry in subheadings:
        if not isinstance(entry, dict):
            continue
        pages = entry.get("pages") or entry.get("source_pages") or []
        if isinstance(pages, (int, str)):
            pages = [pages]
        codes = _coerce_code_list(entry.get("code"))
        for code in codes:
            normalized = _normalize_hs_code(code)
            if not normalized:
                continue
            index[normalized] = [int(p) for p in pages if isinstance(p, (int, float, str))]

    _CODE_PAGE_INDEX = index
    return _CODE_PAGE_INDEX


def _lookup_pages_for_code(code: Optional[str]) -> List[int]:
    normalized = _normalize_hs_code(code)
    if not normalized:
        return []
    index = _load_code_page_index()
    if normalized in index:
        return index[normalized]
    if len(normalized) >= 6 and normalized[:6] in index:
        return index[normalized[:6]]
    if len(normalized) >= 4 and normalized[:4] in index:
        return index[normalized[:4]]
    if len(normalized) >= 2 and normalized[:2] in index:
        return index[normalized[:2]]
    return []


def _apply_pages_if_missing(block: Optional[Dict[str, Any]], fallback_codes: List[str]) -> bool:
    if not isinstance(block, dict):
        return False
    if block.get("source_pages"):
        return False
    for code in fallback_codes:
        pages = _lookup_pages_for_code(code)
        if pages:
            block["source_pages"] = pages
            return True
    return False

def get_classification(query_data: dict, progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None):
    if not section_summaries:
        logger.warning("Section summaries not loaded; cannot classify.")
        return {"error": "Section summaries not loaded"}

    section_result = None
    chapter_result = None
    heading_result = None
    subheading_result = None

    # Step 1: Pre-classify to find potentially relevant sections
    if progress_callback:
        progress_callback('pre_classification', {'status': 'Starting pre-classification...'})
    
    pre_classification = pre_classify_section(query_data, section_summaries)
    if not pre_classification:
        logger.warning("Pre-classification failed for product '%s'.", query_data.get("product_name", ""))
        return {"error": "Pre-classification failed"}
    
    # Report pre-classification result immediately
    pre_classification_result = pre_classification.model_dump(exclude_none=True)
    if progress_callback:
        progress_callback('pre_classification', {
            'status': 'Pre-classification completed',
            'result': pre_classification_result
        })
    
    # Step 2: Load details only for selected sections
    candidate_sections = [
        item.section_id
        for item in (pre_classification.recommended_sections or [])
        if item.section_id
    ]
    if not candidate_sections:
        logger.warning(
            "Pre-classification returned no recommended sections for product '%s'.",
            query_data.get("product_name", ""),
        )
        return {"error": "Pre-classification returned no recommended sections"}

    section_details = load_section_details(section_kb_folder, candidate_sections)
    
    if not section_details:
        logger.warning(
            "Section details load failed for sections %s (product '%s').",
            candidate_sections,
            query_data.get("product_name", ""),
        )
        return {"error": "Failed to load section details"}
    
    # Step 3: Classify with detailed information
    if progress_callback:
        progress_callback('section_classification', {'status': 'Classifying Section...'})
    
    section_classification = classify_section(query_data, section_details)

    if section_classification:
        section_result = section_classification.model_dump(exclude_none=True)
        
        # Report section classification result immediately
        if progress_callback:
            progress_callback('section_classification', {
                'status': 'Section classification completed',
                'result': section_result
            })
        
        selected_section = section_classification.selected_section
        if selected_section.section_id != "Other":
            # Chapter classification
            if progress_callback:
                progress_callback('chapter_classification', {'status': 'Classifying Chapter...'})
            
            chapter_classification = classify_chapter(
                query_data=query_data,
                section_id=selected_section.section_id,
                knowledge_base_folder=chapter_kb_folder,
                file_name="",
                file_path=""
            )
            if chapter_classification:
                chapter_result = chapter_classification.model_dump(exclude_none=True)
                
                # Report chapter classification result immediately
                if progress_callback:
                    progress_callback('chapter_classification', {
                        'status': 'Chapter classification completed',
                        'result': chapter_result
                    })

                selected_chapter = chapter_classification.selected_chapter
                if selected_chapter.chapter_id:
                    # Heading classification
                    if progress_callback:
                        progress_callback('heading_classification', {'status': 'Classifying Heading...'})
                    
                    heading_classification = classify_heading(
                        query_data=query_data,
                        chapter_id=selected_chapter.chapter_id,
                        knowledge_base_folder=heading_kb_folder.format(
                            chapter_id=selected_chapter.chapter_id,
                            section_id=selected_section.section_id
                        )
                    )
                    if heading_classification:
                        heading_result = heading_classification.model_dump(exclude_none=True)
                        
                        # Report heading classification result immediately
                        if progress_callback:
                            progress_callback('heading_classification', {
                                'status': 'Heading classification completed',
                                'result': heading_result
                            })

                        selected_heading = heading_classification.selected_heading
                        if selected_heading.heading_id:
                            # Subheading classification
                            if progress_callback:
                                progress_callback('subheading_classification', {'status': 'Classifying Subheading...'})
                            
                            subheading_classification = classify_subheading(
                                query_data=query_data,
                                heading_id=selected_heading.heading_id,
                                knowledge_base_file=subheading_kb_file.format(
                                    heading_id=selected_heading.heading_id,
                                    chapter_id=selected_chapter.chapter_id,
                                    section_id=selected_section.section_id
                                )
                            )
                            if subheading_classification:
                                subheading_result = subheading_classification.model_dump(exclude_none=True)
                                
                                # Report subheading classification result immediately
                                if progress_callback:
                                    progress_callback('subheading_classification', {
                                        'status': 'Subheading classification completed',
                                        'result': subheading_result
                                    })
                            else:
                                logger.warning(
                                    "Subheading classification returned empty result for product '%s' (heading=%s).",
                                    query_data.get("product_name", ""),
                                    selected_heading.heading_id,
                                )
                    else:
                        logger.warning(
                            "Heading classification returned empty result for product '%s' (chapter=%s).",
                            query_data.get("product_name", ""),
                            selected_chapter.chapter_id,
                        )
            else:
                logger.warning(
                    "Chapter classification returned empty result for product '%s' (section=%s).",
                    query_data.get("product_name", ""),
                    selected_section.section_id,
                )
    else:
        logger.warning(
            "Section classification returned empty result for product '%s'.",
            query_data.get("product_name", ""),
        )

    fallback_codes = []
    if subheading_result:
        fallback_codes.append(
            (subheading_result.get("selected_subheading") or {}).get("subheading_id")
        )
    if heading_result:
        fallback_codes.append(
            (heading_result.get("selected_heading") or {}).get("heading_id")
        )
    if chapter_result:
        fallback_codes.append(
            (chapter_result.get("selected_chapter") or {}).get("chapter_id")
        )

    fallback_used = False
    if fallback_codes:
        fallback_used |= _apply_pages_if_missing(subheading_result, fallback_codes)
        fallback_used |= _apply_pages_if_missing(heading_result, fallback_codes)
        fallback_used |= _apply_pages_if_missing(chapter_result, fallback_codes)
        fallback_used |= _apply_pages_if_missing(section_result, fallback_codes)

    if fallback_used:
        logger.info(
            "Applied WCO page fallback from subheading index for product '%s'.",
            query_data.get("product_name", ""),
        )

    return {
        "pre_classification": pre_classification_result if pre_classification else None,
        "section_classification": section_result,
        "chapter_classification": chapter_result,
        "heading_classification": heading_result,
        "subheading_classification": subheading_result
    }
