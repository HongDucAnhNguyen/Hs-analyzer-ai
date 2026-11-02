"""UK Trade Tariff Service crawler"""

import logging
import httpx
from bs4 import BeautifulSoup
from typing import List
from .base import HSCodeDatabaseCrawler, HSCodeDatabaseResult, HSCodeResult

logger = logging.getLogger(__name__)


class UKTradeTariffCrawler(HSCodeDatabaseCrawler):
    """Crawler for UK Trade Tariff Service"""
    
    def __init__(self):
        self.base_url = "https://www.trade-tariff.service.gov.uk"
        
    @property
    def source_name(self) -> str:
        return "UK Integrated Online Tariff"

    @property
    def source_url(self) -> str:
        return "https://www.trade-tariff.service.gov.uk/a-z-index/a"
    
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """Search UK Trade Tariff for HS codes"""
        logger.info(f"Searching UK Trade Tariff for: {query}")
        
        search_url = f"{self.base_url}/search?q={query}"
        hs_codes = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(search_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Helper function to extract HS codes from a table
                def extract_from_table(table_element) -> List[HSCodeResult]:
                    results = []
                    if not table_element:
                        return results
                    
                    tbody = table_element.find('tbody')
                    if not tbody:
                        return results
                    
                    rows = tbody.find_all('tr', class_='govuk-table__row')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            # First cell contains the link
                            link_cell = cells[0]
                            code_cell = cells[1]
                            
                            link_tag = link_cell.find('a')
                            if link_tag:
                                href = link_tag.get('href', '')
                                description = link_tag.get_text(strip=True)
                                
                                # Extract HS code from the code cell
                                # The code is in multiple divs with class 'code-text'
                                code_texts = code_cell.find_all('div', class_='code-text')
                                hs_code = ''.join([div.get_text(strip=True) for div in code_texts])
                                
                                if hs_code:
                                    full_url = f"{self.base_url}{href}" if href.startswith('/') else href
                                    
                                    results.append(HSCodeResult(
                                        hs_code=hs_code,
                                        count=1,  # Each HS code appears once in search results
                                        description=description,
                                        url=full_url
                                    ))
                    return results
                
                # Find the "Best commodity matches" table
                best_caption = soup.find('caption', string=lambda text: text and 'Best commodity matches' in text)
                if best_caption:
                    table = best_caption.find_parent('table')
                    hs_codes.extend(extract_from_table(table))
                
                # Also find "Other results" table (contains 4-digit Heading codes)
                other_caption = soup.find('caption', string=lambda text: text and 'Other results' in text)
                if other_caption:
                    other_table = other_caption.find_parent('table')
                    hs_codes.extend(extract_from_table(other_table))
                
                # Calculate percentage for each HS code
                total_count = len(hs_codes)
                if total_count > 0:
                    for hs_code_result in hs_codes:
                        hs_code_result.percentage = round((1 / total_count) * 100, 2)
                
                logger.info(f"Found {len(hs_codes)} HS codes from UK Trade Tariff")
                
        except Exception as e:
            logger.error(f"Error crawling UK Trade Tariff: {e}")
        
        return HSCodeDatabaseResult(
            source=self.source_name,
            source_url=self.source_url,
            query=query,
            hs_codes=hs_codes,
            result_url=search_url,
            total_count=len(hs_codes)
        )
