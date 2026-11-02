"""Helper utilities for Excel processing

Contains:
- Numeric value parsing
- Date utilities
- String utilities
"""

import re
from datetime import datetime
from typing import Any, Optional

import pandas as pd


def parse_numeric_value(val: Any) -> Optional[float]:
    """Parse a value that might be a number with commas or other formatting
    
    Args:
        val: Value to parse (can be int, float, str, or None)
        
    Returns:
        Parsed float value or None if parsing fails
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    
    if isinstance(val, (int, float)):
        return float(val)
    
    if isinstance(val, str):
        cleaned = val.strip().replace(',', '').replace(' ', '')
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    return None


def is_valid_npl_sp(npl_sp: Any) -> bool:
    """Check if NPL/SP is valid (not empty, not None, not only special chars)
    
    Args:
        npl_sp: Value to check
        
    Returns:
        True if valid, False otherwise
    """
    if not npl_sp or pd.isna(npl_sp):
        return False
    npl_str = str(npl_sp).strip()
    if not npl_str:
        return False
    # Check if contains at least one alphanumeric character
    return bool(re.search(r'[a-zA-Z0-9]', npl_str))


def format_hs_code(hs_code: Any) -> str:
    """Format HS code to 8 digits with leading zeros
    
    Args:
        hs_code: HS code value (can be str or number)
        
    Returns:
        Formatted HS code string
    """
    if hs_code is None or (isinstance(hs_code, float) and pd.isna(hs_code)):
        return ""
    
    hs_str = str(hs_code).strip()
    
    # Handle numeric values that may have been read as float
    if hs_str.replace('.', '').replace(',', '').isdigit():
        hs_str = str(int(float(hs_str)))
    
    # Pad with leading zeros to 8 digits
    if hs_str.isdigit():
        hs_str = hs_str.zfill(8)
    
    return hs_str


def generate_filename(prefix: str = "report", suffix: str = "") -> str:
    """Generate a filename with timestamp
    
    Args:
        prefix: Filename prefix
        suffix: Optional suffix before timestamp
        
    Returns:
        Filename with timestamp (e.g., report_20260120_143022.xlsx)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if suffix:
        return f"{prefix}_{suffix}_{timestamp}.xlsx"
    return f"{prefix}_{timestamp}.xlsx"

