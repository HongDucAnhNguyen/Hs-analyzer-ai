"""Crawler for US Customs and Border Protection (CBP) Rulings
Website: https://rulings.cbp.gov/home
"""

import logging
from typing import List
from datetime import datetime
import httpx

from crawl_service.crawlers.base import BaseCrawler
from crawl_service.core.models import RulingResult

logger = logging.getLogger(__name__)


class USCBPCrawler(BaseCrawler):
    """Crawler for US CBP rulings"""
    
    BASE_API_URL = "https://rulings.cbp.gov/api"
    
    def __init__(self):
        super().__init__()
        self.source_name = "US CBP Ruling"
        self.source_url = "https://rulings.cbp.gov/home"
    
    async def search(self, query: str, max_results: int = 10) -> List[RulingResult]:
        """Search US CBP rulings"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for rulings
                search_url = f"{self.BASE_API_URL}/search"
                params = {
                    "term": query,
                    "collection": "ALL",
                    "commodityGrouping": "ALL",
                    "pageSize": 100,  # Fetch more to filter
                    "page": 1,
                    "sortBy": "RELEVANCE"
                }
                
                logger.info(f"Searching US CBP rulings with query: {query}")
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                search_results = response.json()
                rulings_list = search_results.get('rulings', [])
                logger.info(f"Found {len(rulings_list)} rulings from US CBP")
                
                # Filter and collect results
                temp_results = []
                
                for ruling in rulings_list:
                    ruling_number = ruling.get('rulingNumber')
                    if not ruling_number:
                        continue
                    
                    # Filter by categories = "Classification"
                    categories = ruling.get('categories', '')
                    if categories != 'Classification':
                        continue
                    
                    # Filter by date: only rulings from 2012 onwards
                    ruling_date_str = ruling.get('rulingDate', '')
                    if not ruling_date_str:
                        continue
                    
                    try:
                        # Parse date like "2008-07-17T00:00:00"
                        ruling_date = datetime.fromisoformat(ruling_date_str.replace('Z', '+00:00'))
                        if ruling_date.year < 2012:
                            continue
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Could not parse ruling date '{ruling_date_str}' for {ruling_number}: {e}")
                        continue
                    
                    try:
                        ruling_content = await self._fetch_ruling_content(client, ruling_number)
                        
                        temp_results.append({
                            "ruling_number": ruling_number,
                            "subject": ruling.get('subject', ''),
                            "content": ruling_content,
                            "ruling_date": ruling_date,
                            "categories": categories,
                            "tariffs": ruling.get('tariffs', []),
                            "collection": ruling.get('collection', ''),
                            "commodity_grouping": ruling.get('commodityGrouping'),
                            "is_usmca": ruling.get('isUsmca', False),
                            "is_nafta": ruling.get('isNafta', False)
                        })
                        
                    except Exception as e:
                        logger.error(f"Error fetching ruling {ruling_number}: {e}")
                        continue
                
                # Sort by date (most recent first)
                temp_results.sort(key=lambda x: x["ruling_date"], reverse=True)
                
                # Create RulingResult objects from sorted and filtered results
                for item in temp_results[:max_results]:
                    results.append(RulingResult(
                        source=self.source_name,
                        source_url=self.source_url,
                        ruling_id=item["ruling_number"],
                        title=item["subject"],
                        content=item["content"],
                        url=f"https://rulings.cbp.gov/ruling/{item['ruling_number']}",
                        tariffs=item["tariffs"],  # Include tariffs/HS codes directly
                        metadata={
                            "categories": item["categories"],
                            "ruling_date": item["ruling_date"].strftime("%Y-%m-%d"),
                            "tariffs": item["tariffs"],
                            "collection": item["collection"],
                            "commodity_grouping": item["commodity_grouping"],
                            "is_usmca": item["is_usmca"],
                            "is_nafta": item["is_nafta"],
                        }
                    ))
                
                logger.info(f"US CBP: Found {len(results)} results for query '{query}' (filtered: Classification category, from 2012 onwards)")
                
        except Exception as e:
            logger.error(f"Error crawling US CBP: {e}")
            raise
        
        return results
    
    async def _fetch_ruling_content(self, client: httpx.AsyncClient, ruling_number: str) -> str:
        """Fetch the full content of a ruling"""
        try:
            ruling_url = f"{self.BASE_API_URL}/ruling/{ruling_number}"
            response = await client.get(ruling_url)
            response.raise_for_status()
            
            ruling_data = response.json()
            
            # Format the ruling content
            content_parts = []
            
            if ruling_data.get('rulingNumber'):
                content_parts.append(f"Ruling Number: {ruling_data['rulingNumber']}")
            
            if ruling_data.get('subject'):
                content_parts.append(f"Subject: {ruling_data['subject']}")
            
            if ruling_data.get('description'):
                content_parts.append(f"\nDescription:\n{ruling_data['description']}")
            
            if ruling_data.get('dutifulText'):
                content_parts.append(f"\nDutiful Text:\n{ruling_data['dutifulText']}")
            
            if ruling_data.get('text'):
                content_parts.append(f"\nFull Text:\n{ruling_data['text']}")
            
            if ruling_data.get('tariffs'):
                tariffs = ', '.join(ruling_data['tariffs'])
                content_parts.append(f"\nTariff Classifications: {tariffs}")
            
            if ruling_data.get('rulingDate'):
                content_parts.append(f"\nRuling Date: {ruling_data['rulingDate']}")
            
            return '\n\n'.join(content_parts)
        except Exception as e:
            logger.error(f"Error fetching ruling content for {ruling_number}: {e}")
            return f"Error fetching content: {str(e)}"
