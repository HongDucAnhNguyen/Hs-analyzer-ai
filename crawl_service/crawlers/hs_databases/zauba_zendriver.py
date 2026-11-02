"""Zauba crawler using Zendriver for Cloudflare bypass

Uses the CloudflareSolver from utils to bypass Cloudflare challenges on Zauba.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .base import HSCodeDatabaseCrawler, HSCodeDatabaseResult, HSCodeResult
from ...utils.cloudflare_solver import CloudflareSolver, get_chrome_user_agent

logger = logging.getLogger(__name__)


# ============================================================================
# HS Code Parsing
# ============================================================================

def parse_hs_codes_from_html(html: str, min_digits: int = 6) -> tuple[List[Dict], int]:
    """Parse HS codes from Zauba page HTML.
    
    Only returns leaf HS codes (innermost nodes), filtering out:
    1. Parent/branch codes (codes that are prefixes of other codes)
    2. Short codes like Sub Chapter (4 digits) - only keeps codes with min_digits or more
    
    For example:
    - Tree structure: 85 -> 8528 -> 85286900, only 85286900 is returned
    - USA Imports: Sub Chapter 9008 is filtered, only HS Code 900890 is kept
    
    Args:
        html: HTML content to parse
        min_digits: Minimum number of digits for HS code (default 6 to exclude Sub Chapters)
    """
    soup = BeautifulSoup(html, 'html.parser')
    all_hs_codes = []
    
    # Find all links that match HS code pattern
    all_links = soup.find_all('a', href=True)
    
    for link in all_links:
        text = link.get_text(strip=True)
        href = link.get('href', '')
        
        # Match pattern: digits followed by count in parentheses
        # Example: "85299090(20,765)" or "85299090 (20,765)"
        match = re.match(r'^(\d{4,10})\s*\(([0-9,]+)\)$', text)
        if match:
            hscode = match.group(1)
            count_str = match.group(2).replace(',', '')
            
            # Skip codes with fewer than min_digits (e.g., Sub Chapters with 4 digits)
            if len(hscode) < min_digits:
                continue
            
            try:
                count = int(count_str)
                
                all_hs_codes.append({
                    'hs_code': hscode,
                    'count': count,
                    'url': f"https://www.zauba.com{href}" if href.startswith('/') else href
                })
            except ValueError:
                continue
    
    # Filter to keep only leaf nodes (HS codes that are not prefixes of other HS codes)
    # A parent code is one where another code starts with it
    all_codes = set(item['hs_code'] for item in all_hs_codes)
    
    leaf_hs_codes = []
    for item in all_hs_codes:
        code = item['hs_code']
        # Check if this code is a parent (prefix) of any other code
        is_parent = any(
            other_code != code and other_code.startswith(code) 
            for other_code in all_codes
        )
        if not is_parent:
            leaf_hs_codes.append(item)
    
    # Calculate total records from leaf nodes only
    total_records = sum(item['count'] for item in leaf_hs_codes)
    
    # Calculate percentages
    if total_records > 0:
        for item in leaf_hs_codes:
            item['percentage'] = round((item['count'] / total_records) * 100, 2)
    else:
        for item in leaf_hs_codes:
            item['percentage'] = 0.0
    
    logger.info(f"[Zauba] Filtered to {len(leaf_hs_codes)} leaf HS codes (min {min_digits} digits)")
    
    return leaf_hs_codes, total_records


# ============================================================================
# Combined Zauba Crawler (Single Session)
# ============================================================================

class ZaubaZendriverCombinedCrawler(HSCodeDatabaseCrawler):
    """
    Combined crawler for Zauba using single browser session.
    
    Searches USA Imports, India Import, and India Export in one session,
    reusing Cloudflare cookies between requests.
    """
    
    SOURCE_USA = "Zauba (USA Imports)"
    SOURCE_INDIA_IMPORT = "Zauba (India Import)"
    SOURCE_INDIA_EXPORT = "Zauba (India Export)"
    
    # Search page URLs (where users go to search, not result pages)
    SEARCH_URL_USA = "https://www.zauba.com/USA-imports-exports/Imports"
    SEARCH_URL_INDIA = "https://www.zauba.com/shipment_search"
    
    def __init__(self, timeout: float = 60, headless: bool = True, proxy: Optional[str] = None):
        self.base_url = "https://www.zauba.com"
        self.timeout = timeout
        self.headless = headless
        self.proxy = proxy
        
    @property
    def source_name(self) -> str:
        return "Zauba Combined"
    
    @property
    def source_names(self) -> List[str]:
        return [self.SOURCE_USA, self.SOURCE_INDIA_IMPORT, self.SOURCE_INDIA_EXPORT]
    
    @property
    def search_urls(self) -> Dict[str, str]:
        """Map source names to their search page URLs"""
        return {
            self.SOURCE_USA: self.SEARCH_URL_USA,
            self.SOURCE_INDIA_IMPORT: self.SEARCH_URL_INDIA,
            self.SOURCE_INDIA_EXPORT: self.SEARCH_URL_INDIA
        }
    
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """Legacy method - returns combined results."""
        results = await self.search_multiple(query)
        all_hs_codes = []
        total_records = 0
        result_url = self.base_url
        
        for result in results:
            all_hs_codes.extend(result.hs_codes)
            total_records += result.total_count or 0
            if result.result_url:
                result_url = result.result_url
        
        return HSCodeDatabaseResult(
            source=self.source_name,
            source_url=self.base_url,
            query=query,
            hs_codes=all_hs_codes,
            result_url=result_url,
            total_count=total_records
        )
    
    async def search_multiple(self, query: str) -> List[HSCodeDatabaseResult]:
        """Search all sources using single browser session."""
        logger.info(f"[Zauba Combined] Searching: {query}")
        
        usa_result = HSCodeDatabaseResult(
            source=self.SOURCE_USA, source_url=self.SEARCH_URL_USA, query=query, hs_codes=[], result_url=self.SEARCH_URL_USA
        )
        india_import_result = HSCodeDatabaseResult(
            source=self.SOURCE_INDIA_IMPORT, source_url=self.SEARCH_URL_INDIA, query=query, hs_codes=[], result_url=self.SEARCH_URL_INDIA
        )
        india_export_result = HSCodeDatabaseResult(
            source=self.SOURCE_INDIA_EXPORT, source_url=self.SEARCH_URL_INDIA, query=query, hs_codes=[], result_url=self.SEARCH_URL_INDIA
        )
        
        try:
            async with CloudflareSolver(
                user_agent=get_chrome_user_agent(),
                timeout=self.timeout,
                headless=self.headless,
                proxy=self.proxy,
            ) as solver:
                
                # Source 1: USA Imports (form submission)
                logger.info("[Zauba Combined] === USA Imports ===")
                try:
                    await solver.navigate_and_bypass(f"{self.base_url}/USA-imports-exports/Imports")
                    
                    await solver.driver.main_tab.evaluate(f"""
                        (function() {{
                            var input = document.querySelector('#search');
                            if (input) {{
                                input.value = '{query}';
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            var submit = document.querySelector('input[type="submit"]');
                            if (submit) submit.click();
                        }})();
                    """)
                    
                    await asyncio.sleep(5)
                    html = await solver.navigate_and_bypass(await solver.get_current_url())
                    result_url = await solver.get_current_url()
                    
                    hs_codes_data, records = parse_hs_codes_from_html(html)
                    logger.info(f"[Zauba Combined] USA found {len(hs_codes_data)} HS codes")
                    
                    usa_result = HSCodeDatabaseResult(
                        source=self.SOURCE_USA,
                        source_url=self.SEARCH_URL_USA,
                        query=query,
                        hs_codes=[HSCodeResult(
                            hs_code=item['hs_code'],
                            count=item['count'],
                            percentage=item.get('percentage', 0),
                            url=item.get('url')
                        ) for item in hs_codes_data],
                        result_url=result_url,
                        total_count=records
                    )
                except Exception as e:
                    logger.warning(f"[Zauba Combined] USA failed: {e}")
                
                # Source 2: India Import (direct URL - reuses cookies)
                logger.info("[Zauba Combined] === India Import ===")
                try:
                    formatted_query = query.lower().replace(' ', '-')
                    import_url = f"{self.base_url}/import-{formatted_query}-hs-code.html"
                    
                    html = await solver.navigate_and_bypass(import_url)
                    hs_codes_data, records = parse_hs_codes_from_html(html)
                    logger.info(f"[Zauba Combined] India Import found {len(hs_codes_data)} HS codes")
                    
                    india_import_result = HSCodeDatabaseResult(
                        source=self.SOURCE_INDIA_IMPORT,
                        source_url=self.SEARCH_URL_INDIA,
                        query=query,
                        hs_codes=[HSCodeResult(
                            hs_code=item['hs_code'],
                            count=item['count'],
                            percentage=item.get('percentage', 0),
                            url=item.get('url')
                        ) for item in hs_codes_data],
                        result_url=import_url,
                        total_count=records
                    )
                except Exception as e:
                    logger.warning(f"[Zauba Combined] India Import failed: {e}")
                
                # Source 3: India Export (direct URL - reuses cookies)
                logger.info("[Zauba Combined] === India Export ===")
                try:
                    formatted_query = query.lower().replace(' ', '-')
                    export_url = f"{self.base_url}/export-{formatted_query}-hs-code.html"
                    
                    html = await solver.navigate_and_bypass(export_url)
                    hs_codes_data, records = parse_hs_codes_from_html(html)
                    logger.info(f"[Zauba Combined] India Export found {len(hs_codes_data)} HS codes")
                    
                    india_export_result = HSCodeDatabaseResult(
                        source=self.SOURCE_INDIA_EXPORT,
                        source_url=self.SEARCH_URL_INDIA,
                        query=query,
                        hs_codes=[HSCodeResult(
                            hs_code=item['hs_code'],
                            count=item['count'],
                            percentage=item.get('percentage', 0),
                            url=item.get('url')
                        ) for item in hs_codes_data],
                        result_url=export_url,
                        total_count=records
                    )
                except Exception as e:
                    logger.warning(f"[Zauba Combined] India Export failed: {e}")
            
            logger.info(f"[Zauba Combined] Done - USA: {len(usa_result.hs_codes)}, India Import: {len(india_import_result.hs_codes)}, India Export: {len(india_export_result.hs_codes)}")
            return [usa_result, india_import_result, india_export_result]
            
        except Exception as e:
            logger.error(f"[Zauba Combined] Session failed: {e}")
            return [usa_result, india_import_result, india_export_result]
