"""Pydantic schemas for HS Code Analyzer API"""

from typing import List, Optional
import unicodedata
from pydantic import BaseModel, Field, field_validator


class HSCodeCandidate(BaseModel):
    """HS code candidate with occurrence count"""
    hs_code: str = Field(..., description="HS code (6 or 8 digits)")
    number_of_occurrences: int = Field(..., description="Number of occurrences in search results", ge=0)
    
    @field_validator('hs_code', mode='before')
    @classmethod
    def validate_hs_code(cls, v):
        if v is None:
            raise ValueError("HS code is required")
        # Normalize and clean HS code
        v = str(v).strip().replace(".", "").replace(" ", "")
        # Basic validation: should be 4-10 digits
        if not v.isdigit() or len(v) < 4:
            raise ValueError(f"Invalid HS code format: {v}")
        return v


class ProductInfo(BaseModel):
    """Product information for HS code analysis - compatible with other services"""
    engagement_code: Optional[str] = Field(None, description="Engagement code provided by the client")
    product_name: str = Field(..., description="Product name (required)")
    science_name: Optional[str] = Field(None, description="Scientific or technical name")
    product_description: Optional[str] = Field(None, description="Detailed product description")
    function: Optional[str] = Field(None, description="Main function of the product")
    structure: Optional[str] = Field(None, description="Structure or assembly method")
    material: Optional[str] = Field(None, description="Main material composition")
    specifications: Optional[str] = Field(None, description="Technical specifications (dimensions, weight, etc.)")
    other_information: Optional[str] = Field(None, description="Additional information")
    
    @field_validator('engagement_code', 'product_name', 'science_name', 'product_description', 'function', 
                     'structure', 'material', 'specifications', 'other_information', mode='before')
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
            return normalized or None
        return v

    @field_validator('product_name', mode='after')
    @classmethod
    def validate_required_not_blank(cls, v):
        if v is None:
            raise ValueError("Field cannot be blank.")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be blank.")
        return v


class HSCodeAnalyzeRequest(BaseModel):
    """Request model for HS code analysis"""
    product: ProductInfo = Field(..., description="Product information to analyze")
    hs_codes: List[HSCodeCandidate] = Field(..., description="List of HS codes to analyze", min_length=1)


class HSCodeAnalysisResult(BaseModel):
    """Analysis result for a single HS code - structured similar to classification service"""
    hs_code: str = Field(
        ..., 
        description="HS code being analyzed"
    )
    number_of_occurrences: int = Field(
        ..., 
        description="Number of occurrences in search results"
    )
    compatibility_score: float = Field(
        ..., 
        description="Compatibility score from 0.0 to 1.0", 
        ge=0.0, 
        le=1.0
    )
    hs_code_description: Optional[str] = Field(
        None, 
        description="Description of the HS code according to the Harmonized System (Section, Chapter, Heading)"
    )
    section_info: Optional[str] = Field(
        None,
        description="Section information the HS code belongs to (e.g., Section XVI - Machinery and mechanical appliances)"
    )
    chapter_info: Optional[str] = Field(
        None,
        description="Chapter information the HS code belongs to (e.g., Chapter 84 - Nuclear reactors, boilers, machinery)"
    )
    gir_applied: Optional[str] = Field(
        None,
        description="Quick note of which GIR rules were applied (e.g., GIR 1 & 3a)"
    )
    legal_reasoning: str = Field(
        ...,
        description="Legal reasoning (3-5 sentences) explaining score, including any exclusion notes"
    )


class HSCodeAnalyzeResponse(BaseModel):
    """Response model for HS code analysis"""
    product_name: str = Field(
        ..., 
        description="Input product name"
    )
    total_hs_codes_analyzed: int = Field(
        ..., 
        description="Total number of HS codes analyzed"
    )
    recommended_hs_code: Optional[str] = Field(
        None, 
        description="Recommended HS code (most suitable for the product)"
    )
    results: List[HSCodeAnalysisResult] = Field(
        ..., 
        description="Detailed analysis results for each HS code, sorted by compatibility score descending"
    )
    executive_summary: str = Field(
        ...,
        description="Executive summary (2-3 sentences) explaining the final decision"
    )
