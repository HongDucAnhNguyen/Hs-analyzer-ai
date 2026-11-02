"""Direct Botasaurus integration for Zauba searches - no PM2 needed"""

import logging
from typing import Dict, List, Optional
from botasaurus.browser import browser, Driver
from botasaurus_driver.exceptions import CloudflareDetectionException
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Browser Configuration - Optimized for Docker
# ============================================================================

# ============================================================================
# Browser Configuration - Optimized for Docker
# ============================================================================

# Browser configs for Docker environment - Using headless=True for stability
# headless=False causes Chrome crashes in Docker without proper GPU support
BROWSER_CONFIG_USA = {
    'headless': True,  # Stable in Docker (headless=False causes crashes)
    'block_images': True,
    'max_retry': 3,
    'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'add_arguments': [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-dev-shm-usage',
    ]
}

BROWSER_CONFIG_USA_FACETS = {
    'headless': True,
    'block_images': True,
    'max_retry': 3,
    'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'add_arguments': [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-dev-shm-usage',
    ]
}

BROWSER_CONFIG_SHIPMENT = {
    'headless': True,  # Stable in Docker (headless=False causes crashes)
    'block_images': True,
    'max_retry': 3,
    'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'add_arguments': [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-dev-shm-usage',
    ]
}


# ============================================================================
# Zauba USA Imports Search (WEB2)
# ============================================================================

@browser(**BROWSER_CONFIG_USA)
def _search_zauba_usa_internal(driver: Driver, query: str) -> Dict:
    """
    Internal function: Search Zauba USA Imports
    
    Navigates to https://www.zauba.com/USA-imports-exports/Imports
    Submits search and returns result URL with code
    
    Args:
        driver: Botasaurus Driver instance
        query: Search term (e.g., "projector")
    
    Returns:
        dict with 'success', 'result_url', 'url_code', 'error'
    """
    search_page = "https://www.zauba.com/USA-imports-exports/Imports"
    
    logger.info(f"[Zauba USA] Searching for: {query}")
    
    try:
        # Step 1: Navigate with Cloudflare bypass
        logger.info("[Zauba USA] Navigating to search page...")
        try:
            driver.google_get(search_page, bypass_cloudflare=True)
        except Exception as e:
            logger.warning(f"[Zauba USA] Bypass warning: {e}")
            driver.sleep(5)
        
        driver.sleep(10)
        
        # Check if passed Cloudflare
        if "Just a moment" in driver.title:
            # Try manual bypass
            logger.warning("[Zauba USA] Cloudflare detected, attempting bypass...")
            for attempt in range(3):
                try:
                    driver.detect_and_bypass_cloudflare()
                    driver.sleep(10)
                    if "Just a moment" not in driver.title:
                        break
                except CloudflareDetectionException:
                    driver.sleep(10)
            
            # Still blocked?
            if "Just a moment" in driver.title:
                raise Exception("Cloudflare blocked after multiple attempts")
        
        logger.info("[Zauba USA] Passed Cloudflare, submitting search...")
        
        # Step 2: Submit search
        driver.run_js(f"""
            var input = document.querySelector('#search');
            if (input) {{
                input.value = '{query}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            var submit = document.querySelector('input[type="submit"]');
            if (submit) {{
                submit.click();
            }}
        """)
        
        driver.sleep(10)
        
        # Step 3: Handle Cloudflare on results page
        for attempt in range(2):
            if "Just a moment" in driver.title:
                logger.warning(f"[Zauba USA] Cloudflare on results page, attempt {attempt+1}...")
                try:
                    driver.detect_and_bypass_cloudflare()
                except:
                    pass
                driver.sleep(10)
            else:
                break
        
        driver.sleep(5)
        
        # Step 4: Extract result
        result_url = driver.current_url
        
        # Validate result
        if result_url == search_page or "Just a moment" in driver.title:
            raise Exception("Search failed or Cloudflare blocked")
        
        # Extract URL code
        url_code = None
        if '-import-data-' in result_url:
            url_code = result_url.split('-import-data-')[-1]
        elif '-export-data-' in result_url:
            url_code = result_url.split('-export-data-')[-1]
        
        logger.info(f"[Zauba USA] Success! URL: {result_url}, Code: {url_code}")
        
        return {
            'success': True,
            'result_url': result_url,
            'url_code': url_code,
            'query': query
        }
        
    except Exception as e:
        logger.error(f"[Zauba USA] Search failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'query': query
        }


@browser(**BROWSER_CONFIG_USA_FACETS)
def _scrape_zauba_facets_internal(driver: Driver, url_code: str, result_url: str = None) -> Dict:
    """
    Internal function: Scrape HS codes from Zauba USA result or facets page
    
    Args:
        driver: Botasaurus Driver instance
        url_code: URL code from search result (e.g., "a17erjm39b64")
        result_url: Full result URL (optional, used as fallback)
    
    Returns:
        dict with 'success', 'hscodes', 'total_records'
    """
    
    logger.info(f"[Zauba USA Facets] Scraping code: {url_code}")
    
    try:
        # Try the result URL first (has HS codes on the page)
        if result_url:
            scrape_url = result_url
            logger.info(f"[Zauba USA Facets] Using result URL: {scrape_url}")
        else:
            # Fallback to facets URL
            scrape_url = f"https://www.zauba.com/facets/import-data-{url_code}"
            logger.info(f"[Zauba USA Facets] Using facets URL: {scrape_url}")
        
        # Navigate with bypass
        try:
            driver.google_get(scrape_url, bypass_cloudflare=True)
        except Exception as e:
            logger.warning(f"[Zauba USA Facets] Bypass warning: {e}")
        
        driver.sleep(10)
        
        # Handle Cloudflare
        for attempt in range(3):
            if "Just a moment" in driver.title:
                logger.warning(f"[Zauba USA Facets] Cloudflare attempt {attempt+1}...")
                try:
                    driver.detect_and_bypass_cloudflare()
                except:
                    pass
                driver.sleep(10)
            else:
                break
        
        driver.sleep(5)
        
        # Get page HTML
        html = driver.page_html
        
        if "Just a moment" in driver.title:
            raise Exception("Cloudflare blocked facets page")
        
        logger.info(f"[Zauba USA Facets] Page loaded, title: {driver.title[:100]}")
        logger.info(f"[Zauba USA Facets] Page URL: {driver.current_url}")
        
        # Parse HS codes from the page
        soup = BeautifulSoup(html, 'html.parser')
        
        hscodes = []
        total_records = 0
        
        # Find all links that match HS code pattern
        all_links = soup.find_all('a', href=True)
        logger.info(f"[Zauba USA Facets] Found {len(all_links)} total links on page")
        
        # Debug: show some sample link texts
        sample_texts = [link.get_text(strip=True) for link in all_links[:10] if link.get_text(strip=True)]
        logger.info(f"[Zauba USA Facets] Sample link texts: {sample_texts}")
        
        for link in all_links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Match pattern: digits followed by count in parentheses
            # Example: "900890 (23,962)" or "853990 (1,793)"
            match = re.match(r'^(\d{4,10})\s*\(([0-9,]+)\)$', text)
            if match:
                hscode = match.group(1)
                count_str = match.group(2).replace(',', '')
                
                try:
                    count = int(count_str)
                    
                    hscodes.append({
                        'hscode': hscode,
                        'count': count,
                        'url': f"https://www.zauba.com{href}" if href.startswith('/') else href
                    })
                    
                    total_records += count
                except ValueError:
                    continue
        
        logger.info(f"[Zauba USA Facets] Parsed {len(hscodes)} HS codes")
        
        logger.info(f"[Zauba USA Facets] Parsed {len(hscodes)} HS codes")
        
        # Calculate percentages
        if total_records > 0:
            for item in hscodes:
                item['percentage'] = round((item['count'] / total_records) * 100, 2)
        else:
            for item in hscodes:
                item['percentage'] = 0.0
        
        logger.info(f"[Zauba USA Facets] Found {len(hscodes)} HS codes, total: {total_records:,}")
        
        return {
            'success': True,
            'hscodes': hscodes,
            'total_records': total_records
        }
        
    except Exception as e:
        logger.error(f"[Zauba USA Facets] Scraping failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'hscodes': [],
            'total_records': 0
        }


# ============================================================================
# Zauba Shipment Search (WEB3)
# ============================================================================

@browser(**BROWSER_CONFIG_SHIPMENT)
def _search_zauba_shipment_internal(driver: Driver, query: str) -> Dict:
    """
    Internal function: Search Zauba Shipment for HS codes
    
    Navigates to https://www.zauba.com/import-{query}-hs-code.html
    Parses HS codes directly from the page
    
    Args:
        driver: Botasaurus Driver instance
        query: Search term (e.g., "projector")
    
    Returns:
        dict with 'success', 'hs_codes', 'total_records', 'result_url'
    """
    # Format query for URL
    formatted_query = query.lower().replace(' ', '-')
    search_url = f"https://www.zauba.com/import-{formatted_query}-hs-code.html"
    
    logger.info(f"[Zauba Shipment] Searching: {search_url}")
    
    try:
        # Navigate with bypass
        try:
            driver.google_get(search_url, bypass_cloudflare=True)
        except Exception as e:
            logger.warning(f"[Zauba Shipment] Bypass warning: {e}")
        
        driver.sleep(10)
        
        # Handle Cloudflare
        for attempt in range(3):
            if "Just a moment" in driver.title:
                logger.warning(f"[Zauba Shipment] Cloudflare attempt {attempt+1}...")
                try:
                    driver.detect_and_bypass_cloudflare()
                except:
                    pass
                driver.sleep(10)
            else:
                break
        
        driver.sleep(5)
        
        # Get HTML
        html = driver.page_html
        
        if "Just a moment" in driver.title:
            raise Exception("Cloudflare blocked shipment page")
        
        logger.info(f"[Zauba Shipment] Page loaded, title: {driver.title[:100]}")
        
        # Parse HS codes from page - they appear as links with format "85299090(20,765)"
        soup = BeautifulSoup(html, 'html.parser')
        
        hs_codes = []
        total_records = 0
        
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
                
                try:
                    count = int(count_str)
                    
                    hs_codes.append({
                        'hs_code': hscode,
                        'count': count,
                        'url': f"https://www.zauba.com{href}" if href.startswith('/') else href
                    })
                    
                    total_records += count
                except ValueError:
                    continue
        
        logger.info(f"[Zauba Shipment] Parsed {len(hs_codes)} HS codes")
        
        # Calculate percentages
        if total_records > 0:
            for item in hs_codes:
                item['percentage'] = round((item['count'] / total_records) * 100, 2)
        else:
            for item in hs_codes:
                item['percentage'] = 0.0
        
        logger.info(f"[Zauba Shipment] Found {len(hs_codes)} HS codes, total: {total_records:,}")
        
        return {
            'success': True,
            'hs_codes': hs_codes,
            'total_records': total_records,
            'result_url': search_url
        }
        
    except Exception as e:
        logger.error(f"[Zauba Shipment] Search failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'hs_codes': [],
            'total_records': 0,
            'result_url': search_url
        }


# ============================================================================
# Public API Functions (synchronous wrappers for use in crawlers)
# ============================================================================

def search_zauba_usa(query: str) -> Dict:
    """
    Search Zauba USA Imports (synchronous function)
    
    Args:
        query: Search term
    
    Returns:
        dict with 'success', 'result_url', 'url_code'
    """
    return _search_zauba_usa_internal(query)


def scrape_zauba_usa_facets(url_code: str, result_url: str = None) -> Dict:
    """
    Scrape HS codes from Zauba USA result/facets page (synchronous function)
    
    Args:
        url_code: URL code from search result
        result_url: Full result URL (optional, used as primary source)
    
    Returns:
        dict with 'success', 'hscodes', 'total_records'
    """
    return _scrape_zauba_facets_internal(url_code, result_url)


def search_zauba_shipment(query: str) -> Dict:
    """
    Search Zauba Shipment for HS codes (synchronous function)
    
    Args:
        query: Search term
    
    Returns:
        dict with 'success', 'hs_codes', 'total_records', 'result_url'
    """
    return _search_zauba_shipment_internal(query)
