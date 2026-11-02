"""Zauba Shipment Search crawler using Direct Botasaurus (WEB3)"""

import logging
from typing import List
from .base import HSCodeDatabaseCrawler, HSCodeDatabaseResult, HSCodeResult
from .zauba_botasaurus import search_zauba_shipment

logger = logging.getLogger(__name__)


class ZaubaShipmentCrawler(HSCodeDatabaseCrawler):
    """
    Crawler for Zauba Shipment Search - Direct Botasaurus Integration
    
    WEB3: https://www.zauba.com/shipment_search
    URL format: https://www.zauba.com/import-{query}-hs-code.html
    
    Parses HTS Code listing from HTML and extracts:
    - HS codes in format: 85299090(20,765)
    - Count of times each code appeared
    - Percentage of each code
    
    No PM2 service needed - runs directly in Docker with Xvfb
    """
    
    def __init__(self):
        self.base_url = "https://www.zauba.com"
        
    @property
    def source_name(self) -> str:
        return "Zauba Shipment Search"
    
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """
        Search Zauba Shipment for HS codes via Direct Botasaurus
        
        Flow:
        1. Format query: "projector" -> "projector"
        2. Navigate to: https://www.zauba.com/import-projector-hs-code.html
        3. Parse HTS Code section for codes like: 85299090(20,765)
        4. Return list with counts and percentages
        """
        logger.info(f"Searching Zauba Shipment for: {query}")
        
        try:
            # Call Botasaurus search in executor (blocking call)
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, search_zauba_shipment, query)
            
            if not result:
                raise Exception("No result returned")
            
            # Convert to HSCodeResult objects
            hs_codes = []
            for item in result.get('hs_codes', []):
                hs_codes.append(HSCodeResult(
                    hs_code=item['hs_code'],
                    count=item.get('count'),
                    percentage=item.get('percentage'),
                    url=item.get('url')
                ))
            
            result_url = result.get('result_url', '')
            total_records = result.get('total_records', 0)
            
            logger.info(
                f"Found {len(hs_codes)} HS codes, "
                f"total records: {total_records:,}"
            )
            
            return HSCodeDatabaseResult(
                source=self.source_name,
                query=query,
                hs_codes=hs_codes,
                result_url=result_url,
                total_count=total_records
            )
            
        except Exception as e:
            logger.error(f"Zauba Shipment search failed: {e}")
            formatted_query = query.lower().replace(' ', '-')
            fallback_url = f"{self.base_url}/import-{formatted_query}-hs-code.html"
            
            return HSCodeDatabaseResult(
                source=self.source_name,
                query=query,
                hs_codes=[],
                result_url=fallback_url
            )

