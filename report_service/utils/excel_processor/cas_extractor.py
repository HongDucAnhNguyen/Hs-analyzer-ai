"""CAS Number Extractor for Chemical Products

This module provides functions to:
1. Extract CAS numbers from product names (ten_hang)
2. Use LLM to extract CAS when not found in product name
3. Check if CAS is in Appendix III (NĐ 24/2026) - special control chemicals
4. Check if HS code belongs to Chapter 28-29 (chemical products)

Rules for CAS extraction:
- CAS numbers are usually in parentheses ()
- Take the component with smallest % (excluding water, solvents)
- If not found, group and ask LLM

References:
- Điều 6, NĐ 26/2026/NĐ-CP: Declaration for chemicals with HS 28, 29
- Phụ lục III, NĐ 24/2026/NĐ-CP: Special control chemicals with CAS numbers
"""

import re
import json
import logging
import os
from typing import Optional, List, Dict, Tuple, Set
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================================
# CAS NUMBER REGEX PATTERNS
# ============================================================================

# CAS number format: XXXXXXX-XX-X (2-7 digits, dash, 2 digits, dash, 1 digit)
# Also matches formats like: CAS: 123-45-6, CAS No. 123-45-6, CAS#123-45-6
CAS_PATTERN = re.compile(r'\b(\d{2,7}-\d{2}-\d)\b')

# Extended CAS patterns to capture various formats
CAS_WITH_PREFIX_PATTERNS = [
    re.compile(r'CAS[:\s#\.No]*\s*(\d{2,7}-\d{2}-\d)', re.IGNORECASE),  # CAS: 123-45-6, CAS No. 123-45-6
    re.compile(r'\((\d{2,7}-\d{2}-\d)\)', re.IGNORECASE),  # (123-45-6)
    re.compile(r'\[(\d{2,7}-\d{2}-\d)\]', re.IGNORECASE),  # [123-45-6]
    re.compile(r'CAS\s*=\s*(\d{2,7}-\d{2}-\d)', re.IGNORECASE),  # CAS = 123-45-6
    re.compile(r'[_-](\d{2,7}-\d{2}-\d)\)?', re.IGNORECASE),  # carbon_1333-86-4 or carbon-1333-86-4
]

# Pattern to find components with percentage: e.g., "SUBSTANCE NAME 5.5% (CAS: 123-45-6)"
COMPONENT_WITH_PERCENT_PATTERN = re.compile(
    r'([^,;]+?)\s*(\d+(?:\.\d+)?)\s*%\s*(?:\((?:CAS[:\s#\.No]*)?(\d{2,7}-\d{2}-\d)\))?',
    re.IGNORECASE
)

# Pattern to find percentage with substance: "5.5% SUBSTANCE NAME (CAS)"
PERCENT_FIRST_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*%\s*([^,;(]+?)(?:\s*\((?:CAS[:\s#\.No]*)?(\d{2,7}-\d{2}-\d)\))?',
    re.IGNORECASE
)

# Solvents and water to exclude (Vietnamese and English)
EXCLUDED_SUBSTANCES = {
    # Water
    'water', 'nước', 'h2o', 'nuoc',
    # Common solvents
    'dung môi', 'dung moi', 'solvent', 'solvents',
    'ethanol', 'methanol', 'isopropanol', 'ipa',
    'acetone', 'aceton', 'axeton',
    'toluene', 'toluen',
    'xylene', 'xylen',
    'benzene', 'benzen',
    'dmso', 'dimethyl sulfoxide',
    'dmf', 'dimethylformamide',
    'thf', 'tetrahydrofuran',
    'dichloromethane', 'dcm',
    'chloroform',
    'ethyl acetate', 'etyl axetat',
    'petroleum ether', 'ete dầu hỏa',
    'hexane', 'hexan',
    'heptane', 'heptan',
    # Diluents
    'chất pha loãng', 'chat pha loang', 'diluent',
    'chất độn', 'chat don', 'filler',
    # Base substances
    'dầu khoáng', 'dau khoang', 'mineral oil',
    'dầu silicon', 'dau silicon', 'silicone oil',
}

# CAS numbers for water and common solvents to exclude
EXCLUDED_CAS = {
    '7732-18-5',   # Water
    '64-17-5',     # Ethanol
    '67-56-1',     # Methanol
    '67-63-0',     # Isopropanol
    '67-64-1',     # Acetone
    '108-88-3',    # Toluene
    '1330-20-7',   # Xylene (mixed)
    '71-43-2',     # Benzene
    '67-68-5',     # DMSO
    '68-12-2',     # DMF
    '109-99-9',    # THF
    '75-09-2',     # Dichloromethane
    '67-66-3',     # Chloroform
    '141-78-6',    # Ethyl acetate
    '110-54-3',    # Hexane
    '142-82-5',    # Heptane
}


# ============================================================================
# ND24 CHEMICAL DATABASE (ALL APPENDICES)
# ============================================================================

_nd24_chemical_db: Optional[Dict[str, dict]] = None


def _load_nd24_chemical_database() -> Dict[str, dict]:
    """Load ND24 chemical database (all appendices) from JSON file.
    
    This database contains ALL chemicals from Appendices I, II, III, IV
    of Decree 24/2026/NĐ-CP for CAS matching and name lookup.
    
    Returns:
        Dictionary mapping CAS numbers to chemical info
    """
    global _nd24_chemical_db
    
    if _nd24_chemical_db is not None:
        return _nd24_chemical_db
    
    data_path = Path(__file__).parent.parent.parent / "data" / "nd24_chemical_cas_database.json"
    
    try:
        if data_path.exists():
            with open(data_path, 'r', encoding='utf-8') as f:
                _nd24_chemical_db = json.load(f)
            # Don't count metadata
            count = len([k for k in _nd24_chemical_db.keys() if not k.startswith('_')])
            logger.info(f"Loaded {count} chemicals from ND24 database (all appendices)")
        else:
            logger.warning(f"ND24 chemical database not found: {data_path}")
            _nd24_chemical_db = {}
    except Exception as e:
        logger.error(f"Error loading ND24 chemical database: {e}")
        _nd24_chemical_db = {}
    
    return _nd24_chemical_db


def get_chemical_name_from_cas(cas_number: str) -> Optional[str]:
    """Get chemical name from CAS number using ND24 database.
    
    This function looks up the chemical name for a given CAS number
    from the comprehensive ND24 database (all appendices I, II, III, IV).
    
    Args:
        cas_number: CAS number to look up (e.g., "123-45-6")
        
    Returns:
        Chemical name if found, None otherwise
    """
    if not cas_number:
        return None
    
    db = _load_nd24_chemical_database()
    cas_clean = cas_number.strip()
    
    if cas_clean in db and not cas_clean.startswith('_'):
        entry = db[cas_clean]
        if isinstance(entry, dict):
            return entry.get('name')
        elif isinstance(entry, str):
            return entry
    
    return None


def get_chemical_appendix_info(cas_number: str) -> Optional[List[str]]:
    """Get which appendices a chemical belongs to.
    
    Args:
        cas_number: CAS number to look up
        
    Returns:
        List of appendix numbers (e.g., ['I', 'II', 'III']) or None
    """
    if not cas_number:
        return None
    
    db = _load_nd24_chemical_database()
    cas_clean = cas_number.strip()
    
    if cas_clean in db and not cas_clean.startswith('_'):
        entry = db[cas_clean]
        if isinstance(entry, dict):
            return entry.get('appendix', [])
    
    return None


def check_cas_in_appendix_iii(cas_number: str) -> Tuple[bool, Optional[str]]:
    """Check if CAS number is in Appendix III (special control chemicals).
    
    Uses the ND24 database to check if a CAS is in Appendix III,
    which requires special permits before customs clearance.
    
    Args:
        cas_number: CAS number to check (e.g., "123-45-6")
        
    Returns:
        Tuple of (is_in_appendix_iii, chemical_name_if_found)
    """
    if not cas_number:
        return False, None
    
    db = _load_nd24_chemical_database()
    cas_clean = cas_number.strip()
    
    if cas_clean in db and not cas_clean.startswith('_'):
        entry = db[cas_clean]
        if isinstance(entry, dict):
            appendix_list = entry.get('appendix', [])
            if 'III' in appendix_list:
                return True, entry.get('name')
    
    return False, None


def check_hs_chapter_28_29(hs_code: str) -> bool:
    """Check if HS code belongs to Chapter 28 or 29 (chemical products).
    
    Chapter 28: Inorganic chemicals
    Chapter 29: Organic chemicals
    
    According to Điều 6, NĐ 26/2026/NĐ-CP, chemicals with HS codes in 
    Chapter 28 and 29 must be declared when importing.
    
    Args:
        hs_code: HS code (can be 6 or 8 digits)
        
    Returns:
        True if HS code is in Chapter 28 or 29
    """
    if not hs_code:
        return False
    
    hs_clean = str(hs_code).strip()[:2]
    
    try:
        chapter = int(hs_clean)
        return chapter in (28, 29)
    except ValueError:
        return False


# ============================================================================
# CAS EXTRACTION FROM PRODUCT NAME
# ============================================================================

def extract_cas_from_ten_hang(ten_hang: str) -> Tuple[Optional[str], Optional[float]]:
    """Extract CAS number from product name (ten_hang) using regex patterns.
    
    Strategy:
    1. Try to find CAS number directly in text (regex patterns)
    2. Look for components with percentage
    3. Exclude water, solvents, and other excluded substances
    4. Return CAS of the component with SMALLEST percentage
    
    If CAS not found in text, use LLM fallback (get_cas_via_llm_sync).
    
    Format examples in ten_hang:
    - "Hóa chất A 15% (CAS: 123-45-6), Hóa chất B 5% (456-78-9), Nước 80%"
    - "CHEMICAL A (CAS 123-45-6) 10%, SOLVENT 90%"
    - "Product containing Substance (123-45-6) at 2.5%"
    
    Args:
        ten_hang: Product name string
        
    Returns:
        Tuple of (cas_number, percentage) or (None, None) if not found
    """
    if not ten_hang:
        return None, None
    
    # Normalize text
    text = ten_hang.strip()
    
    # Find all components with percentages
    components = []
    
    # Pattern 1: "SUBSTANCE NAME XX% (CAS: YYY-YY-Y)" or "SUBSTANCE NAME XX% (YYY-YY-Y)"
    for match in COMPONENT_WITH_PERCENT_PATTERN.finditer(text):
        substance_name = match.group(1).strip().lower()
        percentage = float(match.group(2))
        cas_number = match.group(3)  # May be None
        
        # If CAS not in this pattern, try to find it nearby
        if not cas_number:
            # Look for CAS in the substance name itself
            cas_in_name = CAS_PATTERN.search(match.group(0))
            if cas_in_name:
                cas_number = cas_in_name.group(1)
        
        if cas_number:
            components.append({
                'name': substance_name,
                'percentage': percentage,
                'cas': cas_number
            })
    
    # Pattern 2: "XX% SUBSTANCE NAME (CAS)"
    if not components:
        for match in PERCENT_FIRST_PATTERN.finditer(text):
            percentage = float(match.group(1))
            substance_name = match.group(2).strip().lower()
            cas_number = match.group(3)
            
            if cas_number:
                components.append({
                    'name': substance_name,
                    'percentage': percentage,
                    'cas': cas_number
                })
    
    # If no components found with percentage patterns, try to find CAS with various prefixes
    if not components:
        # Try all CAS patterns with prefix
        for pattern in CAS_WITH_PREFIX_PATTERNS:
            for match in pattern.finditer(text):
                cas = match.group(1)
                if cas not in EXCLUDED_CAS:
                    # Look for percentage near this CAS
                    cas_pos = match.start()
                    context_before = text[max(0, cas_pos - 80):cas_pos]
                    context_after = text[cas_pos:min(len(text), cas_pos + 80)]
                    
                    percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', context_before + context_after)
                    percentage = float(percent_match.group(1)) if percent_match else 100.0
                    
                    components.append({
                        'name': 'unknown',
                        'percentage': percentage,
                        'cas': cas
                    })
    
    # Fallback: Find any CAS numbers in text
    if not components:
        all_cas = CAS_PATTERN.findall(text)
        if all_cas:
            for cas in all_cas:
                if cas in EXCLUDED_CAS:
                    continue
                    
                # Look for percentage near CAS
                cas_pos = text.find(cas)
                context = text[max(0, cas_pos - 80):min(len(text), cas_pos + 80)]
                percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', context)
                
                if percent_match:
                    percentage = float(percent_match.group(1))
                else:
                    percentage = 100.0
                    
                components.append({
                    'name': 'unknown',
                    'percentage': percentage,
                    'cas': cas
                })
    
    if not components:
        return None, None
    
    # Filter out excluded substances and CAS numbers
    filtered_components = []
    for comp in components:
        # Check if CAS is excluded
        if comp['cas'] in EXCLUDED_CAS:
            continue
            
        # Check if substance name contains excluded terms
        is_excluded = False
        for excluded in EXCLUDED_SUBSTANCES:
            if excluded in comp['name']:
                is_excluded = True
                break
        
        if not is_excluded:
            filtered_components.append(comp)
    
    if not filtered_components:
        # If all components were excluded, return the first non-excluded CAS found
        for comp in components:
            if comp['cas'] not in EXCLUDED_CAS:
                return comp['cas'], comp['percentage']
        return None, None
    
    # Return CAS of component with smallest percentage
    min_component = min(filtered_components, key=lambda x: x['percentage'])
    return min_component['cas'], min_component['percentage']


def extract_all_cas_from_ten_hang(ten_hang: str) -> List[Dict]:
    """Extract all CAS numbers from product name.
    
    Args:
        ten_hang: Product name string
        
    Returns:
        List of dicts with 'cas', 'percentage', 'is_excluded' fields
    """
    if not ten_hang:
        return []
    
    text = ten_hang.strip()
    results = []
    
    # Find all CAS numbers
    for cas_match in CAS_PATTERN.finditer(text):
        cas = cas_match.group(1)
        
        # Look for percentage before CAS
        cas_pos = cas_match.start()
        context = text[max(0, cas_pos - 100):cas_pos]
        percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', context)
        
        percentage = float(percent_match.group(1)) if percent_match else None
        is_excluded = cas in EXCLUDED_CAS
        
        results.append({
            'cas': cas,
            'percentage': percentage,
            'is_excluded': is_excluded,
            'in_appendix_iii': check_cas_in_appendix_iii(cas)[0]
        })
    
    return results


# ============================================================================
# LLM-BASED CAS EXTRACTION
# ============================================================================

# LLM Agent for CAS extraction (lazy initialization)
_cas_extractor_agent = None


def _get_cas_extractor_agent():
    """Get or create the CAS extractor LLM agent (lazy initialization)."""
    global _cas_extractor_agent
    
    if _cas_extractor_agent is None:
        try:
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.models.gemini import GeminiModel
            from pydantic import BaseModel, Field
            from typing import List, Optional
            
            class CASExtractionResult(BaseModel):
                """Result of CAS extraction from product name."""
                cas_numbers: List[str] = Field(
                    default_factory=list,
                    description="List of CAS numbers found (format: XXXXXXX-XX-X)"
                )
                primary_cas: Optional[str] = Field(
                    None,
                    description="Primary CAS number (smallest %, excluding water/solvents)"
                )
                confidence: float = Field(
                    0.0,
                    description="Confidence score 0-1"
                )
                reasoning: str = Field(
                    "",
                    description="Brief explanation"
                )
            
            provider = os.getenv("LLM_PROVIDER", "openai").lower()
            model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
            
            if provider == "gemini":
                gemini_model = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash-lite")
                model = GeminiModel(gemini_model)
            else:
                model = OpenAIModel(model_name)
            
            _cas_extractor_agent = Agent(
                model=model,
                output_type=CASExtractionResult,
                system_prompt="""You are an expert chemist with extensive knowledge of chemical CAS numbers.
Your task is to IDENTIFY the CAS number for chemicals mentioned in Vietnamese product names.

IMPORTANT: You must use your knowledge to GUESS the CAS number even if it's not explicitly written in the text.

Strategy:
1. Identify the main chemical/substance from the product name (brand names, chemical names, formulas)
2. Use your knowledge to find the CAS number for that chemical
3. Common product types and their CAS numbers:
   - Powder coatings hardeners (RB, Primid, B-HAA) → β-hydroxyalkylamide: 6334-25-4
   - Thermal paper/ink ribbons → often contain dyes or waxes
   - Titanium dioxide (TiO2) → 13463-67-7
   - Carbon black → 1333-86-4
   - Silicon dioxide (SiO2, silica) → 7631-86-9
   - Iron oxide → 1309-37-1
   - Calcium carbonate → 471-34-1
   - Aluminum oxide → 1344-28-1

4. For non-chemical products (electronics, machinery, paper), return "N/A" in reasoning

Vietnamese terms:
- "chất tạo độ cứng" = hardener/curing agent
- "bột sơn tĩnh điện" = powder coating
- "hộp mực" = ink cartridge/ribbon
- "máy ghi nhiệt độ" = temperature recorder

ALWAYS try to provide a CAS number based on your chemical knowledge. Set confidence based on how sure you are.""",
            )
            
            logger.info(f"CAS Extractor Agent initialized with provider: {provider}")
        except Exception as e:
            logger.error(f"Failed to initialize CAS Extractor Agent: {e}")
            _cas_extractor_agent = None
    
    return _cas_extractor_agent


async def extract_cas_via_llm(ten_hang: str) -> Tuple[Optional[str], float]:
    """Use LLM to extract CAS number from product name.
    
    This is used when simple regex extraction fails.
    
    Args:
        ten_hang: Product name string
        
    Returns:
        Tuple of (cas_number, confidence) or (None, 0.0) if not found
    """
    if not ten_hang:
        return None, 0.0
    
    agent = _get_cas_extractor_agent()
    if agent is None:
        logger.warning("CAS Extractor Agent not available")
        return None, 0.0
    
    try:
        prompt = f"""Identify the CAS number for this Vietnamese product:

"{ten_hang}"

Instructions:
1. Identify the main chemical substance from the product name
2. Use your chemistry knowledge to determine its CAS number
3. For hardeners like "RB 68", "Primid" → likely β-hydroxyalkylamide (CAS: 6334-25-4)
4. For ink/thermal products → identify the main dye or chemical component
5. If truly non-chemical (pure electronics/machinery), set primary_cas to None

You MUST provide a CAS number if any chemical can be identified. Use format: XXXXXXX-XX-X"""
        
        result = await agent.run(prompt)
        output = result.output
        
        if output.primary_cas:
            # Validate CAS format
            if CAS_PATTERN.match(output.primary_cas):
                return output.primary_cas, output.confidence
            # Try without validation for edge cases
            cas_match = CAS_PATTERN.search(output.primary_cas)
            if cas_match:
                return cas_match.group(1), output.confidence
        
        return None, 0.0
        
    except Exception as e:
        logger.error(f"LLM CAS extraction failed: {e}")
        return None, 0.0


async def extract_cas_batch_via_llm(products: List[str]) -> Dict[str, Optional[str]]:
    """Extract CAS numbers for multiple products using LLM.
    
    More efficient for batch processing.
    
    Args:
        products: List of product names
        
    Returns:
        Dictionary mapping product name to CAS number
    """
    results = {}
    
    for product in products:
        cas, _ = await extract_cas_via_llm(product)
        results[product] = cas
    
    return results


# ============================================================================
# COMBINED EXTRACTION LOGIC
# ============================================================================

async def get_cas_number(
    ten_hang: str, 
    use_llm_fallback: bool = True
) -> Tuple[Optional[str], str]:
    """Get CAS number using combined strategies.
    
    Strategy:
    1. First try regex extraction from product name
    2. If not found and use_llm_fallback=True, use LLM
    
    Args:
        ten_hang: Product name
        use_llm_fallback: Whether to use LLM if regex fails
        
    Returns:
        Tuple of (cas_number, source) where source is 'regex', 'llm', or 'not_found'
    """
    # Try regex first
    cas, percentage = extract_cas_from_ten_hang(ten_hang)
    
    if cas:
        return cas, 'regex'
    
    # Try LLM fallback
    if use_llm_fallback:
        cas, confidence = await extract_cas_via_llm(ten_hang)
        if cas and confidence > 0.5:
            return cas, 'llm'
    
    return None, 'not_found'


def analyze_chemical_compliance(
    hs_code: str, 
    cas_number: Optional[str]
) -> Dict[str, any]:
    """Analyze chemical product for regulatory compliance.
    
    Checks:
    1. HS Chapter 28-29 → Must declare (Điều 6, NĐ 26/2026)
    2. CAS in Appendix III → Special control (NĐ 24/2026)
    
    Args:
        hs_code: HS code of the product
        cas_number: CAS number if available
        
    Returns:
        Dictionary with compliance analysis
    """
    result = {
        'hs_code': hs_code,
        'cas_number': cas_number,
        'is_chapter_28_29': False,
        'requires_declaration': False,
        'is_special_control': False,
        'appendix_iii_name': None,
        'regulations': [],
    }
    
    # Check HS Chapter 28-29
    if check_hs_chapter_28_29(hs_code):
        result['is_chapter_28_29'] = True
        result['requires_declaration'] = True
        result['regulations'].append(
            "Khai báo hóa chất theo Điều 6, NĐ 26/2026/NĐ-CP (HS Chương 28/29)"
        )
    
    # Check Appendix III
    if cas_number:
        is_in_appendix, chemical_name = check_cas_in_appendix_iii(cas_number)
        if is_in_appendix:
            result['is_special_control'] = True
            result['appendix_iii_name'] = chemical_name
            result['regulations'].append(
                f"Hóa chất kiểm soát đặc biệt theo Phụ lục III, NĐ 24/2026/NĐ-CP: {chemical_name}"
            )
    
    return result


# ============================================================================
# SYNCHRONOUS LLM CAS EXTRACTION (for use in non-async contexts)
# ============================================================================

def get_cas_via_llm_sync(ten_hang: str) -> Optional[str]:
    """Synchronous wrapper to get CAS number via LLM.
    
    This is used when calling from synchronous code (e.g., Excel generation).
    
    Args:
        ten_hang: Product name string
        
    Returns:
        CAS number if found, None otherwise
    """
    import asyncio
    
    if not ten_hang:
        return None
    
    try:
        # Try to get existing event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, extract_cas_via_llm(ten_hang))
                cas, confidence = future.result(timeout=30)
        except RuntimeError:
            # No running event loop, we can use asyncio.run directly
            cas, confidence = asyncio.run(extract_cas_via_llm(ten_hang))
        
        if cas and confidence > 0.3:  # Lower threshold for LLM results
            logger.info(f"LLM extracted CAS: {cas} (confidence: {confidence:.2f}) from '{ten_hang[:50]}...'")
            return cas
        
        return None
        
    except Exception as e:
        logger.warning(f"LLM CAS extraction failed for '{ten_hang[:50]}...': {e}")
        return None


def batch_extract_cas_via_llm_sync(products: List[str]) -> Dict[str, Optional[str]]:
    """Batch extract CAS numbers using LLM (synchronous).
    
    OPTIMIZED VERSION:
    - Deduplicates product names to avoid redundant LLM calls
    - Sends multiple products in a single LLM request (batching)
    - Maps results back to all original product names
    
    Args:
        products: List of product names (may contain duplicates)
        
    Returns:
        Dictionary mapping product name to CAS number
    """
    if not products:
        return {}
    
    # STEP 1: Deduplicate product names
    unique_products = list(set(p.strip() for p in products if p and p.strip()))
    
    if not unique_products:
        return {}
    
    logger.info(f"CAS batch extraction: {len(products)} products → {len(unique_products)} unique")
    
    # STEP 2: Call batched LLM extraction for unique products
    results = _extract_cas_batch_single_call(unique_products)
    
    # STEP 3: Map results back to all original product names (including duplicates)
    final_results = {}
    for product in products:
        if product and product.strip():
            product_clean = product.strip()
            final_results[product] = results.get(product_clean)
    
    return final_results


def _extract_cas_batch_single_call(unique_products: List[str], batch_size: int = 20) -> Dict[str, Optional[str]]:
    """Extract CAS numbers for multiple unique products in batched LLM calls.
    
    Sends multiple products in a single LLM prompt to reduce API calls.
    Processes in batches of batch_size to avoid token limits.
    
    Args:
        unique_products: List of unique product names
        batch_size: Maximum products per LLM call (default 20)
        
    Returns:
        Dictionary mapping product name to CAS number
    """
    import asyncio
    
    all_results = {}
    
    # Process in batches
    for i in range(0, len(unique_products), batch_size):
        batch = unique_products[i:i + batch_size]
        logger.info(f"Processing CAS batch {i//batch_size + 1}: {len(batch)} products")
        
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _extract_cas_batch_async(batch))
                    batch_results = future.result(timeout=60)
            except RuntimeError:
                # No running event loop
                batch_results = asyncio.run(_extract_cas_batch_async(batch))
            
            all_results.update(batch_results)
            
        except Exception as e:
            logger.warning(f"Batch CAS extraction failed: {e}, falling back to individual calls")
            # Fallback: individual calls for this batch
            for product in batch:
                if product not in all_results:
                    cas = get_cas_via_llm_sync(product)
                    all_results[product] = cas
    
    return all_results


async def _extract_cas_batch_async(products: List[str]) -> Dict[str, Optional[str]]:
    """Async batch extraction - sends multiple products in ONE LLM call.
    
    Args:
        products: List of product names (max ~20 for token limits)
        
    Returns:
        Dictionary mapping product name to CAS number
    """
    if not products:
        return {}
    
    agent = _get_batch_cas_extractor_agent()
    if agent is None:
        logger.warning("Batch CAS Extractor Agent not available, falling back to individual calls")
        results = {}
        for p in products:
            cas, _ = await extract_cas_via_llm(p)
            results[p] = cas
        return results
    
    try:
        # Build numbered list for clear mapping
        product_list = "\n".join([f"{i+1}. {p}" for i, p in enumerate(products)])
        
        prompt = f"""Identify CAS numbers for these Vietnamese products. 
Return the CAS number (format: XXXXXXX-XX-X) for each product, or "N/A" if not a chemical.

Products:
{product_list}

IMPORTANT:
- Use your chemistry knowledge to determine CAS numbers even if not explicitly stated
- Common chemicals: TiO2=13463-67-7, Al2O3=1344-28-1, SiO2=7631-86-9, CaCO3=471-34-1
- Return ONLY a numbered list matching the input order
- Each line: "number. CAS-NUMBER" or "number. N/A"
"""
        
        result = await agent.run(prompt)
        output = result.output
        
        # Parse results
        results = {}
        if output.results:
            for i, cas in enumerate(output.results):
                if i < len(products):
                    product = products[i]
                    if cas and cas != "N/A" and CAS_PATTERN.match(cas):
                        results[product] = cas
                        logger.info(f"Batch CAS: {cas} from '{product[:40]}...'")
                    else:
                        results[product] = None
        
        # Fill any missing products
        for product in products:
            if product not in results:
                results[product] = None
        
        return results
        
    except Exception as e:
        logger.error(f"Batch LLM extraction failed: {e}")
        return {p: None for p in products}


# Batch CAS extractor agent (lazy initialization)
_batch_cas_extractor_agent = None


def _get_batch_cas_extractor_agent():
    """Get or create the batch CAS extractor LLM agent."""
    global _batch_cas_extractor_agent
    
    if _batch_cas_extractor_agent is None:
        try:
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.models.gemini import GeminiModel
            from pydantic import BaseModel, Field
            from typing import List, Optional
            
            class BatchCASResult(BaseModel):
                """Result of batch CAS extraction."""
                results: List[Optional[str]] = Field(
                    default_factory=list,
                    description="List of CAS numbers in same order as input, None or 'N/A' if not found"
                )
            
            provider = os.getenv("LLM_PROVIDER", "openai").lower()
            model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
            
            if provider == "gemini":
                gemini_model = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash-lite")
                model = GeminiModel(gemini_model)
            else:
                model = OpenAIModel(model_name)
            
            _batch_cas_extractor_agent = Agent(
                model=model,
                output_type=BatchCASResult,
                system_prompt="""You are an expert chemist. Extract CAS numbers for a LIST of products.

For each product:
1. Identify the main chemical substance
2. Return its CAS number (format: XXXXXXX-XX-X)
3. Use "N/A" for non-chemical products

Common chemicals:
- Titanium dioxide (TiO2) → 13463-67-7
- Aluminum oxide (Al2O3, AEROXIDE) → 1344-28-1  
- Silicon dioxide (SiO2) → 7631-86-9
- Carbon black → 1333-86-4
- Calcium carbonate → 471-34-1
- Iron oxide → 1309-37-1
- β-hydroxyalkylamide (RB, Primid) → 6334-25-4

Return results in the SAME ORDER as input products.""",
            )
            
            logger.info(f"Batch CAS Extractor Agent initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Batch CAS Extractor Agent: {e}")
            _batch_cas_extractor_agent = None
    
    return _batch_cas_extractor_agent

