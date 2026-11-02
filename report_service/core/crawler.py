"""TRAINS Online Crawler

Crawls the TRAINS Online website (https://trainsonline.unctad.org/)
to find NTM (Non-Tariff Measures) data using HS Codes.

Uses pre-loaded JSON mapping for HS code → Product ID lookup (no API calls needed).
"""

import logging
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Load HS code to Product ID mapping at module level (singleton)
_HS_CODE_PRODUCT_ID_MAP: Optional[Dict[str, int]] = None


def _load_hs_code_mapping() -> Dict[str, int]:
    """Load HS code to Product ID mapping from JSON file
    
    Returns:
        Dictionary mapping 6-digit HS codes to product IDs
    """
    global _HS_CODE_PRODUCT_ID_MAP
    
    if _HS_CODE_PRODUCT_ID_MAP is not None:
        return _HS_CODE_PRODUCT_ID_MAP
    
    # Try multiple possible paths
    possible_paths = [
        Path(__file__).parent.parent / "data" / "hs_code_product_ids.json",
        Path("report_service/data/hs_code_product_ids.json"),
        Path("/app/report_service/data/hs_code_product_ids.json"),  # Docker
    ]
    
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, "r") as f:
                    _HS_CODE_PRODUCT_ID_MAP = json.load(f)
                logger.info(f"Loaded {len(_HS_CODE_PRODUCT_ID_MAP)} HS code mappings from {path}")
                return _HS_CODE_PRODUCT_ID_MAP
            except Exception as e:
                logger.warning(f"Failed to load HS code mapping from {path}: {e}")
                continue
    
    logger.error("Could not load HS code mapping file from any path")
    _HS_CODE_PRODUCT_ID_MAP = {}
    return _HS_CODE_PRODUCT_ID_MAP


def get_product_id_from_hs_code(hs_code_6: str) -> Optional[int]:
    """Get product ID for a 6-digit HS code from pre-loaded mapping
    
    Args:
        hs_code_6: 6-digit HS code
        
    Returns:
        Product ID if found, None otherwise
    """
    mapping = _load_hs_code_mapping()
    return mapping.get(hs_code_6)


# Crawl TRAINS to fetch links -> attach them to NTM report items
class TrainsOnlineCrawler:
    """Crawler for TRAINS Online website
    
    Searches for NTM data using 6-digit HS codes.
    Uses pre-loaded JSON mapping for instant HS code → Product ID lookup.
    """
    
    BASE_URL = "https://trainsonline.unctad.org"
    SEARCH_PATH = "/detailedSearch"
    
    # Default country codes - Vietnam (204) as imposing country
    DEFAULT_IMPOSING_COUNTRY = "204"  # Vietnam
    
    # All affected countries (from the user's provided URL)
    ALL_AFFECTED_COUNTRIES = (
        "1,2,4,5,6,7,190,3,8,10,16,153,11,12,9,13,14,15,17,34,18,26,59,19,20,21,155,22,23,24,25,273,27,29,30,31,"
        "242,33,38,35,36,37,39,40,42,43,44,46,47,48,49,51,53,54,55,56,152,57,58,250,110,52,60,79,61,62,63,234,64,"
        "65,67,68,215,66,279,69,70,72,73,75,77,78,80,82,81,84,85,86,88,89,90,92,93,236,94,179,95,96,97,98,99,100,"
        "101,102,103,104,105,106,107,108,109,111,112,237,274,114,113,115,87,277,118,119,120,123,121,122,124,125,"
        "127,128,129,130,131,132,133,134,135,168,137,138,139,167,275,142,141,143,144,145,146,32,148,149,150,151,"
        "254,256,156,158,159,160,161,162,163,116,233,165,164,147,257,170,169,83,171,259,172,173,174,175,176,177,"
        "178,182,184,185,186,187,188,189,191,192,193,194,247,195,196,278,197,198,199,272,200,201,202,154,203,205,"
        "28,206,207,71,117,210,209,41,211,264,213,214,216,217,218,45,219,239,220,180,221,222,223,224,226,228,229,"
        "230,227,265,231,232,225,235,240,166,269,243,244,157,245,204,276,246,212,248,263,271,249,208,74"
    )
    
    # All NTM types
    ALL_NTM_TYPES = "A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P"
    
    # Columns visibility configuration (from user's provided URL)
    COLUMNS_VISIBILITY = json.dumps({
        "countryImposingNTMsVisible": True,
        "affectedCountriesNamesVisible": True,
        "ntmCodeVisible": True,
        "ntmDescriptionVisible": True,
        "measureDescriptionVisible": True,
        "productDescriptionVisible": False,
        "hsCodeVisible": True,
        "issuingAgencyVisible": False,
        "regulationTitleVisible": True,
        "regulationSymbolVisible": False,
        "implementationDateVisible": True,
        "regulationFileVisible": True,
        "regulationOfficialTitleOriginalVisible": False,
        "measureDescriptionOriginalVisible": False,
        "measureProductDescriptionOriginalVisible": False,
        "supportingRegulationsVisible": False,
        "measureObjectivesOriginalVisible": False,
        "yearsOfDataCollectionVisible": False,
        "repealDateVisible": False,
        "objectiveCodesVisible": True
    })

    def __init__(
        self,
        base_url: str = BASE_URL,
        imposing_country: str = DEFAULT_IMPOSING_COUNTRY,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """Initialize the crawler
        
        Args:
            base_url: Base URL for TRAINS Online
            imposing_country: Country code for imposing country (default: Vietnam/204)
            timeout: Request timeout in seconds (not used in new implementation)
            max_retries: Maximum number of retries (not used in new implementation)
        """
        self.base_url = base_url
        self.imposing_country = imposing_country
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Pre-load HS code mapping
        _load_hs_code_mapping()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        pass

    async def search_by_hs_code(
        self, 
        hs_code_6_digit: str, 
        decision_1357: Optional[str] = None
    ) -> str:
        """Search TRAINS Online for a given 6-digit HS Code
        
        Uses pre-loaded JSON mapping - no HTTP calls needed.
        
        Args:
            hs_code_6_digit: 6-digit HS code to search for
            decision_1357: Import/Export decision from QĐ 1357 field
                - "Import" or contains "import" → search Import NTMs
                - "Export" or contains "export" → search Export NTMs
                - None or other → search both Import and Export NTMs
            
        Returns:
            Train Link URL if found, "NA" if not found
        """
        if len(hs_code_6_digit) < 6:
            logger.warning(f"Invalid HS code length: {hs_code_6_digit}")
            return "NA"
            
        # Use first 6 digits
        hs_code = hs_code_6_digit[:6]
        
        # Determine Import/Export based on decision_1357
        is_import, is_export = self._parse_decision_1357(decision_1357)
        
        # Get the product ID from pre-loaded mapping (instant lookup)
        product_id = get_product_id_from_hs_code(hs_code)
        
        if product_id:
            # Build the detailed search URL with the product ID
            train_link = self._build_search_url(str(product_id), is_import, is_export)
            logger.debug(f"Found Train Link for HS code {hs_code} (product_id: {product_id})")
            return train_link
        else:
            # 6-digit HS code not found in mapping
            logger.debug(f"HS code {hs_code} not found in mapping")
            return "NA"

    def _parse_decision_1357(self, decision_1357: Optional[str]) -> Tuple[bool, bool]:
        """Parse the decision_1357 field to determine Import/Export flags
        
        Args:
            decision_1357: Value from QĐ 1357 column
            
        Returns:
            Tuple of (is_import, is_export) booleans
        """
        if not decision_1357:
            # If no value, select both Import and Export
            return True, True
        
        decision_lower = decision_1357.lower().strip()
        
        if "import" in decision_lower:
            return True, False  # Only Import
        elif "export" in decision_lower:
            return False, True  # Only Export
        else:
            # Default: select both
            return True, True

    def _build_search_url(
        self, 
        product_id: str, 
        is_import: bool = True, 
        is_export: bool = True
    ) -> str:
        """Build the TRAINS detailed search URL with a product ID
        
        Default settings:
        - Economies applying the NTMs: Viet Nam (204)
        - Affected Markets: All economies
        - Products affected: product_id (from HS code lookup)
        - Type(s) of NTMs: All NTM Types
        - Date(s): Empty (no date filter)
        - Import or Export NTMs: Based on decision_1357
        - Multilateral or Bilateral NTMs: Both selected
        
        Args:
            product_id: Internal TRAINS product ID
            is_import: Whether to search Import NTMs
            is_export: Whether to search Export NTMs
            
        Returns:
            Full search URL
        """
        params = {
            "imposingCountries": self.imposing_country,  # Viet Nam (204)
            "imposingCountriesGroupSelection": "",
            "imposingCountriesAll": "false",
            "internationalStandardsImposing": "false",
            "imposingCountriesGroup": "0",
            # When affectedCountriesAll=true (select all), still need the full list
            "affectedCountries": self.ALL_AFFECTED_COUNTRIES,  # All economies list
            "affectedCountriesGroupSelection": "",
            "affectedCountriesAll": "true",  # Select all economies checkbox
            "affectedCountriesGroup": "0",
            "products": product_id,  # 6-digit HS code product
            "productsAll": "false",
            "productsGroup": "0",
            # When allNtmTypes=true (select all), still need the full list
            "ntmTypes": self.ALL_NTM_TYPES,  # All NTM types list (A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P)
            "allNtmTypes": "true",  # Select all NTM types checkbox
            "fromDate": "",  # No date filter
            "toDate": "",
            "excludeHorizontal": "false",  # Set to false as per example URL
            "import": "true" if is_import else "false",  # Based on decision_1357
            "export": "true" if is_export else "false",  # Based on decision_1357
            "multilateral": "true",  # Both Multilateral
            "unilateral": "true",    # and Bilateral selected
            "pageNumber": "1",
            "columnsVisibility": self.COLUMNS_VISIBILITY
        }
        
        query_string = urlencode(params, safe=',')
        return f"{self.base_url}{self.SEARCH_PATH}?{query_string}"

    async def batch_search(
        self,
        items: List[Dict[str, str]],
        max_concurrent: int = 5,
        delay_between_requests: float = 0.5
    ) -> Dict[str, str]:
        """Search for multiple items in batch
        
        Since we use pre-loaded mapping, this is now instant (no HTTP calls).
        Parameters max_concurrent and delay_between_requests are kept for API compatibility
        but are not used.
        
        Args:
            items: List of dicts with 'hs_code' and optionally 'decision_1357' keys
                   Each item should have:
                   - hs_code: 6-digit HS code
                   - decision_1357: Import/Export indicator (optional)
            max_concurrent: Not used (kept for API compatibility)
            delay_between_requests: Not used (kept for API compatibility)
            
        Returns:
            Dictionary mapping "hs_code:decision" key to train_link (URL or "NA")
        """
        results: Dict[str, str] = {}
        
        # Deduplicate by hs_code + decision_1357 combination
        seen = set()
        unique_items = []
        for item in items:
            hs_code = item.get("hs_code", "")[:6]
            decision = item.get("decision_1357")
            key = f"{hs_code}:{decision or 'both'}"
            if key not in seen:
                seen.add(key)
                unique_items.append((hs_code, decision, key))
        
        # Process all items (instant lookup from pre-loaded mapping)
        for hs_code, decision, key in unique_items:
            train_link = await self.search_by_hs_code(hs_code, decision)
            results[key] = train_link
        
        found_count = sum(1 for v in results.values() if v != "NA")
        logger.info(f"Batch search completed: {found_count}/{len(results)} HS codes found")
        
        return results

    async def close(self):
        """Close - no resources to clean up with pre-loaded mapping"""
        pass
