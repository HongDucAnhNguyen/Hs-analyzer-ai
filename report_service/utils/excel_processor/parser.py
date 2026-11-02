"""Excel parsing functions

Handles parsing of TKR Excel files into structured data.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from report_service.core.models import ExcelRowData

from .constants import EXCEL_COLUMN_MAP, NUMERIC_FIELDS
from .file_cache import ExcelFileCache
from .helpers import parse_numeric_value

logger = logging.getLogger(__name__)


def find_header_row(file_content: bytes) -> int:
    """Find header row - backward compatible wrapper
    
    Args:
        file_content: Raw bytes of the Excel file
        
    Returns:
        0-indexed row number where header is located
    """
    cache = ExcelFileCache(file_content)
    return cache._find_header_row_fast()


def parse_excel_file(
    file_content: bytes
) -> Tuple[List[ExcelRowData], List[str], Optional[pd.DataFrame], Optional[str]]:
    """Parse Excel file using optimized caching
    
    Args:
        file_content: Raw bytes of the Excel file
        
    Returns:
        Tuple of (rows, errors, dataframe, sheet_name)
    """
    cache = ExcelFileCache(file_content)
    cache.load()
    
    return parse_excel_from_cache(cache)


def parse_excel_from_cache(
    cache: ExcelFileCache
) -> Tuple[List[ExcelRowData], List[str], Optional[pd.DataFrame], Optional[str]]:
    """Parse Excel data from cache - main parsing logic
    
    Args:
        cache: Loaded ExcelFileCache instance
        
    Returns:
        Tuple of (rows, errors, dataframe, sheet_name)
    """
    rows: List[ExcelRowData] = []
    errors: List[str] = []
    
    df = cache.df
    if df is None or df.empty:
        errors.append("Excel file is empty")
        return rows, errors, None, cache.sheet_name
    
    logger.info(f"Parsing {len(df)} rows, {len(df.columns)} columns")
    
    # Build column mapping (avoid creating new dict for each row)
    column_mapping = _build_column_mapping(df)
    
    # Rename columns in-place (no copy)
    df.rename(columns=column_mapping, inplace=True)
    
    # Pre-compute which columns exist
    model_fields = set(ExcelRowData.model_fields.keys()) - {'flow'}
    available_fields = model_fields & set(df.columns)
    
    # Process rows using itertuples (much faster than iterrows)
    header_row = cache.header_row
    valid_rows = 0
    
    # Convert to records for faster iteration
    records = df.to_dict('records')
    
    for idx, record in enumerate(records):
        row_num = idx + header_row + 2
        
        try:
            row_dict = _parse_record(record, available_fields)
            
            # Skip empty rows
            if not row_dict.get('ma_loai_hinh') and not row_dict.get('ma_hs') and not row_dict.get('so_tk'):
                continue
            
            row_data = ExcelRowData(**row_dict)
            row_data.flow = row_data.compute_flow()
            rows.append(row_data)
            valid_rows += 1
            
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    logger.info(f"Parsed {valid_rows} valid rows")
    
    # Return a shallow reference, not a copy
    return rows, errors, df, cache.sheet_name


def _build_column_mapping(df: pd.DataFrame) -> Dict[str, str]:
    """Build column mapping from Excel headers to model fields
    
    Args:
        df: DataFrame with original column names
        
    Returns:
        Dictionary mapping original column names to model field names
    """
    column_mapping = {}
    
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in EXCEL_COLUMN_MAP:
            column_mapping[col] = EXCEL_COLUMN_MAP[col_str]
        else:
            col_lower = col_str.lower()
            for excel_col, model_col in EXCEL_COLUMN_MAP.items():
                if col_lower == excel_col.lower():
                    column_mapping[col] = model_col
                    break
    
    return column_mapping


def _parse_record(record: Dict[str, Any], available_fields: set) -> Dict[str, Any]:
    """Parse a single record from the DataFrame
    
    Args:
        record: Dictionary from df.to_dict('records')
        available_fields: Set of fields that exist in the DataFrame
        
    Returns:
        Dictionary suitable for ExcelRowData construction
    """
    row_dict: Dict[str, Any] = {}
    
    for field in available_fields:
        val = record.get(field)
        
        if pd.isna(val) if isinstance(val, float) else val is None:
            row_dict[field] = None
        elif field in NUMERIC_FIELDS:
            row_dict[field] = parse_numeric_value(val)
        elif isinstance(val, (int, float)):
            if isinstance(val, float) and val.is_integer():
                str_val = str(int(val))
            else:
                str_val = str(val)
            
            if field == 'ma_hs' and str_val.isdigit():
                str_val = str_val.zfill(8)
            row_dict[field] = str_val
        else:
            str_val = str(val).strip()
            if field == 'ma_hs' and str_val.isdigit():
                str_val = str_val.zfill(8)
            row_dict[field] = str_val
    
    return row_dict

