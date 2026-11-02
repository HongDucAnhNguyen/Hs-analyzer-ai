"""Orchestrator for HS Code Database searches"""

import logging
import asyncio
from typing import List, Set, Dict
from collections import defaultdict
import logfire
from crawl_service.core.models import ProductCrawlQuery, HSCodeDatabaseResponse, HSCodeQueryGroup, HSCodeSourceResult
from crawl_service.core.query_rewriter import rewrite_product_to_queries
from crawl_service.utils.shared_query_cache import shared_query_cache
from crawl_service.crawlers.hs_databases.uk_trade_tariff import UKTradeTariffCrawler
from crawl_service.crawlers.hs_databases.zauba_zendriver import ZaubaZendriverCombinedCrawler
from crawl_service.crawlers.hs_databases.tradevision import TradeVisionImportCrawler, TradeVisionExportCrawler

logger = logging.getLogger(__name__)


def normalize_hs_code(hs_code: str) -> str:
    """
    Normalize HS code to exactly 6 digits (international standard).
    Removes any non-digit characters, pads 4-digit codes with "00", and takes first 6 digits.
    
    Args:
        hs_code: Raw HS code string (e.g., "8471.30.01", "847130010000", "4802")
        
    Returns:
        Normalized 6-digit HS code (e.g., "847130", "480200")
    """
    # Remove all non-digit characters
    digits_only = ''.join(c for c in hs_code if c.isdigit())
    
    # Handle different code lengths:
    # - 4 digits (Heading level): pad with "00" to make 6 digits
    # - 6+ digits: take first 6 digits
    if len(digits_only) == 4:
        return digits_only + "00"
    elif len(digits_only) >= 6:
        return digits_only[:6]
    else:
        # For codes shorter than 4 digits, pad with zeros
        return digits_only.ljust(6, '0') if digits_only else ""


def aggregate_hs_codes(hs_codes: list) -> list:
    """
    Aggregate HS codes by normalized 6-digit code.
    Combines counts and keeps highest percentage/first description.
    
    Args:
        hs_codes: List of HSCodeResult objects
        
    Returns:
        List of aggregated HSCodeResult objects with normalized HS codes
    """
    from crawl_service.core.models import HSCodeResult as ModelHSCodeResult
    
    # Group by normalized HS code
    aggregated: Dict[str, Dict] = defaultdict(lambda: {
        'count': 0,
        'percentage': 0.0,
        'description': None,
        'url': None,
        'original_codes': []
    })
    
    for hs in hs_codes:
        normalized = normalize_hs_code(hs.hs_code)
        if not normalized:  # Skip empty codes
            continue
            
        agg = aggregated[normalized]
        agg['count'] += hs.count or 0
        agg['original_codes'].append(hs.hs_code)
        
        # Keep highest percentage
        if hs.percentage and (agg['percentage'] is None or hs.percentage > agg['percentage']):
            agg['percentage'] = hs.percentage
            
        # Keep first non-empty description
        if hs.description and not agg['description']:
            agg['description'] = hs.description
            
        # Keep first non-empty URL
        if hs.url and not agg['url']:
            agg['url'] = hs.url
    
    # Recalculate percentages based on total count
    total_count = sum(agg['count'] for agg in aggregated.values())
    
    # Convert back to HSCodeResult objects
    result = []
    for normalized_code, agg in aggregated.items():
        # Recalculate percentage if we have counts
        percentage = agg['percentage']
        if total_count > 0 and agg['count'] > 0:
            percentage = round((agg['count'] / total_count) * 100, 2)
        
        result.append(ModelHSCodeResult(
            hs_code=normalized_code,
            count=agg['count'] if agg['count'] > 0 else None,
            percentage=percentage if percentage else None,
            description=agg['description'],
            url=agg['url']
        ))
    
    # Sort by count (descending), then by HS code
    result.sort(key=lambda x: (-(x.count or 0), x.hs_code))
    
    return result


class HSCodeDatabaseOrchestrator:
    """Orchestrates HS code database searches across multiple sources"""
    
    def __init__(self):
        # Initialize all crawlers
        # Note: Using ZaubaZendriverCombinedCrawler (single session) instead of 
        # separate USA/Shipment crawlers to avoid Cloudflare blocking
        self.crawlers = [
            UKTradeTariffCrawler(),
            ZaubaZendriverCombinedCrawler(),
            TradeVisionImportCrawler(),
            TradeVisionExportCrawler(),
        ]
        
        # Get expanded source names (including individual sources from combined crawlers)
        all_sources = []
        for crawler in self.crawlers:
            if hasattr(crawler, 'source_names'):
                all_sources.extend(crawler.source_names)
            else:
                all_sources.append(crawler.source_name)
        
        logfire.info("🏗️ HS Database Orchestrator initialized",
                    crawler_count=len(self.crawlers),
                    source_count=len(all_sources),
                    sources=all_sources)
        logger.info(f"Initialized HS Database Orchestrator with {len(all_sources)} sources: {all_sources}")
    
    async def search_hs_codes(self, request: ProductCrawlQuery) -> HSCodeDatabaseResponse:
        """
        Search for HS codes across all databases using rewritten queries
        
        Args:
            request: ProductCrawlQuery with product information
            
        Returns:
            HSCodeDatabaseResponse with HS codes grouped by technical query
        """
        with logfire.span(
            "search_hs_codes",
            product_name=request.product_name,
            science_name=request.science_name or "",
            has_description=bool(request.product_description),
            has_function=bool(request.function),
            has_material=bool(request.material)
        ):
            logfire.info("🔍 Starting HS database search", 
                        product_name=request.product_name,
                        science_name=request.science_name or "")
            logger.info(f"Starting HS database search for product: {request.product_name}")
            
            # Convert request to dict for caching
            product_info = request.dict()
            
            # Step 1: Get or generate rewritten queries with distributed locking
            # This ensures consistent technical_name across concurrent /hs-ruling and /hs_database calls
            with logfire.span("get_rewritten_queries_with_lock"):
                logfire.info("🔍 Getting rewritten queries (with distributed lock if needed)")
                
                async def _generate_queries():
                    """Generator function for lock-aware cache"""
                    return await rewrite_product_to_queries(
                        product_name=request.product_name,
                        science_name=request.science_name or "",
                        product_description=request.product_description or "",
                        function=request.function or "",
                        material=request.material or "",
                        structure=request.structure or "",
                        specifications=request.specifications or ""
                    )
                
                try:
                    rewritten_queries, was_generated = await shared_query_cache.get_or_generate_queries(
                        product_info, _generate_queries
                    )
                    
                    if was_generated:
                        logfire.info("✅ Query rewriting completed (generated new)", 
                                    count=len(rewritten_queries),
                                    technical_queries=rewritten_queries)
                        logger.info(f"Generated new rewritten queries: {rewritten_queries}")
                    else:
                        logfire.info("✅ Using cached/shared rewritten queries", 
                                    count=len(rewritten_queries),
                                    technical_queries=rewritten_queries)
                        logger.info(f"Using cached/shared rewritten queries: {rewritten_queries}")
                        
                except Exception as e:
                    logfire.error("❌ Query rewriting failed", error=str(e))
                    logger.error(f"Error rewriting queries: {e}")
                    # Fallback to just product name
                    rewritten_queries = [request.product_name]
                    logfire.info("⚠️ Using fallback query", fallback=request.product_name)
            
            # Step 2: Search all databases for each rewritten query
            with logfire.span("parallel_hs_database_search", 
                            query_count=len(rewritten_queries),
                            source_count=len(self.crawlers),
                            total_tasks=len(rewritten_queries) * len(self.crawlers)):
                
                logfire.info("🔧 Preparing parallel HS database search tasks",
                            queries=rewritten_queries,
                            sources=[c.source_name for c in self.crawlers])
                
                query_groups = []
                all_hs_codes_set: Set[str] = set()
                errors = {}
                
                # Process each query sequentially to organize results properly
                for query in rewritten_queries:
                    with logfire.span(f"search_query_{query.replace(' ', '_')[:20]}", 
                                     query=query,
                                     source_count=len(self.crawlers)):
                        
                        logfire.info(f"🔍 Searching HS databases", 
                                    query=query,
                                    source_count=len(self.crawlers))
                        logger.info(f"Searching with technical query: {query}")
                        
                        # Search all sources with this query in parallel
                        sources = []
                        
                        # All crawlers can run in parallel
                        tasks = [self._search_with_error_handling(crawler, query) for crawler in self.crawlers]
                        crawl_results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # Flatten results (some crawlers return multiple results)
                        flattened_results = []
                        for crawler, result in zip(self.crawlers, crawl_results):
                            if isinstance(result, Exception):
                                flattened_results.append((crawler.source_name, result))
                            elif isinstance(result, list):
                                # Combined crawler returns list of results
                                for r in result:
                                    flattened_results.append((r.source, r))
                            else:
                                flattened_results.append((result.source, result))
                        
                        successful_searches = sum(1 for _, r in flattened_results if not isinstance(r, Exception))
                        failed_searches = sum(1 for _, r in flattened_results if isinstance(r, Exception))
                        
                        logfire.info(f"✅ Parallel search completed",
                                    query=query,
                                    total=len(flattened_results),
                                    successful=successful_searches,
                                    failed=failed_searches)
                        
                        for source_name, result in flattened_results:
                            if isinstance(result, Exception):
                                error_msg = str(result)
                                logfire.error(f"❌ HS database search failed",
                                            source=source_name,
                                            query=query,
                                            error=error_msg,
                                            error_type=type(result).__name__)
                                logger.error(f"Error from {source_name}: {error_msg}")
                                errors[source_name] = error_msg
                                continue
                            
                            # Convert HS codes from crawler model to orchestrator model
                            # Then normalize to 6-digit HS codes and aggregate
                            from crawl_service.core.models import HSCodeResult as ModelHSCodeResult
                            
                            # First convert to model format
                            raw_hs_codes = []
                            for hs_code in result.hs_codes:
                                raw_hs_codes.append(ModelHSCodeResult(
                                    hs_code=hs_code.hs_code,
                                    count=hs_code.count,
                                    percentage=hs_code.percentage,
                                    description=hs_code.description,
                                    url=hs_code.url
                                ))
                            
                            # Normalize to 6-digit and aggregate counts
                            converted_hs_codes = aggregate_hs_codes(raw_hs_codes)
                            
                            # Add normalized HS codes to the set
                            for hs in converted_hs_codes:
                                all_hs_codes_set.add(hs.hs_code)
                            
                            # Add source result
                            sources.append(HSCodeSourceResult(
                                source=result.source,
                                source_url=result.source_url,
                                query=result.query,
                                hs_codes=converted_hs_codes,
                                result_url=result.result_url,
                                total_count=result.total_count
                            ))
                            
                            logfire.info(f"📊 Retrieved HS codes",
                                        source=source_name,
                                        query=query,
                                        hs_codes_count=len(converted_hs_codes),
                                        top_hs_codes=[h.hs_code for h in converted_hs_codes[:3]])
                        
                        # Create query group
                        total_hs_codes_in_group = len(set(
                            hs.hs_code for source in sources for hs in source.hs_codes
                        ))
                        
                        query_groups.append(HSCodeQueryGroup(
                            technical_name=query,
                            sources=sources,
                            total_hs_codes=total_hs_codes_in_group
                        ))
                        
                        logfire.info(f"✅ Query group completed",
                                    query=query,
                                    unique_hs_codes=total_hs_codes_in_group,
                                    sources_with_results=len(sources))
            
            # Step 3: Build response
            with logfire.span("build_response"):
                # Get unique source names with search page URLs from actual results
                sources_queried = []
                seen_sources = set()
                
                # Collect source URLs from actual search results (use source_url which is the search page URL)
                for query_group in query_groups:
                    for source_result in query_group.sources:
                        if source_result.source not in seen_sources:
                            seen_sources.add(source_result.source)
                            sources_queried.append({
                                "source_name": source_result.source,
                                "source_url": source_result.source_url or ""
                            })
                
                response = HSCodeDatabaseResponse(
                    product_name=request.product_name,
                    rewritten_queries=rewritten_queries,
                    results=query_groups,
                    total_unique_hs_codes=len(all_hs_codes_set),
                    sources_queried=sources_queried,
                    errors=errors
                )
                
                logfire.info("🎉 HS database search completed successfully",
                            product_name=request.product_name,
                            total_unique_hs_codes=len(all_hs_codes_set),
                            query_groups_count=len(query_groups),
                            sources_queried=sources_queried,
                            has_errors=len(errors) > 0,
                            error_sources=list(errors.keys()) if errors else [])
                
                logger.info(f"HS database search complete. Found {len(all_hs_codes_set)} unique HS codes")
                
                return response
    
    async def _search_with_error_handling(self, crawler, query: str):
        """
        Search a single HS database with error handling and detailed logging
        
        Args:
            crawler: HS database crawler instance
            query: Search query
            
        Returns:
            HSCodeDatabaseSearchResponse, list of responses (for combined crawlers),
            or raises exception on error
        """
        source_name = crawler.source_name
        with logfire.span(f"search_{source_name.replace(' ', '_')}", 
                         source=source_name,
                         query=query):
            try:
                logfire.info(f"🔍 Starting HS database search",
                            source=source_name,
                            query=query)
                
                # Check if crawler has search_multiple method (combined crawler)
                if hasattr(crawler, 'search_multiple'):
                    results = await crawler.search_multiple(query)
                    
                    total_hs_codes = sum(len(r.hs_codes) for r in results)
                    source_names = [r.source for r in results]
                    
                    logfire.info(f"✅ HS database search completed (multiple sources)",
                                source=source_name,
                                query=query,
                                sources=source_names,
                                total_hs_codes=total_hs_codes)
                    
                    return results
                else:
                    result = await crawler.search(query)
                    
                    logfire.info(f"✅ HS database search completed",
                                source=source_name,
                                query=query,
                                hs_codes_count=len(result.hs_codes),
                                total_count=result.total_count,
                                top_hs_codes=[h.hs_code for h in result.hs_codes[:3]] if result.hs_codes else [])
                    
                    return result
            except Exception as e:
                error_msg = str(e)
                logfire.error(f"❌ HS database search failed",
                            source=source_name,
                            query=query,
                            error=error_msg,
                            error_type=type(e).__name__)
                logger.error(f"Error searching {source_name}: {e}")
                raise
