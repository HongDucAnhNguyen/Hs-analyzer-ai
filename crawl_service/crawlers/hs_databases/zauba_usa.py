"""Zauba USA Imports crawler using Direct Botasaurus (WEB2)"""

import logging
import asyncio
from typing import List
from .base import HSCodeDatabaseCrawler, HSCodeDatabaseResult, HSCodeResult
from .zauba_botasaurus import search_zauba_usa, scrape_zauba_usa_facets

logger = logging.getLogger(__name__)


class ZaubaUSACrawler(HSCodeDatabaseCrawler):
    """
    Crawler for Zauba USA Imports using Direct Botasaurus Integration
    
    WEB2: https://www.zauba.com/USA-imports-exports/Imports
    
    Flow:
    1. Input query -> search zauba.com directly with Botasaurus
    2. Get result URL like: https://www.zauba.com/projector-import-data-a17erjm39b64
    3. Extract HS codes from facets page with counts and percentages
    4. Return list of HS codes with statistics
    
    No PM2 service needed - runs directly in Docker with Xvfb
    """
    
    def __init__(self):
        self.base_url = "https://www.zauba.com"
        self.start_url = f"{self.base_url}/USA-imports-exports/Imports"
        
    @property
    def source_name(self) -> str:
        return "Zauba USA Imports"
    
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """
        Search Zauba USA for HS codes using Direct Botasaurus
        
        Steps:
        1. search_zauba_usa(query) 
           - Navigates to USA-imports-exports/Imports
           - Fills search form and submits
           - Returns result URL: projector-import-data-a17erjm39b64
        
        2. scrape_zauba_usa_facets(url_code)
           - Scrapes facets page directly
           - Parses HS codes with counts
           - Calculates percentages
        """
        logger.info(f"Searching Zauba USA for: {query}")
        
        try:
            # Step 1: Search to get URL (run in thread pool)
            search_result = await asyncio.to_thread(search_zauba_usa, query)
            
            if not search_result.get('success'):
                raise Exception(f"Search failed: {search_result.get('error')}")
            
            result_url = search_result.get('result_url')
            url_code = search_result.get('url_code')
            
            logger.info(f"Got result URL: {result_url}")
            
            # Step 2: Get facets (HS codes) - pass result_url for better scraping
            facets_result = await asyncio.to_thread(scrape_zauba_usa_facets, url_code, result_url)
            
            if not facets_result.get('success'):
                logger.warning("Failed to get HS codes from facets")
                hs_codes = []
                total_records = 0
            else:
                # Convert to HSCodeResult objects
                hs_codes = []
                for item in facets_result.get('hscodes', []):
                    hs_codes.append(HSCodeResult(
                        hs_code=item['hscode'],
                        count=item['count'],
                        percentage=item['percentage'],
                        url=item.get('url')
                    ))
                
                total_records = facets_result.get('total_records', 0)
            
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
            logger.error(f"Zauba USA search failed: {e}")
            return HSCodeDatabaseResult(
                source=self.source_name,
                query=query,
                hs_codes=[],
                result_url=self.start_url
            )

