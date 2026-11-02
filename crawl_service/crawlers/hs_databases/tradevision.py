"""The Trade Vision crawler"""

import logging
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict
from collections import Counter
from .base import HSCodeDatabaseCrawler, HSCodeDatabaseResult, HSCodeResult

logger = logging.getLogger(__name__)


class TradeVisionCrawler(HSCodeDatabaseCrawler):
    """Crawler for The Trade Vision global trade data"""
    
    def __init__(self, data_type: str = "import"):
        """
        Initialize crawler
        
        Args:
            data_type: Either "import" or "export"
        """
        self.base_url = "https://www.thetradevision.com"
        self.data_type = data_type
        
    @property
    def source_name(self) -> str:
        return f"The Trade Vision ({self.data_type.title()})"
    
    def _format_query_for_url(self, query: str) -> str:
        """Format query for URL: replace spaces with hyphens, lowercase"""
        return query.lower().replace(' ', '-')
    
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """
        Search The Trade Vision for HS codes across all countries
        
        URL format: https://www.thetradevision.com/global/{query}-{import/export}-data
        """
        logger.info(f"Searching The Trade Vision ({self.data_type}) for: {query}")
        
        formatted_query = self._format_query_for_url(query)
        search_url = f"{self.base_url}/global/{formatted_query}-{self.data_type}-data"
        
        hs_codes_list: List[str] = []  # Changed to list to track duplicates
        
        try:
            # Add headers and proxy to match working curl command
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Proxy configuration (httpx uses 'proxy' parameter)
            proxy_url = 'http://Kshxu21s:NWsAmu8jYK@77.47.159.51:50100'
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers, proxy=proxy_url) as client:
                response = await client.get(search_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all table rows in the results
                # Each row has: Date (td.FULL_DISCRIPTIONs), HS Code (td.FULL_DISCRIPTIONs), Description (td.FULL_DISCRIPTION)
                # We need to extract HS codes from the second column
                
                # Find all tables with tbody
                tables = soup.find_all('table', class_='table')
                
                for table in tables:
                    tbody = table.find('tbody')
                    if not tbody:
                        continue
                    
                    rows = tbody.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td', class_='FULL_DISCRIPTIONs')
                        # Typically: [0] = Date, [1] = HS Code
                        if len(cells) >= 2:
                            hs_code_text = cells[1].get_text(strip=True)
                            if hs_code_text.isdigit():
                                hs_codes_list.append(hs_code_text)
                
                logger.info(f"Found {len(hs_codes_list)} total HS codes ({len(set(hs_codes_list))} unique) from The Trade Vision")
                
        except Exception as e:
            logger.error(f"Error crawling The Trade Vision: {e}")
        
        # Calculate count and percentage for each HS code
        total_count = len(hs_codes_list)
        hs_code_counter = Counter(hs_codes_list)
        
        # Convert to list of HSCodeResult objects with count and percentage
        # Sort by count (descending), then by hs_code (ascending) for ties
        hs_codes = []
        for code, count in hs_code_counter.most_common():
            percentage = round((count / total_count * 100), 2) if total_count > 0 else 0.0
            hs_codes.append(HSCodeResult(
                hs_code=code,
                count=count,
                percentage=percentage
            ))
        
        return HSCodeDatabaseResult(
            source=self.source_name,
            source_url=self.base_url,
            query=query,
            hs_codes=hs_codes,
            result_url=search_url,
            total_count=total_count
        )


class TradeVisionImportCrawler(TradeVisionCrawler):
    """Crawler for The Trade Vision import data"""
    
    def __init__(self):
        super().__init__(data_type="import")


class TradeVisionExportCrawler(TradeVisionCrawler):
    """Crawler for The Trade Vision export data"""
    
    def __init__(self):
        super().__init__(data_type="export")
