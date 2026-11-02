import asyncio
import json
import os
import re
from typing import Dict, List, Optional
import loguru

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.cohere_rerank import CohereRerank
from rag_service.core.embeddings.gemini_1536 import Gemini1536Embedding

from rag_service.constants.prompt import REWRITE_PROMPT, SYNTHESIS_PROMPT
from rag_service.core.agent_function_tool.semantic_search import semantic_search
from rag_service.core.llm_wrapper import get_llm

try:
    import logfire
    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False


# ---- Config ----
COHERE_RERANK_MODEL = os.getenv(
    "COHERE_RERANK_MODEL", "rerank-multilingual-v3.5")
RERANK_THRESHOLD = 0.2
MAX_RETRIES = 3

# Use multi-provider LLM with fallback support
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.2-chat-latest")
llm = get_llm(provider=LLM_PROVIDER, model=LLM_MODEL, temperature=0)

# Lazy-loaded lookup table for exact HS code -> metadata fallback.
_CODE_PAGE_INDEX: Optional[Dict[str, Dict[str, object]]] = None

# Auto-detect and configure embedding model based on available API keys
def _get_embedding_model():
    """Automatically select embedding model based on available API keys."""
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    # Priority: OpenAI > Gemini
    if openai_key:
        loguru.logger.info("🔧 Using OpenAI embeddings (text-embedding-3-large, dim=1536)")
        return OpenAIEmbedding(
            model="text-embedding-3-large",
            embed_batch_size=10,
            dimensions=1536
        )
    # Fallback to Gemini
    elif gemini_key:
        loguru.logger.info("🔧 Using Gemini embeddings (gemini-embedding-001, forced to dim=1536)")
        return Gemini1536Embedding(api_key=gemini_key)
    else:
        raise ValueError(
            "No embedding API key found! Please set either OPENAI_API_KEY or GEMINI_API_KEY in your .env file. "
            "Embeddings are required for semantic search functionality."
        )

def _auto_detect_collection_suffix():
    """Auto-detect collection suffix based on which embedding provider is active."""
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    # Priority: OpenAI > Gemini (same as _get_embedding_model)
    if openai_key:
        return "_openai"
    elif gemini_key:
        return "_gemini"
    else:
        return "_gemini"  # Default fallback

Settings.embed_model = _get_embedding_model()


# ============================
# STEP 1: Rewrite / Normalize Query
# ============================


def _extract_json_object(raw_text: str) -> Optional[Dict[str, object]]:
    """Extract and parse the first JSON object from LLM output."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    # Fast path: whole string is JSON.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON object via brace matching.
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_hs_code(code: Optional[str]) -> str:
    if not code:
        return ""
    return "".join(ch for ch in str(code) if ch.isdigit())


def _coerce_code_list(raw_codes: object) -> List[str]:
    if not raw_codes:
        return []
    if isinstance(raw_codes, str):
        return [raw_codes]
    if isinstance(raw_codes, (list, tuple, set)):
        return [str(code) for code in raw_codes if code is not None]
    return [str(raw_codes)]


def _extract_metadata_fields(metadata: Dict[str, object]) -> Dict[str, object]:
    if not isinstance(metadata, dict):
        metadata = {}

    pages = metadata.get("pages") or metadata.get("source_pages") or metadata.get("page") or []
    if isinstance(pages, (int, str)):
        pages = [pages]
    chapter = metadata.get("chapter") or metadata.get("chapter_en") or metadata.get("chapter_vi")
    heading = metadata.get("heading") or metadata.get("heading_en") or metadata.get("heading_vi")

    return {
        "source_pages": pages if isinstance(pages, list) else [],
        "chapter": chapter,
        "heading": heading,
        "file_name": metadata.get("file_name") or metadata.get("filename"),
        "file_path": metadata.get("file_path") or metadata.get("filepath"),
        "title": metadata.get("title") or metadata.get("heading_title"),
    }


def _get_code_page_index() -> Dict[str, Dict[str, object]]:
    global _CODE_PAGE_INDEX
    if _CODE_PAGE_INDEX is not None:
        return _CODE_PAGE_INDEX

    index: Dict[str, Dict[str, object]] = {}
    data_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
        "structured_subheadings_v2_all.json",
    )

    try:
        with open(data_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle) or {}
    except Exception as exc:
        loguru.logger.warning(f"Failed to load subheading index: {exc}")
        _CODE_PAGE_INDEX = {}
        return _CODE_PAGE_INDEX

    subheadings = payload.get("subheadings", []) if isinstance(payload, dict) else []
    for entry in subheadings:
        if not isinstance(entry, dict):
            continue
        pages = entry.get("pages") or []
        if isinstance(pages, (int, str)):
            pages = [pages]
        codes = _coerce_code_list(entry.get("code"))
        chapter = entry.get("chapter") or entry.get("chapter_en") or entry.get("chapter_vi")
        heading = entry.get("heading") or entry.get("heading_en") or entry.get("heading_vi")
        for code in codes:
            normalized = _normalize_hs_code(code)
            if not normalized:
                continue
            index[normalized] = {
                "source_pages": pages if isinstance(pages, list) else [],
                "chapter": chapter,
                "heading": heading,
                "file_name": "structured_subheadings_v2_all.json",
                "file_path": data_path,
            }

    _CODE_PAGE_INDEX = index
    return _CODE_PAGE_INDEX


def _lookup_metadata_by_code(subheading_id: Optional[str]) -> Optional[Dict[str, object]]:
    normalized = _normalize_hs_code(subheading_id)
    if not normalized:
        return None
    index = _get_code_page_index()
    return index.get(normalized)


def _select_metadata_for_code(
    semantic_nodes: List[NodeWithScore],
    subheading_id: Optional[str],
    allow_fuzzy_fallback: bool = False,
) -> Dict[str, object]:
    if not semantic_nodes:
        loguru.logger.debug(
            f"No semantic nodes for metadata selection (subheading_id={subheading_id})",
        )
        return _extract_metadata_fields({})

    normalized_target = _normalize_hs_code(subheading_id)
    if not normalized_target:
        for node in semantic_nodes:
            metadata = node.node.metadata or {}
            pages = metadata.get("pages") or metadata.get("source_pages") or metadata.get("page") or []
            if pages:
                loguru.logger.info(
                    "Fallback metadata selected from semantic node without subheading_id",
                )
                return _extract_metadata_fields(metadata)
        return _extract_metadata_fields({})
    loguru.logger.debug(
        f"Selecting metadata for subheading_id={subheading_id} normalized={normalized_target} nodes={len(semantic_nodes)}",
    )
    for node in semantic_nodes:
        metadata = node.node.metadata or {}
        codes = _coerce_code_list(metadata.get("code"))
        normalized_codes = {_normalize_hs_code(code) for code in codes if code is not None}
        if normalized_target and normalized_target in normalized_codes:
            loguru.logger.info(
                f"Exact code match for {normalized_target} -> codes={sorted(code for code in normalized_codes if code)} pages={metadata.get('pages') or metadata.get('source_pages') or []}",
            )
            return _extract_metadata_fields(metadata)

    target_heading = normalized_target[:4] if normalized_target else ""
    best_heading_match: Optional[NodeWithScore] = None
    best_score = float("-inf")

    for node in semantic_nodes:
        metadata = node.node.metadata or {}
        codes = _coerce_code_list(metadata.get("code"))
        normalized_codes = [_normalize_hs_code(code) for code in codes if code is not None]
        if not target_heading:
            continue
        if any(code.startswith(target_heading) for code in normalized_codes if code):
            score = getattr(node, "score", None)
            if score is None:
                score = getattr(node.node, "score", 0)
            if score is None:
                score = 0
            if score > best_score:
                best_score = score
                best_heading_match = node

    if best_heading_match:
        match_metadata = best_heading_match.node.metadata or {}
        match_codes = _coerce_code_list(match_metadata.get("code"))
        normalized_match_codes = [_normalize_hs_code(code) for code in match_codes if code is not None]
        loguru.logger.info(
            f"Heading match for {target_heading} -> codes={[code for code in normalized_match_codes if code]} pages={match_metadata.get('pages') or match_metadata.get('source_pages') or []} score={getattr(best_heading_match, 'score', None)}",
        )
        return _extract_metadata_fields(best_heading_match.node.metadata or {})

    unique_codes = []
    for node in semantic_nodes:
        metadata = node.node.metadata or {}
        codes = _coerce_code_list(metadata.get("code"))
        for code in codes:
            normalized = _normalize_hs_code(code)
            if normalized and normalized not in unique_codes:
                unique_codes.append(normalized)
    if unique_codes:
        loguru.logger.info(
            f"No metadata match for subheading_id={subheading_id} normalized={normalized_target}. Available codes={unique_codes}",
        )

    best_pages_match: Optional[NodeWithScore] = None
    best_pages_score = float("-inf")
    for node in semantic_nodes:
        metadata = node.node.metadata or {}
        pages = metadata.get("pages") or metadata.get("source_pages") or metadata.get("page") or []
        if not pages:
            continue
        score = getattr(node, "score", None)
        if score is None:
            score = getattr(node.node, "score", 0)
        if score is None:
            score = 0
        if score > best_pages_score:
            best_pages_score = score
            best_pages_match = node

    if allow_fuzzy_fallback and best_pages_match:
        match_metadata = best_pages_match.node.metadata or {}
        match_codes = _coerce_code_list(match_metadata.get("code"))
        normalized_match_codes = [_normalize_hs_code(code) for code in match_codes if code is not None]
        loguru.logger.info(
            "Fallback metadata selected from top-scoring node with pages",
            subheading_id=subheading_id,
            candidate_codes=[code for code in normalized_match_codes if code],
            source_pages=match_metadata.get("pages") or match_metadata.get("source_pages") or [],
            score=getattr(best_pages_match, "score", None),
        )
        return _extract_metadata_fields(match_metadata)

    loguru.logger.info(
        f"No metadata match for subheading_id={subheading_id} normalized={normalized_target}",
    )
    return _extract_metadata_fields({})


def _build_synthesis_results(
    parsed: Dict[str, object],
    semantic_nodes: Optional[List[NodeWithScore]] = None,
    fallback_nodes: Optional[List[NodeWithScore]] = None
) -> List[Dict[str, object]]:
    """Map new synthesis JSON to legacy result schema."""
    selected = parsed.get("selected_subheading", {}) if isinstance(parsed, dict) else {}
    subheading_id = None
    rationale = ""

    if isinstance(selected, dict):
        subheading_id = selected.get("subheading_id")
        rationale = (selected.get("rationale") or "").strip()

    precedent_evaluation = parsed.get("precedent_evaluation", []) if isinstance(parsed, dict) else []
    precedent_reference = ""
    difference_analysis = ""
    match_status = ""

    if isinstance(precedent_evaluation, list) and precedent_evaluation:
        first_eval = precedent_evaluation[0]
        if isinstance(first_eval, dict):
            precedent_reference = (first_eval.get("precedent_reference") or "").strip()
            difference_analysis = (first_eval.get("difference_analysis") or "").strip()
            match_status = (first_eval.get("match_status") or "").strip()

    reason_parts = [p for p in [rationale, difference_analysis, match_status] if p]
    reason = " | ".join(reason_parts) if reason_parts else ""
    content_of_citation = precedent_reference

    metadata = _select_metadata_for_code(semantic_nodes or [], subheading_id)
    if fallback_nodes:
        pages = metadata.get("source_pages") or []
        if not pages:
            metadata = _select_metadata_for_code(fallback_nodes, subheading_id)

    pages = metadata.get("source_pages") or []
    if not pages:
        fallback_metadata = _lookup_metadata_by_code(subheading_id)
        if fallback_metadata:
            metadata = {**fallback_metadata, **metadata}
            loguru.logger.info(
                "Used dataset fallback for source pages",
                subheading_id=subheading_id,
                source_pages=metadata.get("source_pages") or [],
            )

    pages = metadata.get("source_pages") or []
    if not pages:
        fuzzy_nodes = fallback_nodes if fallback_nodes else (semantic_nodes or [])
        fuzzy_metadata = _select_metadata_for_code(
            fuzzy_nodes,
            subheading_id,
            allow_fuzzy_fallback=True,
        )
        if fuzzy_metadata.get("source_pages"):
            metadata = {**metadata, **fuzzy_metadata}
            loguru.logger.info(
                "Used fuzzy semantic fallback for source pages",
                subheading_id=subheading_id,
                source_pages=metadata.get("source_pages") or [],
            )

    # debug log -> show selected source pages for tabs
    loguru.logger.info(
        f"Source pages selected (subheading_id={subheading_id}) -> "
        f"pages={metadata.get('source_pages') or []} "
        f"file_name={metadata.get('file_name')} "
        f"file_path={metadata.get('file_path')}",
    )

    return [
        {
            "subheading_ids": [subheading_id] if subheading_id else [],
            "reason": reason,
            "content_of_citation": content_of_citation,
            "metadata": metadata,
        }
    ]


async def rewrite_query(product_name: str, science_name: str, product_description: str) -> str:
    """
    Rewrite product name to normalized English search terms.
    """
    if LOGFIRE_AVAILABLE:
        with logfire.span("rewrite_query", product_name=product_name):
            input_msg = ChatMessage(
                role="user",
                content=REWRITE_PROMPT.format(
                    product_name=product_name,
                    science_name=science_name,
                    product_description=product_description,
                ),
            )
            output = await llm.achat([input_msg])
            result = output.message.content.strip()
            parsed = _extract_json_object(result)
            if parsed and isinstance(parsed, dict):
                candidate = str(parsed.get("semantic_search_query") or "").strip()
                if candidate:
                    result = candidate
            logfire.info("Query rewritten", original=product_name, rewritten=result)
            return result
    else:
        input_msg = ChatMessage(
            role="user",
            content=REWRITE_PROMPT.format(
                product_name=product_name,
                science_name=science_name,
                product_description=product_description,
            ),
        )
        output = await llm.achat([input_msg])
        result = output.message.content.strip()
        parsed = _extract_json_object(result)
        if parsed and isinstance(parsed, dict):
            candidate = str(parsed.get("semantic_search_query") or "").strip()
            if candidate:
                result = candidate
        return result


# ============================
# STEP 2: Format Semantic Results
# ============================
def _format_semantic_block(nodes: List[NodeWithScore]) -> str:
    """
    Format semantic search results into readable text with chapter & heading info.
    Only extract essential metadata to minimize token usage.
    """
    blocks = []
    for n in nodes:
        txt = n.node.get_text() if isinstance(n.node, TextNode) else str(n.node)
        metadata = n.node.metadata or {}
        
        # Extract ONLY essential fields to reduce token usage
        essential_metadata = {
            "code": metadata.get("code", []),
            "pages": metadata.get("pages", []),
            "chapter_vi": metadata.get("chapter_vi", ""),
            "chapter_en": metadata.get("chapter_en", "")
        }
        
        blocks.append({
            "content": txt.replace("Phanh phanh", " ").replace(". ", "."),
            "metadata": essential_metadata
        })
        
    return blocks


# ============================
# STEP 3: Full Retrieval Pipeline
# ============================
async def hscode_search(
    product_name: str,
    science_name: str,
    product_description: str,
    function: str,
    material: str,
    structure: str,
    specifications: str,
    other_information: str,
    image_paths: List[str],
    collection_name: str = None,
) -> Dict[str, str]:
    """
    Full hybrid RAG search + reasoning pipeline to determine HS Code.
    """
    if LOGFIRE_AVAILABLE:
        with logfire.span(
            "hscode_search",
            product_name=product_name,
            science_name=science_name or "",
            product_description=(product_description or "")[:200],  # Truncate long text
            function=function or "",
            material=material or "",
            structure=structure or "",
            specifications=specifications or "",
            other_information=(other_information or "")[:200],  # Truncate long text
            has_images=len(image_paths) > 0,
            num_images=len(image_paths)
        ):
            return await _hscode_search_impl(
                product_name, science_name, product_description,
                function, material, structure, specifications,
                other_information, image_paths, collection_name
            )
    else:
        return await _hscode_search_impl(
            product_name, science_name, product_description,
            function, material, structure, specifications,
            other_information, image_paths, collection_name
        )


async def _hscode_search_impl(
    product_name: str,
    science_name: str,
    product_description: str,
    function: str,
    material: str,
    structure: str,
    specifications: str,
    other_information: str,
    image_paths: List[str],
    collection_name: str = None,
) -> Dict[str, str]:
    """
    Internal implementation of hscode_search.
    """
    # Auto-detect collection suffix if collection_name contains base name
    if collection_name:
        base_collections = ["asean", "compendium"]
        for base in base_collections:
            if collection_name == base or collection_name.startswith(f"{base}_"):
                # If just base name (e.g., "asean") or has suffix (e.g., "asean_gemini")
                if collection_name == base:
                    # Auto-append suffix based on active embedding provider
                    suffix = _auto_detect_collection_suffix()
                    collection_name = f"{base}{suffix}"
                    loguru.logger.info(f"🔄 Auto-detected collection: {collection_name}")
                break
    
    # Log all input parameters for debugging
    loguru.logger.info("=" * 80)
    loguru.logger.info("📥 INPUT PARAMETERS:")
    loguru.logger.info(f"  Product Name: {product_name}")
    loguru.logger.info(f"  Science Name: {science_name or '(empty)'}")
    loguru.logger.info(f"  Description: {(product_description or '(empty)')[:100]}...")
    loguru.logger.info(f"  Function: {function or '(empty)'}")
    loguru.logger.info(f"  Material: {material or '(empty)'}")
    loguru.logger.info(f"  Structure: {structure or '(empty)'}")
    loguru.logger.info(f"  Specifications: {specifications or '(empty)'}")
    loguru.logger.info(f"  Other Info: {(other_information or '(empty)')[:100]}...")
    loguru.logger.info(f"  Images: {len(image_paths)} file(s)")
    loguru.logger.info("=" * 80)
    
    # ---- Step 1: Rewrite ----
    rewritten_query = await rewrite_query(product_name, science_name, product_description)
    # print(f"🔄 Rewritten query: {rewritten_query}")
    loguru.logger.info(f"🔄 Rewritten query: {rewritten_query}")
    query = rewritten_query.lower()

    # ---- Step 2: Parallel Search ----
    if LOGFIRE_AVAILABLE:
        with logfire.span("parallel_search", query=query):
            semantic_task = semantic_search(query, collection_name)
            semantic_nodes = await semantic_task
            keyword_data, fulltext_data, graph_result = [], [], None
            code = []
            for i in semantic_nodes:
                metadata = i.node.metadata or {}
                code.append({
                    "code": metadata.get("code", []),
                    "score": metadata.get("score", 0)
                })
            logfire.info(f"Retrieved {len(semantic_nodes)} semantic nodes", semantic_nodes=code)
    else:
        semantic_task = semantic_search(query, collection_name)
        semantic_nodes = await semantic_task

    # ---- Step 3: Rerank Semantic Results ----
    if LOGFIRE_AVAILABLE:
        with logfire.span("rerank_results"):
            cohere_rerank = CohereRerank(model=COHERE_RERANK_MODEL, top_n=10)
            semantic_nodes = cohere_rerank.postprocess_nodes(semantic_nodes, query_str=query)
            
            filtered_semantic_nodes = [
                n for n in semantic_nodes if getattr(n, "score", 0) >= RERANK_THRESHOLD
            ]
            preview = []
            for node in filtered_semantic_nodes[:3]:
                metadata = node.node.metadata or {}
                preview.append({
                    "code": metadata.get("code", []),
                    "pages": metadata.get("pages", []),
                    "file_name": metadata.get("file_name") or metadata.get("filename"),
                })
            loguru.logger.info(f"Filtered semantic node metadata preview: {preview}")
            logfire.info(f"Filtered to {len(filtered_semantic_nodes)} nodes above threshold {RERANK_THRESHOLD}")
            blocks = []
            for n in semantic_nodes:
                metadata = n.node.metadata or {}
                blocks.append({
                    "code": metadata.get("code", []),
                    "score": metadata.get("score", 0)
                })
            logfire.info("semantic_nodes", semantic_nodes=blocks)
            semantic_block = _format_semantic_block(filtered_semantic_nodes)
    else:
        cohere_rerank = CohereRerank(model=COHERE_RERANK_MODEL, top_n=5)
        semantic_nodes = cohere_rerank.postprocess_nodes(semantic_nodes, query_str=query)
        
        filtered_semantic_nodes = [
            n for n in semantic_nodes if getattr(n, "score", 0) >= RERANK_THRESHOLD
        ]
        preview = []
        for node in filtered_semantic_nodes[:3]:
            metadata = node.node.metadata or {}
            preview.append({
                "code": metadata.get("code", []),
                "pages": metadata.get("pages", []),
                "file_name": metadata.get("file_name") or metadata.get("filename"),
            })
        loguru.logger.info(f"Filtered semantic node metadata preview: {preview}")
        semantic_block = _format_semantic_block(filtered_semantic_nodes)

    # ---- Step 4: Format Semantic Results ----
    final_output = f"📘 Semantic Results:\n{semantic_block}\n\n"
    visual_description = ""
    
    # Log context size for debugging
    context_chars = len(str(final_output))
    loguru.logger.info(f"📊 Context size: {context_chars:,} characters (~{context_chars//4:,} tokens)")
    
    # ---- Step 5: LLM Synthesis ----
    synthesis_prompt = SYNTHESIS_PROMPT.format(
        product_name=product_name,
        science_name=science_name,
        product_description=product_description,
        function=function,
        material=material,
        structure=structure,
        specifications=specifications,
        other_information=other_information,
        visual_description=visual_description,
        final_output=final_output,
    )
    
    prompt_chars = len(synthesis_prompt)
    loguru.logger.info(f"📊 Total prompt size: {prompt_chars:,} characters (~{prompt_chars//4:,} tokens)")

    input_msg = ChatMessage(role="user", content=synthesis_prompt)
    sllm = llm
    
    if LOGFIRE_AVAILABLE:
        with logfire.span(
            "llm_synthesis",
            prompt_chars=prompt_chars,
            estimated_tokens=prompt_chars//4
        ):
            for attempt in range(MAX_RETRIES):
                try:
                    loguru.logger.info(f"🤖 Calling structured LLM (attempt {attempt + 1}/{MAX_RETRIES})...")
                    output = await sllm.achat([input_msg])
                    loguru.logger.info(f"✅ LLM response received successfully")
                    raw_text = output.message.content.strip()
                    parsed = _extract_json_object(raw_text) or {}
                    results = _build_synthesis_results(
                        parsed,
                        filtered_semantic_nodes,
                        semantic_nodes
                    )
                    
                    # Log the HS codes returned by LLM
                    loguru.logger.info("=" * 80)
                    loguru.logger.info(f"📤 LLM OUTPUT: {len(results)} result(s)")
                    for i, result in enumerate(results, 1):
                        codes = result.get("subheading_ids", [])
                        reason = result.get("reason", "")[:100]
                        loguru.logger.info(f"  Result {i}: {codes}")
                        loguru.logger.info(f"    Reason: {reason}...")
                    loguru.logger.info("=" * 80)
                    
                    logfire.info(
                        "Synthesis completed",
                        num_results=len(results),
                        first_codes=results[0].get("subheading_ids", []) if results else []
                    )
                    return results
                except Exception as e:
                    loguru.logger.error(f"⚠️ Retry {attempt + 1}/{MAX_RETRIES} failed: {e}")
                    logfire.error(f"LLM synthesis attempt {attempt + 1} failed", error=str(e))
                    if attempt == MAX_RETRIES - 1:
                        loguru.logger.error(f"❌ All retries exhausted. Returning empty result.")
                        return []
    else:
        for attempt in range(MAX_RETRIES):
            try:
                loguru.logger.info(f"🤖 Calling structured LLM (attempt {attempt + 1}/{MAX_RETRIES})...")
                output = await sllm.achat([input_msg])
                loguru.logger.info(f"✅ LLM response received successfully")
                raw_text = output.message.content.strip()
                parsed = _extract_json_object(raw_text) or {}
                results = _build_synthesis_results(
                    parsed,
                    filtered_semantic_nodes,
                    semantic_nodes
                )
                
                # Log the HS codes returned by LLM
                loguru.logger.info("=" * 80)
                loguru.logger.info(f"📤 LLM OUTPUT: {len(results)} result(s)")
                for i, result in enumerate(results, 1):
                    codes = result.get("subheading_ids", [])
                    reason = result.get("reason", "")[:100]
                    loguru.logger.info(f"  Result {i}: {codes}")
                    loguru.logger.info(f"    Reason: {reason}...")
                loguru.logger.info("=" * 80)
                
                return results
            except Exception as e:
                loguru.logger.error(f"⚠️ Retry {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    loguru.logger.error(f"❌ All retries exhausted. Returning empty result.")
                    return []
