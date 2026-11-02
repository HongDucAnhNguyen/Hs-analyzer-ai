"""Crawler for UK HMRC Advance Tariff Rulings
Website: https://www.tax.service.gov.uk/search-for-advance-tariff-rulings
"""

import re
import logging
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import httpx

from crawl_service.crawlers.base import BaseCrawler
from crawl_service.core.models import RulingResult

logger = logging.getLogger(__name__)


class UKHMRCCrawler(BaseCrawler):
    """Crawler for UK HMRC advance tariff rulings"""
    
    BASE_URL = "https://www.tax.service.gov.uk/search-for-advance-tariff-rulings"
    
    def __init__(self):
        super().__init__()
        self.source_name = "UK Advance Tariff Rulings"
        self.source_url = "https://www.tax.service.gov.uk/search-for-advance-tariff-rulings/search?enableTrackingConsent=true"
    
    async def search(self, query: str, max_results: int = 10) -> List[RulingResult]:
        """Search UK HMRC advance tariff rulings"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # First, get the main page to obtain CSRF token
                main_page_url = f"{self.BASE_URL}/search?enableTrackingConsent=true"
                logger.info(f"Fetching UK HMRC search page: {main_page_url}")
                
                # Perform search
                search_url = f"{self.BASE_URL}/search"
                params = {
                    "query": query,
                    "enableTrackingConsent": "true"
                }
                
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all ruling links
                ruling_links = soup.find_all('a', href=re.compile(r'/search-for-advance-tariff-rulings/ruling/\d+'))
                logger.info(f"Found {len(ruling_links)} ruling links on search results page")
                
                # Extract ruling IDs and fetch details with date filtering
                seen_ruling_ids = set()
                temp_results = []
                
                for link in ruling_links:
                    href = link.get('href')
                    if not href:
                        continue
                    
                    # Extract ruling ID from URL
                    match = re.search(r'/ruling/(\d+)', href)
                    if not match:
                        continue
                    
                    ruling_id = match.group(1)
                    
                    # Skip if already processed
                    if ruling_id in seen_ruling_ids:
                        continue
                    seen_ruling_ids.add(ruling_id)
                    
                    # Get the title text
                    title = link.get_text(strip=True)
                    
                    # Fetch the ruling content and start date
                    try:
                        ruling_url = f"{self.BASE_URL}/ruling/{ruling_id}"
                        ruling_content, start_date, tariffs = await self._fetch_ruling_content(client, ruling_url, ruling_id)
                        
                        # Filter by date: only include rulings from 2012 onwards
                        if start_date and start_date.year >= 2012:
                            temp_results.append({
                                "ruling_id": ruling_id,
                                "title": title or f"Ruling {ruling_id}",
                                "content": ruling_content,
                                "url": ruling_url,
                                "start_date": start_date,
                                "tariffs": tariffs
                            })
                    except Exception as e:
                        logger.error(f"Error fetching ruling {ruling_id}: {e}")
                        continue
                
                # Sort by date (most recent first)
                temp_results.sort(key=lambda x: x["start_date"], reverse=True)
                
                # Create RulingResult objects from sorted results
                for item in temp_results[:max_results]:
                    results.append(RulingResult(
                        source=self.source_name,
                        source_url=self.source_url,
                        ruling_id=item["ruling_id"],
                        title=item["title"],
                        content=item["content"],
                        url=item["url"],
                        tariffs=item.get("tariffs", []),
                        metadata={
                            "query": query,
                            "start_date": item["start_date"].strftime("%d %b %Y")
                        }
                    ))
                
                logger.info(f"UK HMRC: Found {len(results)} results for query '{query}' (filtered from 2012 onwards)")
                
        except Exception as e:
            logger.error(f"Error crawling UK HMRC: {e}")
            raise
        
        return results
    
    async def _fetch_ruling_content(self, client: httpx.AsyncClient, url: str, ruling_id: str) -> tuple[str, Optional[datetime], list[str]]:
        """Fetch the full content of a ruling, extract start date and commodity codes
        
        Returns:
            tuple: (content string, start_date datetime object or None, list of tariff codes)
        """
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract start date and commodity code from summary list
            start_date = None
            tariffs = []
            
            dl_elements = soup.find_all('dl', class_='govuk-summary-list')
            for dl in dl_elements:
                rows = dl.find_all('div', class_='govuk-summary-list__row')
                for row in rows:
                    key = row.find('dt', class_='govuk-summary-list__key')
                    value = row.find('dd', class_='govuk-summary-list__value')
                    if key and value:
                        key_text = key.get_text(strip=True).lower()
                        value_text = value.get_text(strip=True)
                        
                        # Extract start date
                        if 'start date' in key_text:
                            try:
                                # Parse date like "18 Dec 2025"
                                start_date = datetime.strptime(value_text, "%d %b %Y")
                                logger.debug(f"Parsed start date for ruling {ruling_id}: {start_date}")
                            except ValueError as ve:
                                logger.warning(f"Could not parse start date '{value_text}' for ruling {ruling_id}: {ve}")
                        
                        # Extract commodity code (UK uses "Commodity code" field)
                        if 'commodity code' in key_text or 'tariff' in key_text:
                            # UK commodity codes are typically 10 digits, but extract any valid codes
                            extracted_codes = self._extract_tariffs_from_text(value_text)
                            tariffs.extend(extracted_codes)
            
            # Also try to extract tariffs from the full content
            text_content = soup.get_text()
            additional_tariffs = self._extract_tariffs_from_text(text_content)
            for code in additional_tariffs:
                if code not in tariffs:
                    tariffs.append(code)
            
            # Remove scripts, styles, navigation, etc.
            for element in soup(["script", "style", "nav", "header", "footer", "form"]):
                element.decompose()
            
            # Try to find the main content area
            main_content = soup.find('main') or soup.find('div', class_='govuk-main-wrapper') or soup
            
            # Extract text content
            text = main_content.get_text(separator='\n', strip=True)
            
            # Clean up multiple newlines
            text = re.sub(r'\n\s*\n', '\n\n', text)
            
            # Extract specific fields if available
            content_parts = [f"Ruling ID: {ruling_id}\n"]
            
            # Look for key-value pairs in the content
            dl_elements = main_content.find_all('dl', class_='govuk-summary-list')
            for dl in dl_elements:
                rows = dl.find_all('div', class_='govuk-summary-list__row')
                for row in rows:
                    key = row.find('dt', class_='govuk-summary-list__key')
                    value = row.find('dd', class_='govuk-summary-list__value')
                    if key and value:
                        content_parts.append(f"{key.get_text(strip=True)}: {value.get_text(strip=True)}")
            
            if len(content_parts) > 1:
                content_parts.append(f"\n{text}")
                return '\n'.join(content_parts), start_date, tariffs
            else:
                return text, start_date, tariffs
            
        except Exception as e:
            logger.error(f"Error fetching ruling content from {url}: {e}")
            return f"Error fetching content: {str(e)}", None, []
    
    def _extract_tariffs_from_text(self, text: str) -> list[str]:
        """Extract HS/commodity codes from text
        
        UK commodity codes typically appear as:
        - 10 digits (e.g., 8471300000)
        - 8 digits (e.g., 84713000)  
        - Dotted format (e.g., 8471.30.00.00 or 8471.30.00)
        """
        tariffs = set()
        
        # Pattern 1: Standard dotted format (e.g., 8471.30.00, 8471.30.00.00)
        pattern1 = re.compile(r'\b(\d{4}\.\d{2}(?:\.\d{2}){1,2})\b')
        
        # Pattern 2: Compact 8-10 digit codes (UK full commodity codes)
        pattern2 = re.compile(r'\b(\d{8,10})\b')
        
        # Extract using pattern 1 (dotted format)
        for match in pattern1.finditer(text):
            code = match.group(1)
            tariffs.add(code)
        
        # Extract using pattern 2 (compact format)
        for match in pattern2.finditer(text):
            code = match.group(1)
            # Skip if it looks like a year or other non-HS number
            if not code.startswith(('19', '20')):
                # Validate: first 2 digits should be valid HS chapter (01-99)
                chapter = int(code[:2])
                if 1 <= chapter <= 99:
                    tariffs.add(code)
        
        return sorted(list(tariffs))
