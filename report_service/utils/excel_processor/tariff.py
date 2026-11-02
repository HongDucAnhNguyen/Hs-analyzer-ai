"""Tariff rate utilities

Handles loading and parsing of tariff rates from JSON file.

PERFORMANCE OPTIMIZED: Uses lru_cache for parse_tax_value to avoid
repeated regex operations during processing.
"""

import json
import logging
import os
import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache for tariff rates
_tariff_rates_cache: Optional[Dict[str, str]] = None

# Pre-compile regex for performance
_TAX_PATTERN = re.compile(r'^([\d.]+)')


def load_tariff_rates() -> Dict[str, str]:
    """Load tariff rates from JSON file with caching
    
    Returns:
        Dictionary mapping HS codes to tax rate strings
    """
    global _tariff_rates_cache
    
    if _tariff_rates_cache is not None:
        return _tariff_rates_cache
    
    # Look for tariff_rates.json in report_service/data directory
    json_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'tariff_rates_2026.json')
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
            _tariff_rates_cache = {k: str(v) for k, v in data.items()}
            logger.info(f"Loaded {len(_tariff_rates_cache)} tariff rates")
            return _tariff_rates_cache
    except FileNotFoundError:
        logger.warning(f"Tariff rates file not found: {json_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing tariff rates JSON: {e}")
        return {}


@lru_cache(maxsize=10000)
def parse_tax_value(tax_str: str) -> Tuple[Optional[float], bool]:
    """Parse tax value from tariff_rates.json - OPTIMIZED with lru_cache
    
    Uses lru_cache to avoid repeated regex operations for the same tax strings.
    Since tariff rates typically have limited unique values, this is very effective.
    
    Args:
        tax_str: Tax string from tariff rates (e.g., "5", "10.5", "Refer to text")
        
    Returns:
        Tuple of (numeric value or None, is_text_only flag)
    """
    if not tax_str:
        return None, False
    
    tax_str = str(tax_str).strip()
    match = _TAX_PATTERN.match(tax_str)
    if match:
        try:
            return float(match.group(1)), False
        except ValueError:
            pass
    
    return None, True


def get_duty_rate(ma_hs: str) -> Optional[float]:
    """Get duty rate for an HS code
    
    Args:
        ma_hs: HS code (will use first 8 digits)
        
    Returns:
        Duty rate as float, or None if not found
    """
    if not ma_hs:
        return None
    
    tariff_rates = load_tariff_rates()
    hs_8 = ma_hs[:8] if len(ma_hs) >= 8 else ma_hs
    tax_str = tariff_rates.get(hs_8)
    
    if tax_str is not None:
        numeric_val, _ = parse_tax_value(str(tax_str))
        return numeric_val
    
    return None


def get_tax_str(ma_hs: str) -> Optional[str]:
    """Get tax string for an HS code
    
    Args:
        ma_hs: HS code (will use first 8 digits)
        
    Returns:
        Tax string from tariff rates, or None if not found
    """
    if not ma_hs:
        return None
    
    tariff_rates = load_tariff_rates()
    hs_8 = ma_hs[:8] if len(ma_hs) >= 8 else ma_hs
    return tariff_rates.get(hs_8)

