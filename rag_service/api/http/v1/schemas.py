from typing import Optional
from pydantic import BaseModel, Field, field_validator
import unicodedata


class ProductSearchQuery(BaseModel):
    """Schema for product search query - compatible with classifier service"""
    product_name: str = Field(..., description="Main product name. Example: 'hair dryer', 'coffee machine'.")
    science_name: Optional[str] = Field(None, description="Scientific or technical name, if available. Example: 'Sodium bicarbonate', 'ABS plastic'.")
    product_description: Optional[str] = Field(None, description="Short summary of the product's main purpose or features (≤ 2 sentences).")
    function: Optional[str] = Field(None, description="Primary function or usage (verb + object). Example: 'drying hair', 'grinding coffee beans'.")
    structure: Optional[str] = Field(None, description="Physical structure or design. Example: 'handheld', 'table-top', 'two-door', 'multi-layer'.")
    material: Optional[str] = Field(None, description="Main material or composition. Example: 'stainless steel', 'ABS plastic', 'wood'.")
    specifications: Optional[str] = Field(None, description="Key specifications such as power, size, voltage, or weight. Can be plain text or JSON.")
    other_information: Optional[str] = Field(
        None,
        description=(
            "Additional attributes in JSON string format. Example: "
            '{"brand": "XYZ", "model": "A1", "origin": "CN", "warranty_months": 12}. '
            "If sent through a form, ensure it is valid JSON text."
        ),
    )
    
    @field_validator('product_name', 'science_name', 'product_description', 'function', 'structure', 'material', 'specifications', 'other_information', mode='before')
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
            return unicodedata.normalize('NFC', v)
        return v
