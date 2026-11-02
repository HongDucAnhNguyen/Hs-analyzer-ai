"""Base crawler interface"""

from abc import ABC, abstractmethod
from typing import List
from crawl_service.core.models import RulingResult


class BaseCrawler(ABC):
    """Base class for all website crawlers"""
    
    def __init__(self):
        self.source_name = self.__class__.__name__.replace("Crawler", "")
    
    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[RulingResult]:
        """
        Search for rulings based on query
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            
        Returns:
            List of RulingResult objects
        """
        pass
