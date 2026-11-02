"""Orchestrator service for coordinating all crawlers"""

import asyncio
import logging
from typing import List, Dict
from collections import defaultdict

from crawl_service.core.models import RulingResult, CrawlRequest, CrawlResponse, ProductCrawlQuery, CrawlResponseGrouped, TechnicalNameGroup, RulingLink, AggregatedHSCode, RulingHSCode
from crawl_service.core.query_rewriter import rewrite_product_to_queries
from crawl_service.core.reason_generator import generate_reason_with_score
from crawl_service.crawlers.cbsa_canada import CBSACanadaCrawler
from crawl_service.crawlers.carm_canada import CARMCanadaCrawler
from crawl_service.crawlers.us_cbp import USCBPCrawler
from crawl_service.crawlers.uk_hmrc import UKHMRCCrawler
from crawl_service.utils.shared_query_cache import shared_query_cache

logger = logging.getLogger(__name__)

# Minimum relevance score threshold - results below this score will be filtered out
MIN_RELEVANCE_SCORE = 0.4  # Only include results with score >= 0.4 (moderately relevant or higher)


def normalize_hs_code(hs_code: str) -> str:
    """
    Normalize HS code to exactly 6 digits (international standard).
    Removes any non-digit characters, pads 4-digit codes with "00", and takes first 6 digits.
    
    Args:
        hs_code: Raw HS code string (e.g., "8471.30.01", "847130010000", "4802", "9903.88.15")
        
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


def extract_hs_codes_from_ruling(ruling: RulingResult) -> List[RulingHSCode]:
    """
    Extract HS codes from a single ruling.
    Normalizes tariff codes to 6-digit HS codes.
    
    Args:
        ruling: RulingResult object
        
    Returns:
        List of RulingHSCode objects (unique, sorted) with count and percentage
    """
    # Get tariffs from the ruling
    tariffs = ruling.tariffs or []
    
    # Also check metadata for tariffs (backward compatibility)
    if not tariffs and ruling.metadata and 'tariffs' in ruling.metadata:
        tariffs = ruling.metadata.get('tariffs', [])
    
    # Also check for classification_number in CARM Canada rulings
    if not tariffs and ruling.metadata and 'classification_number' in ruling.metadata:
        classification = ruling.metadata.get('classification_number', '')
        if classification:
            tariffs = [classification]
    
    # First pass: normalize and deduplicate to get unique codes
    seen = set()
    unique_codes = []
    for tariff in tariffs:
        if not tariff:
            continue
        
        normalized = normalize_hs_code(tariff)
        if not normalized or normalized in seen:
            continue
        
        seen.add(normalized)
        unique_codes.append(normalized)
    
    # Calculate count and percentage for each HS code
    total_codes = len(unique_codes)
    result = []
    for hs_code in unique_codes:
        # count = 1 (each unique HS code appears once in this ruling)
        # percentage = share of this code among all codes in this ruling
        percentage = round((1 / total_codes) * 100, 2) if total_codes > 0 else 0.0
        
        result.append(RulingHSCode(
            hs_code=hs_code,
            count=1,
            percentage=percentage
        ))
    
    # Sort by HS code
    result.sort(key=lambda x: x.hs_code)
    return result


def aggregate_hs_codes_from_rulings(rulings: List[RulingResult]) -> List[AggregatedHSCode]:
    """
    Aggregate HS codes from all rulings.
    Normalizes to 6-digit codes and counts occurrences across all rulings.
    
    Args:
        rulings: List of RulingResult objects
        
    Returns:
        List of AggregatedHSCode objects sorted by count (descending)
    """
    # Group by normalized HS code
    aggregated: Dict[str, int] = defaultdict(int)
    
    for ruling in rulings:
        # Get tariffs from the ruling
        tariffs = ruling.tariffs or []
        
        # Also check metadata for tariffs (backward compatibility)
        if not tariffs and ruling.metadata and 'tariffs' in ruling.metadata:
            tariffs = ruling.metadata.get('tariffs', [])
        
        # Also check for classification_number in CARM Canada rulings
        if not tariffs and ruling.metadata and 'classification_number' in ruling.metadata:
            classification = ruling.metadata.get('classification_number', '')
            if classification:
                tariffs = [classification]
        
        for tariff in tariffs:
            if not tariff:
                continue
            
            normalized = normalize_hs_code(tariff)
            if not normalized:  # Skip empty codes
                continue
            
            aggregated[normalized] += 1
    
    # Calculate total count for percentage
    total_count = sum(aggregated.values())
    
    # Convert to AggregatedHSCode objects
    result = []
    for normalized_code, count in aggregated.items():
        percentage = round((count / total_count) * 100, 2) if total_count > 0 else 0.0
        
        result.append(AggregatedHSCode(
            hs_code=normalized_code,
            count=count,
            percentage=percentage
        ))
    
    # Sort by count (descending), then by HS code
    result.sort(key=lambda x: (-x.count, x.hs_code))
    
    return result


class CrawlOrchestrator:
    """Orchestrates crawling across all sources"""
    
    def __init__(self):
        self.crawlers = [
            CBSACanadaCrawler(),
            CARMCanadaCrawler(),
            USCBPCrawler(),
            UKHMRCCrawler(),
        ]
    
    async def crawl_all(self, request: CrawlRequest) -> CrawlResponse:
        """
        Crawl all sources in parallel using simple query
        
        Args:
            request: CrawlRequest with query and parameters
            
        Returns:
            CrawlResponse with aggregated results
        """
        query = request.query
        max_results = request.max_results_per_source
        
        logger.info(f"Starting crawl for query: '{query}' with max {max_results} results per source")
        
        # Create tasks for all crawlers with single query
        tasks = []
        for crawler in self.crawlers:
            task = self._crawl_with_error_handling(crawler, query, max_results)
            tasks.append(task)
        
        # Run all crawlers in parallel
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        all_results = []
        sources_queried = []
        errors = {}
        
        for crawler, result in zip(self.crawlers, results_list):
            source_name = crawler.source_name
            sources_queried.append(source_name)
            
            if isinstance(result, Exception):
                error_msg = str(result)
                logger.error(f"Error from {source_name}: {error_msg}")
                errors[source_name] = error_msg
            elif isinstance(result, list):
                all_results.extend(result)
                logger.info(f"{source_name}: Successfully retrieved {len(result)} results")
            else:
                error_msg = f"Unexpected result type: {type(result)}"
                logger.error(f"{source_name}: {error_msg}")
                errors[source_name] = error_msg
        
        response = CrawlResponse(
            query=query,
            rewritten_queries=[query],
            total_results=len(all_results),
            results=all_results,
            sources_queried=sources_queried,
            errors=errors
        )
        
        logger.info(f"Crawl completed: {len(all_results)} total results from {len(sources_queried)} sources")
        
        return response
    
    async def crawl_with_product_info(self, product_query: ProductCrawlQuery) -> CrawlResponse:
        """
        Crawl all sources using product information with query rewriting
        
        Args:
            product_query: ProductCrawlQuery with detailed product information
            
        Returns:
            CrawlResponse with aggregated results
        """
        logger.info(f"Starting crawl with product info: '{product_query.product_name}'")
        
        # Step 1: Rewrite product information into 3 search queries
        try:
            rewritten_queries = await rewrite_product_to_queries(
                product_name=product_query.product_name,
                science_name=product_query.science_name or "",
                product_description=product_query.product_description or "",
                function=product_query.function or "",
                material=product_query.material or "",
                structure=product_query.structure or "",
                specifications=product_query.specifications or ""
            )
            logger.info(f"Rewritten queries: {rewritten_queries}")
        except Exception as e:
            logger.error(f"Error rewriting queries: {e}")
            # Fallback to just product name
            rewritten_queries = [product_query.product_name]
        
        # Step 2: Crawl all sources with each query
        all_results = []
        sources_queried = []
        errors = {}
        max_results_per_query = max(1, product_query.max_results_per_source // len(rewritten_queries))
        
        for query in rewritten_queries:
            logger.info(f"Crawling with query: '{query}'")
            
            # Create tasks for all crawlers
            tasks = []
            for crawler in self.crawlers:
                task = self._crawl_with_error_handling(crawler, query, max_results_per_query)
                tasks.append(task)
            
            # Run all crawlers in parallel for this query
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Aggregate results
            for crawler, result in zip(self.crawlers, results_list):
                source_name = crawler.source_name
                if source_name not in sources_queried:
                    sources_queried.append(source_name)
                
                if isinstance(result, Exception):
                    error_msg = str(result)
                    logger.error(f"Error from {source_name} for query '{query}': {error_msg}")
                    if source_name not in errors:
                        errors[source_name] = error_msg
                elif isinstance(result, list):
                    all_results.extend(result)
                    logger.info(f"{source_name}: Retrieved {len(result)} results for query '{query}'")
        
        # Remove duplicates based on ruling_id and source
        seen = set()
        unique_results = []
        for result in all_results:
            key = (result.source, result.ruling_id)
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
        
        response = CrawlResponse(
            query=product_query.product_name,
            rewritten_queries=rewritten_queries,
            total_results=len(unique_results),
            results=unique_results,
            sources_queried=sources_queried,
            errors=errors
        )
        
        logger.info(f"Crawl completed: {len(unique_results)} unique results from {len(sources_queried)} sources")
        
        return response
    
    async def crawl_with_product_info_grouped(self, product_query: ProductCrawlQuery) -> CrawlResponseGrouped:
        """
        Crawl all sources using product information with query rewriting.
        Returns results grouped by technical_name with Vietnamese reasons.
        Fully parallelized for maximum performance.
        
        Args:
            product_query: ProductCrawlQuery with detailed product information
            
        Returns:
            CrawlResponseGrouped with results organized by technical name
        """
        import logfire
        
        with logfire.span(
            "crawl_with_product_info_grouped",
            product_name=product_query.product_name,
            science_name=product_query.science_name or "",
            max_results=product_query.max_results_per_source
        ):
            logfire.info("🚀 Starting crawl service", 
                        product_name=product_query.product_name,
                        science_name=product_query.science_name or "")
            logger.info(f"Starting grouped crawl with product info: '{product_query.product_name}'")
            
            # Step 1: Rewrite product information into 3 search queries (technical names)
            # Uses distributed locking to ensure consistent queries across concurrent calls
            with logfire.span("rewrite_queries_with_lock"):
                logfire.info("🔍 Getting rewritten queries (with distributed lock if needed)")
                
                product_info = product_query.dict()
                
                async def _generate_queries():
                    """Generator function for lock-aware cache"""
                    return await rewrite_product_to_queries(
                        product_name=product_query.product_name,
                        science_name=product_query.science_name or "",
                        product_description=product_query.product_description or "",
                        function=product_query.function or "",
                        material=product_query.material or "",
                        structure=product_query.structure or "",
                        specifications=product_query.specifications or ""
                    )
                
                try:
                    rewritten_queries, was_generated = await shared_query_cache.get_or_generate_queries(
                        product_info, _generate_queries
                    )
                    
                    if was_generated:
                        logfire.info("✅ Query rewriting completed (generated new)", 
                                    count=len(rewritten_queries),
                                    technical_names=rewritten_queries)
                        logger.info(f"Generated new rewritten queries: {rewritten_queries}")
                    else:
                        logfire.info("✅ Using cached/shared rewritten queries", 
                                    count=len(rewritten_queries),
                                    technical_names=rewritten_queries)
                        logger.info(f"Using cached/shared rewritten queries: {rewritten_queries}")
                        
                except Exception as e:
                    logfire.error("❌ Query rewriting failed", error=str(e))
                    logger.error(f"Error rewriting queries: {e}")
                    # Fallback to just product name
                    rewritten_queries = [product_query.product_name]
                    logfire.info("⚠️ Using fallback query", fallback=product_query.product_name)
            
            # Step 2: PARALLEL - Crawl all sources for ALL technical names at once
            max_results_per_query = max(1, product_query.max_results_per_source // len(rewritten_queries))
            
            with logfire.span("parallel_crawl_all_queries", 
                            query_count=len(rewritten_queries),
                            source_count=len(self.crawlers),
                            total_tasks=len(rewritten_queries) * len(self.crawlers)):
                # Create tasks for ALL combinations of (technical_name, crawler)
                all_crawl_tasks = []
                task_metadata = []  # Track which task belongs to which (technical_name, crawler)
                
                logfire.info("🔧 Preparing parallel crawl tasks",
                            queries=rewritten_queries,
                            sources=[c.source_name for c in self.crawlers],
                            max_results_per_query=max_results_per_query)
                
                for technical_name in rewritten_queries:
                    for crawler in self.crawlers:
                        task = self._crawl_with_error_handling(crawler, technical_name, max_results_per_query)
                        all_crawl_tasks.append(task)
                        task_metadata.append({
                            'technical_name': technical_name,
                            'source': crawler.source_name,
                            'source_url': crawler.source_url,
                            'crawler': crawler
                        })
                
                # Run ALL crawl tasks in parallel (3 queries x 4 sources = 12 parallel tasks)
                logfire.info(f"🚀 Launching {len(all_crawl_tasks)} parallel crawl tasks",
                            task_count=len(all_crawl_tasks),
                            breakdown=f"{len(rewritten_queries)} queries × {len(self.crawlers)} sources")
                logger.info(f"Launching {len(all_crawl_tasks)} parallel crawl tasks ({len(rewritten_queries)} queries x {len(self.crawlers)} sources)")
                
                all_results = await asyncio.gather(*all_crawl_tasks, return_exceptions=True)
                
                logfire.info(f"✅ Completed all parallel crawl tasks", 
                            completed=len(all_results),
                            successful=sum(1 for r in all_results if not isinstance(r, Exception)),
                            failed=sum(1 for r in all_results if isinstance(r, Exception)))
            
            # Step 3: Organize results by technical name
            with logfire.span("organize_results"):
                logfire.info("📊 Organizing crawl results by technical name")
                results_by_technical_name = {name: [] for name in rewritten_queries}
                sources_queried = []
                errors = {}
                
                for result, metadata in zip(all_results, task_metadata):
                    technical_name = metadata['technical_name']
                    source_name = metadata['source']
                    
                    if source_name not in [item["source_name"] for item in sources_queried]:
                        sources_queried.append({
                            "source_name": source_name,
                            "source_url": metadata['source_url']
                        })
                    
                    if isinstance(result, Exception):
                        error_msg = str(result)
                        logfire.warn(f"⚠️ Crawl error", 
                                    source=source_name,
                                    technical_name=technical_name,
                                    error=error_msg)
                        logger.error(f"Error from {source_name} for '{technical_name}': {error_msg}")
                        if source_name not in errors:
                            errors[source_name] = error_msg
                    elif isinstance(result, list):
                        results_by_technical_name[technical_name].extend(result)
                        logfire.info(f"📥 Retrieved results",
                                    source=source_name,
                                    technical_name=technical_name,
                                    count=len(result))
                        logger.info(f"{source_name}: Retrieved {len(result)} results for '{technical_name}'")
                
                # Log summary
                total_raw_results = sum(len(results) for results in results_by_technical_name.values())
                logfire.info("📊 Organization completed",
                            total_raw_results=total_raw_results,
                            by_query={name: len(results) for name, results in results_by_technical_name.items()})
            
            # Step 4: PARALLEL - Generate reasons for ALL rulings at once
            with logfire.span("parallel_generate_all_reasons"):
                logfire.info("🤖 Starting parallel reason generation for all rulings")
                technical_name_groups = []
                total_results = 0
                all_rulings_for_hs_aggregation = []  # Track all rulings for overall HS code aggregation
                
                for technical_name in rewritten_queries:
                    query_results = results_by_technical_name[technical_name]
                    
                    # Deduplicate
                    with logfire.span(f"deduplicate_{technical_name}"):
                        seen = set()
                        unique_results = []
                        for ruling in query_results:
                            key = (ruling.source, ruling.ruling_id)
                            if key not in seen:
                                seen.add(key)
                                unique_results.append(ruling)
                        
                        duplicates_removed = len(query_results) - len(unique_results)
                        if duplicates_removed > 0:
                            logfire.info(f"🔄 Deduplication",
                                        technical_name=technical_name,
                                        before=len(query_results),
                                        after=len(unique_results),
                                        removed=duplicates_removed)
                    
                    # Add unique results for overall HS code aggregation
                    all_rulings_for_hs_aggregation.extend(unique_results)
                    
                    if not unique_results:
                        # No results for this technical name
                        logfire.info(f"📭 No results for query",
                                    technical_name=technical_name)
                        technical_name_groups.append(TechnicalNameGroup(
                            technical_name=technical_name,
                            links=[]
                        ))
                        continue
                    
                    # Create parallel tasks for reason generation with scoring
                    with logfire.span(f"generate_reasons_{technical_name}", 
                                     count=len(unique_results),
                                     technical_name=technical_name):
                        logfire.info(f"🤖 Preparing {len(unique_results)} parallel LLM calls with scoring",
                                    technical_name=technical_name,
                                    ruling_ids=[r.ruling_id for r in unique_results])
                        
                        # Prepare full product info for better relevance scoring
                        product_info = {
                            "product_name": product_query.product_name,
                            "science_name": product_query.science_name or "",
                            "product_description": product_query.product_description or "",
                            "function": product_query.function or "",
                            "material": product_query.material or "",
                            "structure": product_query.structure or "",
                            "specifications": product_query.specifications or ""
                        }
                        
                        reason_tasks = []
                        for ruling in unique_results:
                            task = generate_reason_with_score(
                                technical_name=technical_name,
                                ruling_content=ruling.content,
                                product_info=product_info
                            )
                            reason_tasks.append(task)
                        
                        # Generate ALL reasons with scores in parallel
                        logger.info(f"Generating {len(reason_tasks)} reasons with scores in parallel for '{technical_name}'")
                        reason_results = await asyncio.gather(*reason_tasks, return_exceptions=True)
                        
                        successful_reasons = sum(1 for r in reason_results if not isinstance(r, Exception))
                        failed_reasons = sum(1 for r in reason_results if isinstance(r, Exception))
                        logfire.info(f"✅ Reason generation with scoring completed",
                                    technical_name=technical_name,
                                    total=len(reason_results),
                                    successful=successful_reasons,
                                    failed=failed_reasons)
                        
                        # Build ruling links with scores
                        ruling_links_with_scores = []
                        for ruling, reason_result in zip(unique_results, reason_results):
                            if isinstance(reason_result, Exception):
                                logfire.error(f"❌ Reason generation failed",
                                            ruling_id=ruling.ruling_id,
                                            source=ruling.source,
                                            error=str(reason_result))
                                logger.error(f"Error generating reason for {ruling.ruling_id}: {reason_result}")
                                # Fallback with low score
                                reason_data = {
                                    "relevance_score": 0.3,
                                    "reason": f"Quyết định hải quan liên quan đến '{technical_name}'."
                                }
                            else:
                                reason_data = reason_result
                            
                            # Extract HS codes from this ruling
                            ruling_hs_codes = extract_hs_codes_from_ruling(ruling)
                            
                            ruling_links_with_scores.append({
                                "ruling_link": RulingLink(
                                    reason=reason_data["reason"],
                                    link=ruling.url,
                                    ruling_id=ruling.ruling_id,
                                    source=ruling.source,
                                    source_url=ruling.source_url,
                                    relevance_score=reason_data["relevance_score"],
                                    hs_codes=ruling_hs_codes
                                ),
                                "score": reason_data["relevance_score"]
                            })
                        
                        # Sort by relevance score (highest first) and take top 5
                        ruling_links_with_scores.sort(key=lambda x: x["score"], reverse=True)
                        
                        # Filter by minimum threshold and take top 5
                        filtered_links = [
                            item for item in ruling_links_with_scores 
                            if item["score"] >= MIN_RELEVANCE_SCORE
                        ]
                        top_ruling_links = [item["ruling_link"] for item in filtered_links[:5]]
                        
                        logger.info(
                            f"Technical name '{technical_name}': {len(top_ruling_links)} results "
                            f"(filtered top 5 by score >= {MIN_RELEVANCE_SCORE})"
                        )
                        logfire.info(f"📊 Filtered top results by score",
                                    technical_name=technical_name,
                                    original_count=len(ruling_links_with_scores),
                                    filtered_count=len(top_ruling_links),
                                    min_threshold=MIN_RELEVANCE_SCORE,
                                    top_scores=[f"{item['score']:.2f}" for item in filtered_links[:5]])
                        
                        technical_name_groups.append(TechnicalNameGroup(
                            technical_name=technical_name,
                            links=top_ruling_links
                        ))
                        total_results += len(top_ruling_links)
                        logfire.info(f"✅ Group completed",
                                    technical_name=technical_name,
                                    results_count=len(top_ruling_links))
            
            # Step 5: Aggregate HS codes across ALL rulings (deduplicated globally)
            with logfire.span("aggregate_all_hs_codes"):
                # Deduplicate rulings globally before aggregating
                seen_global = set()
                global_unique_rulings = []
                for ruling in all_rulings_for_hs_aggregation:
                    key = (ruling.source, ruling.ruling_id)
                    if key not in seen_global:
                        seen_global.add(key)
                        global_unique_rulings.append(ruling)
                
                overall_hs_codes = aggregate_hs_codes_from_rulings(global_unique_rulings)
                logfire.info(f"📊 Aggregated overall HS codes",
                            total_rulings=len(global_unique_rulings),
                            unique_hs_codes=len(overall_hs_codes),
                            top_hs_codes=[f"{h.hs_code} ({h.count})" for h in overall_hs_codes[:10]])
                logger.info(f"Aggregated {len(overall_hs_codes)} unique HS codes from {len(global_unique_rulings)} rulings")
            
            response = CrawlResponseGrouped(
                product_name=product_query.product_name,
                results=technical_name_groups,
                total_results=total_results,
                total_unique_hs_codes=len(overall_hs_codes),
                sources_queried=sources_queried,
                errors=errors
            )
            
            logfire.info("🎉 Crawl service completed successfully", 
                        total_results=total_results,
                        technical_names_count=len(rewritten_queries),
                        total_unique_hs_codes=len(overall_hs_codes),
                        sources_queried=sources_queried,
                        has_errors=len(errors) > 0)
            logger.info(f"Grouped crawl completed: {total_results} total results, {len(overall_hs_codes)} unique HS codes across {len(rewritten_queries)} technical names")
            
            return response
    
    async def _crawl_with_error_handling(
        self, 
        crawler, 
        query: str, 
        max_results: int
    ) -> List[RulingResult]:
        """
        Crawl a single source with error handling and detailed logging
        
        Args:
            crawler: Crawler instance
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of RulingResult or empty list on error
        """
        import logfire
        
        source_name = crawler.source_name
        with logfire.span(f"crawl_{source_name.replace(' ', '_')}", 
                         source=source_name,
                         query=query,
                         max_results=max_results):
            try:
                logfire.info(f"🔍 Starting crawl",
                            source=source_name,
                            query=query,
                            max_results=max_results)
                
                results = await crawler.search(query, max_results)
                
                logfire.info(f"✅ Crawl completed",
                            source=source_name,
                            query=query,
                            results_count=len(results),
                            ruling_ids=[r.ruling_id for r in results[:5]] if results else [])  # Log first 5 IDs
                
                return results
            except Exception as e:
                error_msg = str(e)
                logfire.error(f"❌ Crawl failed",
                            source=source_name,
                            query=query,
                            error=error_msg,
                            error_type=type(e).__name__)
                logger.error(f"Error crawling {source_name}: {e}")
                raise
