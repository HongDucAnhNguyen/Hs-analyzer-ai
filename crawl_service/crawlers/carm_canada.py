"""Crawler for CARM Canada National Rulings
Website: https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings
"""

import logging
from typing import List
from datetime import datetime
import httpx

from crawl_service.crawlers.base import BaseCrawler
from crawl_service.core.models import RulingResult

logger = logging.getLogger(__name__)


class CARMCanadaCrawler(BaseCrawler):
    """Crawler for CARM Canada national rulings"""
    
    BASE_API_URL = "https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/carmwebservices/v2/carm/publicrulings"
    
    def __init__(self):
        super().__init__()
        self.source_name = "CAN - Tariff Classification Decisions"
        self.source_url = "https://www.cbsa-asfc.gc.ca/recourse-recours/decisions-eng.html#citt-tcce"
    
    async def search(self, query: str, max_results: int = 10) -> List[RulingResult]:
        """Search CARM Canada national rulings"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Fetch the list of all rulings
                list_url = f"{self.BASE_API_URL}/list?lang=en&curr=CAD"
                logger.info(f"Fetching CARM rulings list: {list_url}")
                
                response = await client.get(list_url)
                response.raise_for_status()
                
                rulings_data = response.json()
                
                # Handle different response formats
                if isinstance(rulings_data, list):
                    rulings_list = rulings_data
                elif isinstance(rulings_data, dict) and 'rulings' in rulings_data:
                    rulings_list = rulings_data['rulings']
                else:
                    logger.warning(f"Unexpected CARM response format: {type(rulings_data)}")
                    rulings_list = []
                
                logger.info(f"Found {len(rulings_list)} total rulings in CARM")
                
                query_lower = query.lower()
                temp_results = []
                
                # Filter rulings by query
                for ruling in rulings_list:
                    product = ruling.get('product', '')
                    classification = ruling.get('classificationNumber', '')
                    ruling_type = ruling.get('type', '')
                    
                    # Check if query matches product or classification
                    search_text = f"{product} {classification}".lower()
                    if query_lower not in search_text:
                        continue
                    
                    # Filter by type: must contain "Tariff"
                    if 'tariff' not in ruling_type.lower():
                        continue
                    
                    rulings_id = ruling.get('rulingsId')
                    if not rulings_id:
                        continue
                    
                    # Filter by date: only rulings from 2012 onwards
                    date_str = ruling.get('date', '')
                    if not date_str:
                        continue
                    
                    try:
                        # Parse date like "2025-08-01"
                        ruling_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if ruling_date.year < 2012:
                            continue
                    except ValueError as e:
                        logger.warning(f"Could not parse ruling date '{date_str}' for {rulings_id}: {e}")
                        continue
                    
                    # Fetch detailed ruling information
                    try:
                        ruling_details = await self._fetch_ruling_details(client, rulings_id)
                        
                        # Extract content from details
                        content = self._format_ruling_content(ruling_details)
                        
                        temp_results.append({
                            "rulings_id": rulings_id,
                            "product": product,
                            "content": content,
                            "ruling_date": ruling_date,
                            "classification_number": classification,
                            "ruling_type": ruling_type,
                            "details": ruling_details
                        })
                        
                    except Exception as e:
                        logger.error(f"Error fetching ruling details {rulings_id}: {e}")
                        continue
                
                # Sort by date (most recent first)
                temp_results.sort(key=lambda x: x["ruling_date"], reverse=True)
                
                # Create RulingResult objects from sorted and filtered results
                for item in temp_results[:max_results]:
                    # Extract tariffs from classification number
                    tariffs = []
                    if item["classification_number"]:
                        tariffs.append(item["classification_number"])
                    
                    results.append(RulingResult(
                        source=self.source_name,
                        source_url=self.source_url,
                        ruling_id=item["rulings_id"],
                        title=item["product"],
                        content=item["content"],
                        url=f"https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings/{item['rulings_id']}",
                        tariffs=tariffs,
                        metadata={
                            "classification_number": item["classification_number"],
                            "date": item["ruling_date"].strftime("%Y-%m-%d"),
                            "type": item["ruling_type"],
                            "details": item["details"]
                        }
                    ))
                
                logger.info(f"CARM Canada: Found {len(results)} results for query '{query}' (filtered: type contains 'Tariff', from 2012 onwards)")
                
        except Exception as e:
            logger.error(f"Error crawling CARM Canada: {e}")
            raise
        
        return results
    
    async def _fetch_ruling_details(self, client: httpx.AsyncClient, rulings_id: str) -> dict:
        """Fetch detailed information for a specific ruling"""
        details_url = f"{self.BASE_API_URL}/rulingsdetails/{rulings_id}?lang=en"
        response = await client.get(details_url)
        response.raise_for_status()
        return response.json()
    
    def _format_ruling_content(self, details: dict) -> str:
        """Format ruling details into readable content"""
        content_parts = []
        
        # Header information
        if details.get('product'):
            content_parts.append(f"Product: {details['product']}")
        
        if details.get('classificationNumber'):
            content_parts.append(f"Classification Number: {details['classificationNumber']}")
        
        if details.get('date'):
            content_parts.append(f"Date: {details['date']}")
        
        if details.get('type'):
            content_parts.append(f"Type: {details['type']}")
        
        # Applicant information
        if details.get('applicant'):
            applicant_text = details['applicant'].replace('&&', '\n').strip()
            content_parts.append(f"\nApplicant:\n{applicant_text}")
        
        # Introduction
        if details.get('introduction'):
            intro_text = details['introduction'].replace('&&', '\n').strip()
            content_parts.append(f"\nIntroduction:\n{intro_text}")
        
        # Product Description
        if details.get('productDescription'):
            desc_text = details['productDescription'].replace('&&', '\n').strip()
            content_parts.append(f"\nProduct Description:\n{desc_text}")
        
        # Analysis and Justification
        if details.get('analysis'):
            analysis_text = details['analysis'].replace('&&', '\n').strip()
            content_parts.append(f"\nAnalysis and Justification:\n{analysis_text}")
        
        # Decision
        if details.get('decision'):
            decision_text = details['decision'].replace('&&', '\n').strip()
            content_parts.append(f"\nDecision:\n{decision_text}")
        
        # Legislative/Administrative References
        if details.get('reference'):
            ref_text = details['reference'].replace('&&', '\n').strip()
            content_parts.append(f"\nLegislative/Administrative References:\n{ref_text}")
        
        # Consent
        if details.get('consent'):
            consent_text = details['consent'].replace('&&', '\n').strip()
            content_parts.append(f"\nConsent to Public Release:\n{consent_text}")
        
        # CBSA Contact
        if details.get('cbsaContact'):
            contact_text = details['cbsaContact'].replace('&&', '\n').strip()
            content_parts.append(f"\nCBSA Contact:\n{contact_text}")
        
        # External Reference / File Number
        if details.get('externalReference'):
            content_parts.append(f"\nFile Number: {details['externalReference']}")
        
        return '\n\n'.join(content_parts)
