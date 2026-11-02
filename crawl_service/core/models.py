"""Pydantic models for crawl service"""

from typing import List, Optional, Any, Dict
import unicodedata
from pydantic import BaseModel, Field, field_validator


class ProductCrawlQuery(BaseModel):
    """Schema for product crawl query with detailed product information"""
    engagement_code: Optional[str] = Field(None, description="Engagement code provided by the client")
    product_name: str = Field(..., description="Main product name")
    science_name: Optional[str] = Field(None, description="Scientific or technical name")
    product_description: Optional[str] = Field(None, description="Product description")
    function: Optional[str] = Field(None, description="Primary function or usage")
    structure: Optional[str] = Field(None, description="Physical structure or design")
    material: Optional[str] = Field(None, description="Main material or composition")
    specifications: Optional[str] = Field(None, description="Key specifications")
    other_information: Optional[str] = Field(None, description="Other additional information (JSON string)")
    max_results_per_source: int = Field(
        default=10,
        description="Maximum number of results to return per source",
        ge=1,
        le=50
    )
    
    @field_validator('engagement_code', 'product_name', 'science_name', 'product_description', 'function', 'structure', 'material', 'specifications', 'other_information', mode='before')
    @classmethod
    def validate_utf8_string(cls, v):
        if v is None:
            return v
        if isinstance(v, bytes):
            try:
                v = v.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("Invalid UTF-8 encoding.")
        if isinstance(v, str):
            normalized = unicodedata.normalize('NFC', v).strip()
            return normalized
        return v

    @field_validator('product_name', mode='after')
    @classmethod
    def validate_required_not_blank(cls, v):
        if v is None:
            raise ValueError("Field cannot be blank.")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be blank.")
        return v

    @field_validator('product_description', 'function', mode='after')
    @classmethod
    def validate_required_or_na(cls, v):
        if v is None:
            raise ValueError("Field cannot be blank.")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be blank.")
        return v

    @field_validator('product_description', 'function', mode='after')
    @classmethod
    def normalize_na_to_empty(cls, v):
        if isinstance(v, str) and v.strip().lower() == "n/a":
            return ""
        return v


class RulingHSCode(BaseModel):
    """HS code from a ruling"""
    hs_code: str = Field(..., description="Normalized 6-digit HS code")
    count: Optional[int] = Field(None, description="Count (null for ruling HS codes)")
    percentage: Optional[float] = Field(None, description="Percentage (null for ruling HS codes)")


class RulingLink(BaseModel):
    """A single ruling link with reason"""
    reason: str = Field(..., description="Vietnamese explanation of why this ruling is relevant")
    link: str = Field(..., description="URL to the ruling")
    ruling_id: str = Field(..., description="Ruling ID or number")
    source: str = Field(..., description="Source website name")
    source_url: str = Field(..., description="Source website url")
    relevance_score: float = Field(..., description="Relevance score from 0.0 (not relevant) to 1.0 (highly relevant)", ge=0.0, le=1.0)
    hs_codes: List[RulingHSCode] = Field(default_factory=list, description="HS codes from this ruling")


class AggregatedHSCode(BaseModel):
    """Aggregated HS code with count from rulings"""
    hs_code: str = Field(..., description="Normalized 6-digit HS code")
    count: int = Field(..., description="Number of rulings containing this HS code")
    percentage: float = Field(..., description="Percentage of total occurrences")


class TechnicalNameGroup(BaseModel):
    """Group of rulings for a specific technical name"""
    technical_name: str = Field(..., description="The search query/technical name used")
    links: List[RulingLink] = Field(default_factory=list, description="List of relevant rulings")


class CrawlResponseGrouped(BaseModel):
    """Response model for crawl results grouped by technical name"""
    product_name: str = Field(..., description="Original product name from input")
    results: List[TechnicalNameGroup] = Field(..., description="Results grouped by technical name")
    total_results: int = Field(..., description="Total number of rulings found")
    total_unique_hs_codes: int = Field(0, description="Total unique HS codes found")
    sources_queried: List[Dict[str, str]] = Field(default_factory=list, description="List of sources queried")
    errors: Dict[str, str] = Field(default_factory=dict, description="Errors by source if any")


class RulingResult(BaseModel):
    """Single ruling result from a crawler"""
    source: str = Field(..., description="Source website identifier")
    source_url: str = Field(..., description="Source website url")
    ruling_id: str = Field(..., description="Ruling identifier/number")
    title: str = Field(..., description="Title or subject of the ruling")
    content: str = Field(..., description="Full content/details of the ruling")
    url: str = Field(..., description="URL to the ruling")
    tariffs: List[str] = Field(default_factory=list, description="List of tariff/HS codes from the ruling")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    

class CrawlRequest(BaseModel):
    """Request model for crawling HS code rulings - simple query version"""
    query: str = Field(..., description="Search query for HS code rulings", min_length=1)
    max_results_per_source: int = Field(
        default=10,
        description="Maximum number of results to return per source",
        ge=1,
        le=50
    )


class CrawlResponse(BaseModel):
    """Response model for crawl results"""
    query: str = Field(..., description="Original search query")
    rewritten_queries: List[str] = Field(default_factory=list, description="Rewritten queries used for search")
    total_results: int = Field(..., description="Total number of results found")
    results: List[RulingResult] = Field(default_factory=list, description="List of ruling results")
    sources_queried: List[str] = Field(default_factory=list, description="List of sources queried")
    errors: Dict[str, str] = Field(default_factory=dict, description="Errors by source if any")


# HS Database Models

class HSCodeResult(BaseModel):
    """Single HS code result from HS database"""
    hs_code: str = Field(..., description="HS code")
    count: Optional[int] = Field(None, description="Number of times this code appeared")
    percentage: Optional[float] = Field(None, description="Percentage of total occurrences")
    description: Optional[str] = Field(None, description="Description of the HS code")
    url: Optional[str] = Field(None, description="URL to more information")


class HSCodeSourceResult(BaseModel):
    """HS codes from a single source"""
    source: str = Field(..., description="Source website name")
    source_url: str = Field(..., description="Source website url")
    query: str = Field(..., description="Query used for this source")
    hs_codes: List[HSCodeResult] = Field(default_factory=list, description="List of HS codes found")
    result_url: Optional[str] = Field(None, description="URL of the search results page")
    total_count: Optional[int] = Field(None, description="Total count across all HS codes")


class HSCodeQueryGroup(BaseModel):
    """Group of HS code results for a specific technical query"""
    technical_name: str = Field(..., description="The technical query used")
    sources: List[HSCodeSourceResult] = Field(default_factory=list, description="Results from each source")
    total_hs_codes: int = Field(0, description="Total unique HS codes found across all sources")


class HSCodeDatabaseResponse(BaseModel):
    """Response model for HS database search"""
    product_name: str = Field(..., description="Original product name from input")
    rewritten_queries: List[str] = Field(..., description="Technical queries used for search")
    results: List[HSCodeQueryGroup] = Field(..., description="Results grouped by technical query")
    total_unique_hs_codes: int = Field(0, description="Total unique HS codes across all queries and sources")
    sources_queried: List[Dict[str, str]] = Field(default_factory=list, description="List of sources queried with source_name and source_url")
    errors: Dict[str, str] = Field(default_factory=dict, description="Errors by source if any")
