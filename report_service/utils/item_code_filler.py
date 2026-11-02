"""Item Code (Mã NPL/SP) Pre-filler — Rule-based + LLM filling for missing item codes.

Extracted from gen_item_code.py for use in the report API pipeline.

Modes:
  rule_based — Fast pattern matching only (Phase A)
    R1 — Exact Tên hàng match
    R2 — Normalized Tên hàng match
    R3 — Description after #& (single-SKU only)
    R4 — P/N (Part Number) lookup
    R5 — Noise-stripped Tên hàng match (removes Vietnamese noise words)

  llm — Rule-based first, then LLM for remaining (Phase A → B → C → D)
    Phase A — Rule-based filling (same as above)
    Phase B — Deduplicate remaining empty rows by unique Tên hàng
    Phase C — Batch LLM calls only for unique unfilled items
    Phase D — Propagate LLM results back to all duplicate rows
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from report_service.core.models import ExcelRowData

logger = logging.getLogger(__name__)

# ── Configuration via environment variables ───────────────────────────────
PREFILL_LLM_MODEL = os.getenv("PREFILL_LLM_MODEL", "gpt-4o-mini")
PREFILL_BATCH_SIZE = int(os.getenv("PREFILL_BATCH_SIZE", "30"))
PREFILL_MAX_CONCURRENT = int(os.getenv("PREFILL_MAX_CONCURRENT", "10"))
PREFILL_LLM_TEMPERATURE = float(os.getenv("PREFILL_LLM_TEMPERATURE", "0.0"))
PREFILL_BATCH_TIMEOUT = int(os.getenv("PREFILL_BATCH_TIMEOUT", "120"))

# ── Noise patterns (Vietnamese noise words) ──────────────────────────────

# Suffixes / trailing noise
_NOISE_SUFFIX_RE = re.compile(
    r"(?:"
    r"[.\s]*hàng\s*mới\s*100%"      # Hàng mới 100%
    r"|[.\s]*mới\s*100%"             # Mới 100%
    r"|[.\s]*hàng\s*mới"             # Hàng mới
    r"|\.?\s*$"
    r")",
    re.IGNORECASE,
)

# Leading / inline noise
_NOISE_PREFIX_RE = re.compile(
    r"(?:"
    r"mặt\s*hàng\s*:?\s*"           # "Mặt hàng:"
    r"|hàng\s*hoá\s*:?\s*"          # "Hàng hoá:"
    r"|nk\s+phục\s+vụ\s+sx\b\s*"   # "NK phục vụ SX"
    r"|nhập\s+khẩu\s+phục\s+vụ\s+sản\s+xuất\b\s*"
    r"|dùng\s+(?:cho|để|trong)\s+"  # "dùng cho / dùng để / dùng trong"
    r"|phục\s+vụ\s+(?:sản\s+xuất|sx)\s*"
    r")",
    re.IGNORECASE,
)

# Standalone counter/unit words to strip
_NOISE_UNIT_RE = re.compile(
    r"\b(?:cái|chiếc|bộ|cuộn|tấm|miếng|cặp|đôi|hộp|gói|thùng|kg|pcs|set|ea)\b[.,]?\s*",
    re.IGNORECASE,
)

# Parenthesised trailing junk like "(Hàng mới 100%)"
_NOISE_PAREN_RE = re.compile(
    r"\(\s*(?:hàng\s*)?mới\s*100%\s*\)",
    re.IGNORECASE,
)

# Part Number regex
_PN_RE = re.compile(
    r"(?:P/N|Model|MODEL|Ref|REF)[:\s]*\s*([A-Za-z0-9\-.\/_#]+)", re.IGNORECASE
)


def _strip_noise(s: str) -> str:
    """Remove Vietnamese noise from product description for better matching."""
    s = _NOISE_PAREN_RE.sub("", s)
    s = _NOISE_SUFFIX_RE.sub("", s)
    s = _NOISE_PREFIX_RE.sub("", s)
    s = _NOISE_UNIT_RE.sub(" ", s)
    s = re.sub(r"[,.\s]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize(s: str) -> str:
    """Lowercase, strip all noise, collapse whitespace."""
    s = _strip_noise(str(s).strip())
    return s.lower().strip()


def _build_rule_maps(
    rows_with_sku: List[ExcelRowData],
) -> Tuple[
    Dict[str, str],          # exact_map
    Dict[str, str],          # norm_map
    Dict[str, Set[str]],     # desc_map
    Dict[str, str],          # pn_map
    Dict[str, str],          # noise_stripped_map
]:
    """Build lookup maps from rows that already have Mã NPL/SP."""
    exact_map: Dict[str, str] = {}
    norm_map: Dict[str, str] = {}
    desc_map: Dict[str, Set[str]] = {}
    pn_map: Dict[str, str] = {}
    noise_stripped_map: Dict[str, str] = {}

    for row in rows_with_sku:
        th = (row.ten_hang or "").strip()
        sku = (row.ma_npl_sp or "").strip()
        if not sku or not th:
            continue

        exact_map.setdefault(th, sku)

        th_norm = _normalize(th)
        if th_norm:
            norm_map.setdefault(th_norm, sku)

        if "#&" in th:
            desc = th.split("#&", 1)[1].strip()
            desc_norm = _normalize(desc)
            if desc_norm:
                desc_map.setdefault(desc_norm, set()).add(sku)
            # Also store noise-stripped desc for R5
            if desc_norm and len(desc_norm) >= 10:
                noise_stripped_map.setdefault(desc_norm, sku)

        m = _PN_RE.search(th)
        if m:
            pn = m.group(1).strip().rstrip(".")
            pn_map.setdefault(pn, sku)

        # R5: full noise-stripped Tên hàng
        if th_norm and len(th_norm) >= 10:
            noise_stripped_map.setdefault(th_norm, sku)

    return exact_map, norm_map, desc_map, pn_map, noise_stripped_map


def _apply_rules(
    row: ExcelRowData,
    exact_map: Dict[str, str],
    norm_map: Dict[str, str],
    desc_map: Dict[str, Set[str]],
    pn_map: Dict[str, str],
    noise_stripped_map: Dict[str, str],
) -> Optional[Tuple[str, str]]:
    """Try to fill a single row's item code using rules.

    Returns (item_code, source) or None if no match found.
    """
    th = (row.ten_hang or "").strip()
    if not th:
        return None

    th_norm = _normalize(th)

    # R1 — exact Tên hàng
    if th in exact_map:
        return exact_map[th], "Exact Tên hàng match"

    # R2 — normalised Tên hàng
    if th_norm in norm_map:
        return norm_map[th_norm], "Normalized Tên hàng match"

    # R3 — description after #& (single-SKU only)
    if th_norm in desc_map and len(desc_map[th_norm]) == 1:
        return next(iter(desc_map[th_norm])), "Matched description after #&"

    # R4 — P/N lookup
    m = _PN_RE.search(th)
    if m:
        pn = m.group(1).strip().rstrip(".")
        if pn in pn_map:
            return pn_map[pn], "P/N matched existing SKU"

    # R5 — noise-stripped matching
    if th_norm and len(th_norm) >= 10 and th_norm in noise_stripped_map:
        return noise_stripped_map[th_norm], "Noise-stripped Tên hàng match"

    # R5b — strip noise from desc after #& and match
    if "#&" in th:
        desc_norm = _normalize(th.split("#&", 1)[1].strip())
        if desc_norm and len(desc_norm) >= 10 and desc_norm in noise_stripped_map:
            return noise_stripped_map[desc_norm], "Noise-stripped desc match"

    return None


def prefill_item_codes(rows: List[ExcelRowData]) -> Tuple[List[ExcelRowData], int]:
    """Pre-fill missing Mã NPL/SP using rule-based matching (Phase A only).

    Args:
        rows: List of ExcelRowData parsed from the input Excel file.

    Returns:
        Tuple of (modified rows list, number of rows filled).
        The rows list is modified in-place and also returned for convenience.
    """
    # Split into rows with and without SKU
    rows_with_sku = [r for r in rows if r.ma_npl_sp and r.ma_npl_sp.strip()]
    rows_without_sku = [r for r in rows if not r.ma_npl_sp or not r.ma_npl_sp.strip()]

    # Mark rows that already have SKU as "Original"
    for row in rows_with_sku:
        if not row.source:
            row.source = row.ma_npl_sp
            row.item = "Original"

    if not rows_without_sku:
        logger.info("prefill_item_codes: All rows already have Mã NPL/SP, nothing to fill.")
        return rows, 0

    if not rows_with_sku:
        logger.info("prefill_item_codes: No rows with existing Mã NPL/SP to learn from.")
        return rows, 0

    logger.info(
        f"prefill_item_codes: {len(rows_with_sku)} rows with SKU, "
        f"{len(rows_without_sku)} rows without SKU"
    )

    # Build rule maps
    exact_map, norm_map, desc_map, pn_map, noise_stripped_map = _build_rule_maps(rows_with_sku)

    # Apply rules to rows missing SKU
    filled_count = 0
    rule_counts: Dict[str, int] = {}

    for row in rows_without_sku:
        result = _apply_rules(row, exact_map, norm_map, desc_map, pn_map, noise_stripped_map)
        if result:
            item_code, source = result
            row.ma_npl_sp = item_code
            # Save suggested code and rationale for the 2 new columns in output
            row.source = item_code  # "Mã NPL/SP (Suggested)" column
            row.item = source       # "Rationale" column
            filled_count += 1
            rule_counts[source] = rule_counts.get(source, 0) + 1

    # Log summary
    for rule, count in sorted(rule_counts.items()):
        logger.info(f"  prefill_item_codes: {rule}: {count}")
    logger.info(f"  prefill_item_codes: Total filled: {filled_count}/{len(rows_without_sku)}")

    return rows, filled_count


# ════════════════════════════════════════════════════════════════════════════
# LLM-BASED FILLING (Phase B → C → D)
# ════════════════════════════════════════════════════════════════════════════

# ── Pydantic output models for LLM ───────────────────────────────────────

class SKUItem(BaseModel):
    """One generated SKU entry from LLM."""
    row_id: str = Field(..., description="The row_id provided in the input table")
    item_code: str = Field(
        ...,
        description="Generated Item Code (uppercase, max 20 chars, A-Z 0-9 _ only)",
    )


class SKUBatchResult(BaseModel):
    """Batch response from LLM."""
    items: List[SKUItem] = Field(..., description="List of generated SKU items")


# ── System prompt ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT_BASE = """\
**ROLE & CONTEXT**
You are a **Senior Customs Compliance Data Analyst**. You are processing raw data from the VNACCS system where many trading/non-commercial items lack an "Item Code" (SKU).
Your goal is to **generate consistent, meaningful, and standardized Item Codes** for these missing entries to facilitate a compliance audit.

**INPUT DATA**
I will provide a dataset with 3 columns:
1. **No.** (ID)
2. **Mã NPL/SP** (Client's declared code - often Empty/Null)
3. **Tên Hàng** (Raw mixed text: Vietnamese/English, specs, dimensions, brands)

**PROCESSING ALGORITHM (CHAIN OF THOUGHT)**
You must process the data through the following logic pipeline:

**PHASE 1: PATTERN LEARNING (The "Dictionary" Phase)**
* Scan all rows where `[Mã NPL/SP]` is **NOT** empty.
* Deduce the client's naming convention (e.g., Do they use "NOUN_SPEC"? Do they use "MODEL_NUMBER"?).
* *Memory Constraint:* Remember these existing pairings as the "Truth Dictionary".

**PHASE 2: INTELLIGENT FILLING (The "Semantic" Phase)**
* For rows where `[Mã NPL/SP]` is **EMPTY**:
* Compare the `[Tên Hàng]` against the "Truth Dictionary".
* **Crucial:** Use **Semantic Matching**, not just text matching. *Example:* If "Ốc vít thép" has code `SCREW_STL`, then "Vít bằng thép" should also get `SCREW_STL`.
* If a high-confidence match is found, assign the existing code.

**PHASE 3: GENERATION & STANDARDIZATION (The "Creation" Phase)**
* For rows that remain **EMPTY** (No match found):
1. **Clean & Translate:** Remove Vietnamese "noise" words (e.g., "Mặt hàng:", "Mới 100%", "NK phục vụ SX", "Cái", "Bộ", "Kg"). Translate the core product name to **English**.
2. **Extract Identifiers (Priority Order):**
\t* **Priority A (Model/Part No):** Look for alphanumeric strings following keywords like "Model:", "P/N:", "Ref:", "No.". -> *Output Format: [MODEL_NUMBER]*
\t* **Priority B (Specific Noun + Spec):** If no model, combine the English Noun + Key Specification (Material/Size/Capacity). -> *Output Format: [NOUN]_[SPEC]*
3. **Anti-Generalization Rule:** NEVER generate generic codes like "TOOL", "SPARE_PART", or "MACHINE".
\t* *Bad:* `PLIERS`
\t* *Good:* `PLIERS_CUTTING_6INCH`
4. **Formatting:**
\t* Uppercase ONLY.
\t* Replace spaces/symbols with Underscore `_`.
\t* Max Length: 20 Characters.
\t* Remove special characters (keep only A-Z, 0-9, and `_`).

**PHASE 4: CONSISTENCY AUDIT**
* **Group Check:** Ensure items with the same Nature + Model get the exact same code.
* **Conflict Check:** Ensure your generated code doesn't accidentally duplicate an existing code for a different product.

**OUTPUT FORMAT**
Return the structured JSON for every item in the batch.
Each item must have: row_id, item_code.
The row_id in your output MUST exactly match the row_id provided in the input.\
"""

_STRUCTURED_OUTPUT_ADDENDUM = """
═══ TRUTH DICTIONARY (existing code ↔ product pairs — use as reference) ═══
{truth_dict}
═══ END DICTIONARY ═══

**ADDITIONAL INSTRUCTIONS FOR THIS BATCH RUN**
- I am providing items in a table with columns: row_id, Mã HS, Tên Hàng.
- Return the structured JSON for every item in the batch.
- The row_id in your output MUST exactly match the row_id provided in the input.
- Only return row_id and item_code for each item.
"""


def _build_truth_dictionary(rows_with_sku: List[ExcelRowData], limit: int = 500) -> str:
    """Build truth dictionary string from rows that have SKU."""
    seen: Set[Tuple[str, str]] = set()
    lines: List[str] = []

    for row in rows_with_sku:
        code = (row.ma_npl_sp or "").strip()
        name = (row.ten_hang or "").strip()[:200]
        if not code or not name:
            continue
        key = (code, name)
        if key not in seen:
            seen.add(key)
            lines.append(f"- {code}  →  {name}")
            if len(lines) >= limit:
                break

    return "\n".join(lines)


def _build_system_prompt(truth_dict: str) -> str:
    """Build the full system prompt with truth dictionary."""
    addendum = _STRUCTURED_OUTPUT_ADDENDUM.format(truth_dict=truth_dict)
    return _SYSTEM_PROMPT_BASE + "\n\n" + addendum


def _create_sku_agent(truth_dict: str):
    """Create pydantic-ai Agent for SKU generation."""
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings

    model_str = f"openai:{PREFILL_LLM_MODEL}"
    system = _build_system_prompt(truth_dict)

    return Agent(
        model_str,
        output_type=SKUBatchResult,
        system_prompt=system,
        model_settings=ModelSettings(temperature=PREFILL_LLM_TEMPERATURE),
        name="SKU-Generator",
    )


# ── Phase B: Dedup ────────────────────────────────────────────────────────

def _dedup_for_llm(
    rows_without_sku: List[ExcelRowData],
) -> Tuple[List[dict], Dict[str, List[int]]]:
    """Deduplicate rows by Tên hàng for LLM processing.

    Returns:
        Tuple of (unique_items as list of dicts for LLM, mapping of ten_hang → list of row indices)
    """
    th_to_indices: Dict[str, List[int]] = {}
    for i, row in enumerate(rows_without_sku):
        th = (row.ten_hang or "").strip()
        if th:
            th_to_indices.setdefault(th, []).append(i)

    unique_items: List[dict] = []
    for th, indices in th_to_indices.items():
        first_row = rows_without_sku[indices[0]]
        unique_items.append({
            "row_id": str(indices[0]),
            "ma_hs": first_row.ma_hs or "",
            "ten_hang": th,
        })

    return unique_items, th_to_indices


# ── Phase C: Batch LLM ───────────────────────────────────────────────────

def _format_batch_prompt(batch: List[dict]) -> str:
    """Format a batch of items into a prompt table for the LLM."""
    lines = ["Generate Item Codes for the following items:\n"]
    lines.append("| row_id | Mã HS | Tên Hàng |")
    lines.append("|--------|-------|----------|")
    for item in batch:
        rid = item["row_id"]
        hs = item["ma_hs"]
        th = item["ten_hang"][:300]
        lines.append(f"| {rid} | {hs} | {th} |")
    lines.append(
        "\nReturn JSON with `items` array. "
        "Each item: {row_id, item_code}. "
        "row_id MUST match the row_id above exactly."
    )
    return "\n".join(lines)


async def _process_batch(
    agent,
    batch: List[dict],
    batch_idx: int,
    total_batches: int,
) -> List[SKUItem]:
    """Process a single batch through LLM."""
    prompt = _format_batch_prompt(batch)
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            agent.run(prompt),
            timeout=PREFILL_BATCH_TIMEOUT,
        )
        elapsed = time.perf_counter() - t0
        logger.info(
            f"  LLM batch {batch_idx}/{total_batches} → "
            f"{len(result.output.items)} items ({elapsed:.1f}s)"
        )
        return result.output.items
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        logger.warning(
            f"  LLM batch {batch_idx}/{total_batches} TIMEOUT ({elapsed:.0f}s)"
        )
        return []
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            f"  LLM batch {batch_idx}/{total_batches} failed ({elapsed:.1f}s): {exc}"
        )
        return []


# ── Main LLM pipeline ────────────────────────────────────────────────────

async def prefill_item_codes_llm(
    rows: List[ExcelRowData],
) -> Tuple[List[ExcelRowData], int, int]:
    """Pre-fill missing Mã NPL/SP using rule-based matching + LLM generation.

    Pipeline:
      Phase A — Rule-based filling (fast, free)
      Phase B — Deduplicate remaining empty rows
      Phase C — Batch LLM calls for unique unfilled items
      Phase D — Propagate LLM results back to all duplicate rows

    Args:
        rows: List of ExcelRowData parsed from the input Excel file.

    Returns:
        Tuple of (modified rows, rule_filled_count, llm_filled_count).
        The rows list is modified in-place and also returned for convenience.
    """
    # ── Phase A: Rule-based filling ──────────────────────────────────────
    rows, rule_filled = prefill_item_codes(rows)

    # Re-split after rule-based filling
    rows_with_sku = [r for r in rows if r.ma_npl_sp and r.ma_npl_sp.strip()]
    rows_without_sku_indexed = [
        (i, r) for i, r in enumerate(rows)
        if not r.ma_npl_sp or not r.ma_npl_sp.strip()
    ]

    if not rows_without_sku_indexed:
        logger.info("prefill_llm: All rows filled after rule-based phase.")
        return rows, rule_filled, 0

    rows_without_sku = [r for _, r in rows_without_sku_indexed]

    logger.info(
        f"prefill_llm: {len(rows_without_sku)} rows still without SKU after rules, "
        f"starting LLM phase (model={PREFILL_LLM_MODEL})..."
    )

    # ── Phase B: Dedup ───────────────────────────────────────────────────
    unique_items, th_to_local_indices = _dedup_for_llm(rows_without_sku)
    logger.info(
        f"prefill_llm: Dedup {len(rows_without_sku)} → {len(unique_items)} unique items"
    )

    if not unique_items:
        return rows, rule_filled, 0

    # ── Phase C: LLM batch processing ────────────────────────────────────
    truth_dict = _build_truth_dictionary(rows_with_sku)
    agent = _create_sku_agent(truth_dict)

    # Split into batches
    batches = [
        unique_items[i: i + PREFILL_BATCH_SIZE]
        for i in range(0, len(unique_items), PREFILL_BATCH_SIZE)
    ]
    total_batches = len(batches)
    logger.info(
        f"prefill_llm: {total_batches} batches × {PREFILL_BATCH_SIZE} "
        f"(max_concurrent={PREFILL_MAX_CONCURRENT})"
    )

    # Process batches with concurrency control
    semaphore = asyncio.Semaphore(PREFILL_MAX_CONCURRENT)
    llm_results: Dict[str, str] = {}  # row_id → item_code

    async def _run(batch: List[dict], bi: int) -> List[SKUItem]:
        async with semaphore:
            return await _process_batch(agent, batch, bi, total_batches)

    t_start = time.perf_counter()
    tasks = [
        asyncio.ensure_future(_run(batches[i], i + 1))
        for i in range(total_batches)
    ]

    for coro in asyncio.as_completed(tasks):
        try:
            items = await coro
            for item in items:
                llm_results[item.row_id] = item.item_code
        except Exception as exc:
            logger.warning(f"prefill_llm: batch exception: {exc}")

    elapsed = time.perf_counter() - t_start
    logger.info(
        f"prefill_llm: LLM done — {len(llm_results)}/{len(unique_items)} items "
        f"in {elapsed:.1f}s"
    )

    # ── Phase D: Propagate results ───────────────────────────────────────
    llm_filled = 0
    for th, local_indices in th_to_local_indices.items():
        # The row_id was the local index (within rows_without_sku)
        rep_rid = str(local_indices[0])
        if rep_rid in llm_results:
            code = llm_results[rep_rid]
            for local_idx in local_indices:
                # Map local_idx back to actual row in the main rows list
                actual_idx = rows_without_sku_indexed[local_idx][0]
                rows[actual_idx].ma_npl_sp = code
                rows[actual_idx].source = code  # "Mã NPL/SP (Suggested)"
                rows[actual_idx].item = "Generated"  # "Rationale"
                llm_filled += 1

    logger.info(
        f"prefill_llm: Propagated → {llm_filled} rows filled by LLM "
        f"(from {len(llm_results)} unique results)"
    )

    return rows, rule_filled, llm_filled
