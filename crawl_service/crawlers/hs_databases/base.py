"""Base class for HS database crawlers"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pydantic import BaseModel


class HSCodeResult(BaseModel):
    """Single HS code result"""
    hs_code: str
    count: Optional[int] = None
    percentage: Optional[float] = None
    description: Optional[str] = None
    url: Optional[str] = None


class HSCodeDatabaseResult(BaseModel):
    """Result from an HS database crawler"""
    source: str
    source_url: str = ""
    query: str
    hs_codes: List[HSCodeResult]
    result_url: Optional[str] = None
    total_count: Optional[int] = None
    

class HSCodeDatabaseCrawler(ABC):
    """Base class for HS code database crawlers"""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this source"""
        pass
    
    @abstractmethod
    async def search(self, query: str) -> HSCodeDatabaseResult:
        """
        Search for HS codes using the given query
        
        Args:
            query: Search query string
            
        Returns:
            HSCodeDatabaseResult with HS codes found
        """
        pass
