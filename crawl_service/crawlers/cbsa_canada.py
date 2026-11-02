"""Crawler for CBSA Canada Trade Decisions
Website: https://www.cbsa-asfc.gc.ca/recourse-recours/decisions-eng.html
"""

import re
import logging
from typing import List
from datetime import datetime
from bs4 import BeautifulSoup
import httpx

from crawl_service.crawlers.base import BaseCrawler
from crawl_service.core.models import RulingResult

logger = logging.getLogger(__name__)


class CBSACanadaCrawler(BaseCrawler):
    """Crawler for CBSA Canada trade decisions"""
    
    BASE_URL = "https://www.cbsa-asfc.gc.ca/recourse-recours/decisions-eng.html"
    
    def __init__(self):
        super().__init__()
        self.source_name = "CAN - CBSA Rulings"
        self.source_url = "https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings"
    
    async def search(self, query: str, max_results: int = 10) -> List[RulingResult]:
        """Search CBSA Canada decisions"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Fetch the main decisions page
                logger.info(f"Fetching CBSA decisions page: {self.BASE_URL}")
                response = await client.get(self.BASE_URL)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all tables with trade decisions
                tables = soup.find_all('table', class_='table')
                logger.info(f"Found {len(tables)} tables on the page")
                
                query_lower = query.lower()
                temp_results = []
                
                # Parse each table
                for table in tables:
                    # Get table headers to find date column index
                    header_row = table.find('tr')
                    if not header_row:
                        continue
                    
                    headers = [th.get_text(strip=True) for th in header_row.find_all('th')]
                    
                    # Find the decision date column (it can have different prefixes)
                    date_col_index = -1
                    for idx, header in enumerate(headers):
                        if 'decision date' in header.lower():
                            date_col_index = idx
                            break
                    
                    rows = table.find_all('tr')[1:]  # Skip header row
                    
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) < 6:
                            continue
                        
                        # Extract row information
                        file_number_cell = cells[0]
                        appellant = cells[1].get_text(strip=True)
                        commodity = cells[2].get_text(strip=True)
                        program_type = cells[3].get_text(strip=True)
                        outcome = cells[4].get_text(strip=True)
                        
                        # Filter by program_type: must contain "Tariff"
                        if 'tariff' not in program_type.lower():
                            continue
                        
                        # Get date from appropriate column
                        date_str = ""
                        try:
                            if date_col_index >= 0 and date_col_index < len(cells):
                                date_str = cells[date_col_index].get_text(strip=True)
                            elif len(cells) > 5:
                                date_str = cells[5].get_text(strip=True)
                        except (IndexError, AttributeError) as e:
                            logger.warning(f"Error extracting date from row: {e}")
                            continue
                        
                        # Parse and filter by date: only from 2012 onwards
                        decision_date = None
                        if date_str:
                            try:
                                # Try different date formats
                                for date_format in ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"]:
                                    try:
                                        decision_date = datetime.strptime(date_str, date_format)
                                        break
                                    except ValueError:
                                        continue
                                
                                if not decision_date:
                                    logger.warning(f"Could not parse date '{date_str}'")
                                    continue
                                
                                if decision_date.year < 2012:
                                    continue
                            except Exception as e:
                                logger.warning(f"Error parsing date '{date_str}': {e}")
                                continue
                        else:
                            continue
                        
                        # Check if this row matches the query
                        row_text = f"{appellant} {commodity} {program_type}".lower()
                        if query_lower not in row_text:
                            continue
                        
                        # Get the ruling URL
                        link = file_number_cell.find('a')
                        if not link or not link.get('href'):
                            continue
                        
                        ruling_url = link['href']
                        file_number = link.get_text(strip=True)
                        
                        # Add iframe=true parameter to get full content
                        if '?' in ruling_url:
                            ruling_url_full = f"{ruling_url}&iframe=true"
                        else:
                            ruling_url_full = f"{ruling_url}?iframe=true"
                        
                        # Fetch the detailed ruling content
                        try:
                            ruling_content, tariffs = await self._fetch_ruling_content(client, ruling_url_full)
                            
                            temp_results.append({
                                "file_number": file_number,
                                "commodity": commodity,
                                "appellant": appellant,
                                "content": ruling_content,
                                "url": ruling_url,
                                "program_type": program_type,
                                "outcome": outcome,
                                "decision_date": decision_date,
                                "tariffs": tariffs
                            })
                            
                        except Exception as e:
                            logger.error(f"Error fetching ruling {file_number}: {e}")
                            continue
                
                # Sort by date (most recent first)
                temp_results.sort(key=lambda x: x["decision_date"], reverse=True)
                
                # Create RulingResult objects from sorted and filtered results
                for item in temp_results[:max_results]:
                    results.append(RulingResult(
                        source=self.source_name,
                        source_url=self.source_url,
                        ruling_id=item["file_number"],
                        title=f"{item['commodity']} - {item['appellant']}",
                        content=item["content"],
                        url=item["url"],
                        tariffs=item.get("tariffs", []),
                        metadata={
                            "appellant": item["appellant"],
                            "commodity": item["commodity"],
                            "program_type": item["program_type"],
                            "outcome": item["outcome"],
                            "date": item["decision_date"].strftime("%Y-%m-%d")
                        }
                    ))
                
                logger.info(f"CBSA Canada: Found {len(results)} results for query '{query}' (filtered: program type contains 'Tariff', from 2012 onwards)")
                
        except Exception as e:
            logger.error(f"Error crawling CBSA Canada: {e}")
            raise
        
        return results
    
    async def _fetch_ruling_content(self, client: httpx.AsyncClient, url: str) -> tuple[str, list[str]]:
        """Fetch the full content of a ruling and extract tariff codes
        
        Returns:
            tuple: (content string, list of tariff codes)
        """
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove scripts, styles, navigation, and other non-content elements
            for element in soup(["script", "style", "nav", "header", "footer", "iframe", "noscript"]):
                element.decompose()
            
            # Try to find the main document content
            # The actual decision text is in class="documentcontent"
            main_content = soup.find('div', class_='documentcontent')
            
            # If not found, try other content containers
            if not main_content:
                main_content = soup.find('div', class_='decisia-content')
            if not main_content:
                main_content = soup.find('body')
            if not main_content:
                main_content = soup
            
            # Extract all text content
            text = main_content.get_text(separator='\n', strip=True)
            
            # Clean up excessive whitespace and newlines
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 newlines
            text = re.sub(r' +', ' ', text)  # Remove multiple spaces
            text = re.sub(r'\t+', ' ', text)  # Remove tabs
            
            # Extract tariff codes from content
            tariffs = self._extract_tariffs_from_content(text)
            
            return text.strip(), tariffs
        except Exception as e:
            logger.error(f"Error fetching ruling content from {url}: {e}")
            return f"Error fetching content: {str(e)}", []
    
    def _extract_tariffs_from_content(self, content: str) -> list[str]:
        """Extract HS/tariff codes from ruling content
        
        CBSA tariff codes typically appear as:
        - 8471.30.00 (with dots)
        - 8471.30 (4-6 digit format)
        - tariff item 8471.30.00
        - classification 8471.30.00
        - HS code 847130
        """
        tariffs = set()
        
        # Pattern 1: Standard HS code format with dots (e.g., 8471.30.00, 8471.30, 8471.30.00.00)
        # Must start with 4 digits, then optional .XX groups
        pattern1 = re.compile(r'\b(\d{4}\.\d{2}(?:\.\d{2}){0,2})\b')
        
        # Pattern 2: Compact 6-10 digit codes (e.g., 847130, 8471300000)
        # Avoid matching years like 2012, 2025 or simple numbers
        pattern2 = re.compile(r'\b(\d{6,10})\b')
        
        # Pattern 3: Look for codes near keywords
        pattern3 = re.compile(
            r'(?:tariff\s*(?:item|code|heading|classification)?|classification|HS\s*code|heading)\s*[:\s]*(\d{4}(?:\.\d{2}){1,2})',
            re.IGNORECASE
        )
        
        # Extract using pattern 1 (dotted format)
        for match in pattern1.finditer(content):
            code = match.group(1)
            tariffs.add(code)
        
        # Extract using pattern 3 (keyword-based)
        for match in pattern3.finditer(content):
            code = match.group(1)
            tariffs.add(code)
        
        # Extract using pattern 2 (compact format) - only valid looking HS codes
        for match in pattern2.finditer(content):
            code = match.group(1)
            # Skip if it looks like a year (19XX, 20XX) or too short
            if len(code) >= 6 and not code.startswith(('19', '20')):
                # Validate: first 2 digits should be valid HS chapter (01-99)
                chapter = int(code[:2])
                if 1 <= chapter <= 99:
                    tariffs.add(code)
        
        # Convert to sorted list
        return sorted(list(tariffs))
