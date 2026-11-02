"""Input sheet generation for Excel output

Contains functions for creating the input data sheet with:
- Original data columns
- Reference columns for HS Inconsistency and Value Variance
- Computed columns for price variance analysis

PERFORMANCE OPTIMIZATIONS (v2):
- Use ws.append() for bulk row insertion (10-20x faster)
- Apply styles in batch after data writing
- Single pass through xlsb files
- Cached style objects
"""

import logging
from io import BytesIO
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import NamedStyle

from report_service.core.models import get_flow_from_ma_loai_hinh

from openpyxl.styles import Alignment, Font, PatternFill

from .constants import (
    CELL_ALIGNMENT,
    CELL_FONT,
    CENTER_ALIGNMENT,
    HEADER_ALIGNMENT,
    HEADER_FILL,
    HEADER_FONT,
    NO_BORDER,
    NUMBER_ALIGNMENT,
    THIN_BORDER,
)
from .tariff import load_tariff_rates, parse_tax_value

# Input sheet header style - bold only, no special colors
INPUT_HEADER_FONT = Font(name="Arial", bold=True, size=10)

# New columns header style - black text on yellow background (FFE600 - same as header text yellow)
NEW_COL_HEADER_FONT = Font(name="Arial", bold=True, size=10, color="000000")
NEW_COL_HEADER_FILL = PatternFill(start_color="FFE600", end_color="FFE600", fill_type="solid")
NEW_COL_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Section header style - yellow on black, center aligned, BOLD
SECTION_HEADER_FONT = Font(name="Arial", bold=True, size=10, color="FFE600")
SECTION_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Date and number format constants
DATE_FORMAT = 'DD/MM/YYYY'
NUMBER_FORMAT = '#,##0'
NUMBER_FORMAT_DECIMAL = '#,##0.00'
PERCENTAGE_FORMAT = '0%'

# Default column width and row height for input sheet
TITLE_ROW_HEIGHT = 80
STANDARD_ROW_HEIGHT = 12
STANDARD_COLUMN_WIDTH = 12

logger = logging.getLogger(__name__)


# ============================================================================
# COLUMN OUTPUT MAPPING HELPER
# ============================================================================

def _build_output_col_map(
    max_col_orig: int,
    npl_col: Optional[int],
    skip_cols: Set[int]
) -> Tuple[Dict[int, Optional[int]], int, Optional[Tuple[int, int]]]:
    """Build mapping from original column indices to output column indices.
    
    Handles:
    - Skipping original Source/Item columns (from previous preprocess)
    - Inserting 2 new columns after Mã NPL/SP
    
    Args:
        max_col_orig: Max column in original file (1-based)
        npl_col: NPL column index (1-based) in original file, or None
        skip_cols: Set of column indices to skip (1-based)
    
    Returns:
        Tuple of:
        - col_map: Dict[orig_col -> output_col], None for skipped columns
        - max_col_output: Total number of output columns
        - source_item_cols: Tuple of (source_col, item_col) output indices, or None
    """
    col_map: Dict[int, Optional[int]] = {}
    current_out = 0
    source_item_cols = None
    
    for orig_col in range(1, max_col_orig + 1):
        if orig_col in skip_cols:
            col_map[orig_col] = None
            continue
        current_out += 1
        col_map[orig_col] = current_out
        if npl_col and orig_col == npl_col:
            # Reserve 2 positions for new Source/Item columns
            source_item_cols = (current_out + 1, current_out + 2)
            current_out += 2
    
    return col_map, current_out, source_item_cols


# ============================================================================
# COLUMN DETECTION HELPERS
# ============================================================================

def _detect_columns(row_values: List, row_idx: int) -> Dict[str, Optional[int]]:
    """Detect important column indices from header row
    
    Args:
        row_values: List of cell values from the row
        row_idx: Current row index (for logging)
        
    Returns:
        Dictionary mapping column names to their indices
    """
    result = {
        'npl_col_idx': None,
        'dieu_kien_col_idx': None,
        'ma_loai_hinh_col_idx': None,
        'ngay_dk_col_idx': None,
        'don_gia_tinh_thue_col_idx': None,
        'tong_so_luong_col_idx': None,
        'ma_hs_col_idx': None,
        'so_tk_col_idx': None,
        'ten_hang_col_idx': None,
        'ten_doi_tac_col_idx': None,
        'ma_hieu_ptvc_col_idx': None,
        'source_col_idx': None,
        'item_col_idx': None,
    }
    
    for col_idx, val in enumerate(row_values, 1):
        if not val:
            continue
            
        val_str = str(val).strip()
        val_lower = val_str.lower()
        
        # Mã NPL/SP (exclude "suggested" variants to avoid overwriting)
        if result['npl_col_idx'] is None and (
            val_str in ['Mã NPL/SP', 'Ma NPL/SP', 'Mã NPL', 'Mã SP'] or
            ('npl' in val_lower and 'suggested' not in val_lower)
        ):
            result['npl_col_idx'] = col_idx
            
        # Điều kiện giá hóa đơn
        elif val_str in ['Điều kiện giá hóa đơn', 'Dieu kien gia hoa don', 'ĐKGHĐ'] or 'điều kiện' in val_lower or 'dieu kien' in val_lower:
            result['dieu_kien_col_idx'] = col_idx
            
        # Mã loại hình
        elif val_str in ['Mã loại hình', 'Ma loai hinh', 'Loại hình'] or 'loại hình' in val_lower or 'loai hinh' in val_lower:
            result['ma_loai_hinh_col_idx'] = col_idx
            
        # Ngày ĐK
        elif val_str in ['Ngày ĐK', 'Ngay DK', 'Ngày đăng ký', 'Ngày ĐK TK'] or 'ngày đk' in val_lower or 'ngay dk' in val_lower or 'ngày đăng ký' in val_lower:
            result['ngay_dk_col_idx'] = col_idx
            
        # Đơn giá tính thuế
        elif val_str in ['Đơn giá tính thuế', 'Don gia tinh thue', 'ĐƠN GIÁ TÍNH THUẾ'] or 'đơn giá tính thuế' in val_lower or 'don gia tinh thue' in val_lower or ('đơn giá' in val_lower and 'thuế' in val_lower):
            result['don_gia_tinh_thue_col_idx'] = col_idx
            
        # Tổng số lượng
        elif result['tong_so_luong_col_idx'] is None and (
            val_str in ['Tổng số lượng', 'Tong so luong', 'TỔNG SỐ LƯỢNG', 'Tổng SL', 'TSL'] or 
            val_lower.startswith('tổng số lượng') or val_lower.startswith('tong so luong') or
            val_lower.startswith('tổng sl') or val_lower.startswith('tsl') or
            'tổng số lượng' in val_lower or 'tong so luong' in val_lower or 
            (('số lượng' in val_lower or 'so luong' in val_lower) and 'tổng' in val_lower)
        ):
            result['tong_so_luong_col_idx'] = col_idx
            
        # Mã HS
        elif result['ma_hs_col_idx'] is None and (
            val_str in ['Mã HS', 'Ma HS', 'HS Code', 'MÃ HS', 'HS', 'Mã số HS'] or 
            val_lower == 'mã hs' or val_lower == 'ma hs' or val_lower == 'hs' or
            val_lower.startswith('mã hs') or val_lower.startswith('ma hs') or
            'hs code' in val_lower or 'mã số hs' in val_lower or
            (('hs' in val_lower or 'h s' in val_lower) and ('ma' in val_lower or 'mã' in val_lower) and 'npl' not in val_lower) or
            val_lower.strip() in ['mã hs', 'ma hs', 'hs', 'mahs', 'mãhs']
        ):
            result['ma_hs_col_idx'] = col_idx
            logger.info(f"Found HS column: '{val_str}' at col {col_idx}")
            
        # Số TK
        elif val_str in ['Số TK', 'So TK', 'SỐ TK', 'Số tờ khai'] or val_lower == 'số tk' or val_lower == 'so tk':
            result['so_tk_col_idx'] = col_idx
            
        # Tên hàng
        elif result['ten_hang_col_idx'] is None and (
            val_str in ['Tên hàng', 'Ten hang', 'TÊN HÀNG'] or 
            val_lower == 'tên hàng' or val_lower == 'ten hang'
        ):
            result['ten_hang_col_idx'] = col_idx
        
        # Tên đối tác
        elif result['ten_doi_tac_col_idx'] is None and (
            val_str in ['Tên đối tác', 'Ten doi tac', 'TÊN ĐỐI TÁC'] or
            val_lower == 'tên đối tác' or val_lower == 'ten doi tac'
        ):
            result['ten_doi_tac_col_idx'] = col_idx
        
        # Mã hiệu PTVC
        elif result['ma_hieu_ptvc_col_idx'] is None and (
            val_str in ['Mã hiệu PTVC', 'Ma hieu PTVC', 'MÃ HIỆU PTVC'] or
            val_lower == 'mã hiệu ptvc' or val_lower == 'ma hieu ptvc' or
            'ptvc' in val_lower
        ):
            result['ma_hieu_ptvc_col_idx'] = col_idx
        
        # Mã NPL/SP (Suggested) / Source (from preprocess)
        elif result['source_col_idx'] is None and (
            val_str in ['Source', 'source', 'SOURCE', 'Nguồn', 'Mã NPL/SP (Suggested)', 'Mã NPL/SP\n(Suggested)'] or
            val_lower == 'source' or val_lower == 'nguồn' or
            'suggested' in val_lower or 'mã npl/sp (suggested)' in val_lower
        ):
            result['source_col_idx'] = col_idx
        
        # Rationale / Item / Final Item Code (from preprocess)
        elif result['item_col_idx'] is None and (
            val_str in ['Rationale', 'rationale', 'RATIONALE', 'Final Item Code', 'Item', 'item', 'ITEM', 'Final_Item_Code'] or
            val_lower == 'rationale' or val_lower == 'final item code' or val_lower == 'item'
        ):
            result['item_col_idx'] = col_idx
        
        # Track ALL preprocess/extra columns for skipping (separate from elif chain)
        # This catches columns like "Rationale" even when item_col_idx is already set
        # Normalize val_lower by removing newlines and extra spaces for robust matching
        val_normalized = ' '.join(val_lower.split())  # "final item\ncode" → "final item code"
        if (val_normalized in ['source', 'rationale', 'final_item_code', 'final item code'] or
            'suggested' in val_lower or
            'final item' in val_normalized):
            result.setdefault('preprocess_skip_cols', set()).add(col_idx)
            logger.info(f"[DETECT] Found preprocess column at {col_idx}: '{val_str[:30]}...'" if len(val_str) > 30 else f"[DETECT] Found preprocess column at {col_idx}: '{val_str}'")
    
    return result


def _extract_row_data(row_values: List, col_indices: Dict[str, Optional[int]]) -> Dict:
    """Extract data from a row based on column indices
    
    Args:
        row_values: List of cell values (0-indexed)
        col_indices: Dictionary of column indices (1-indexed)
        
    Returns:
        Dictionary with extracted values
    """
    data = {
        'flow': '',
        'dieu_kien': '',
        'npl': '',
        'so_tk': '',
        'tsl': '',
        'ma_hs': '',
        'ten_hang': '',
        'ten_doi_tac': '',
        'ma_hieu_ptvc': '',
        'date': None,
        'price': None,
        'source': '',
        'item': '',
    }
    
    # Helper to get value by 1-indexed column
    def get_val(col_key: str):
        col_idx = col_indices.get(col_key)
        if col_idx and col_idx <= len(row_values):
            return row_values[col_idx - 1]
        return None
    
    # Ma loai hinh -> flow
    val = get_val('ma_loai_hinh_col_idx')
    if val:
        data['flow'] = get_flow_from_ma_loai_hinh(str(val).strip()).value
    
    # Dieu kien gia hoa don
    val = get_val('dieu_kien_col_idx')
    if val:
        data['dieu_kien'] = str(val).strip()
    
    # NPL/SP
    val = get_val('npl_col_idx')
    if val:
        data['npl'] = str(val).strip()
    
    # So TK
    val = get_val('so_tk_col_idx')
    if val:
        data['so_tk'] = str(int(val) if isinstance(val, float) else val).strip()
    
    # Tong so luong
    val = get_val('tong_so_luong_col_idx')
    if val:
        data['tsl'] = str(val).strip()
    
    # Ma HS
    val = get_val('ma_hs_col_idx')
    if val:
        ma_hs_str = str(val).strip()
        if ma_hs_str.replace('.', '').replace(',', '').isdigit():
            ma_hs_str = str(int(float(ma_hs_str))).zfill(8)
        data['ma_hs'] = ma_hs_str
    
    # Ten hang
    val = get_val('ten_hang_col_idx')
    if val:
        data['ten_hang'] = str(val).strip()
    
    # Ten doi tac
    val = get_val('ten_doi_tac_col_idx')
    if val:
        data['ten_doi_tac'] = str(val).strip()
    
    # Ma hieu PTVC
    val = get_val('ma_hieu_ptvc_col_idx')
    if val:
        data['ma_hieu_ptvc'] = str(val).strip()
    
    # Ngay DK (date)
    val = get_val('ngay_dk_col_idx')
    if isinstance(val, (int, float)):
        data['date'] = float(val)
    elif val is not None:
        try:
            data['date'] = float(val)
        except (ValueError, TypeError):
            pass
    
    # Don gia tinh thue (price)
    val = get_val('don_gia_tinh_thue_col_idx')
    if isinstance(val, (int, float)):
        data['price'] = float(val)
    elif val is not None:
        try:
            data['price'] = float(str(val).replace(',', ''))
        except (ValueError, TypeError):
            pass
    
    # Source (from preprocess)
    val = get_val('source_col_idx')
    if val:
        data['source'] = str(val).strip()
    
    # Item / Final Item Code (from preprocess)
    val = get_val('item_col_idx')
    if val:
        data['item'] = str(val).strip()
    
    return data


def _compute_min_max_values(
    row_data_map: Dict[int, Dict],
    index_groups: Dict[str, List[Tuple[int, Dict]]]
) -> Dict[int, Dict]:
    """Pre-compute MIN/MAX values for each row
    
    Args:
        row_data_map: Dictionary mapping row indices to their data
        index_groups: Dictionary grouping rows by their index value
        
    Returns:
        Dictionary mapping row indices to computed MIN/MAX values
    """
    computed_values = {}
    
    for row_idx, data in row_data_map.items():
        current_date = data['date']
        current_index = data['index']
        
        if current_date is None:
            computed_values[row_idx] = {
                'min_before': 0, 'max_before': 0,
                'min_after': 0, 'max_after': 0,
            }
            continue
        
        # Get all rows with same index
        same_index_rows = index_groups.get(current_index, [])
        
        # Filter for 60-day BEFORE window: date <= current AND date > (current - 60)
        prices_before = [
            r[1]['price'] for r in same_index_rows
            if r[1]['date'] is not None and r[1]['price'] is not None
            and r[1]['date'] <= current_date and r[1]['date'] > (current_date - 60)
        ]
        
        # Filter for 60-day AFTER window: date >= current AND date < (current + 60)
        prices_after = [
            r[1]['price'] for r in same_index_rows
            if r[1]['date'] is not None and r[1]['price'] is not None
            and r[1]['date'] >= current_date and r[1]['date'] < (current_date + 60)
        ]
        
        computed_values[row_idx] = {
            'min_before': min(prices_before) if prices_before else 0,
            'max_before': max(prices_before) if prices_before else 0,
            'min_after': min(prices_after) if prices_after else 0,
            'max_after': max(prices_after) if prices_after else 0,
        }
    
    return computed_values


def _setup_new_columns(ws, section_row_idx: int, header_row_idx: int, max_col: int, filter_row_idx: Optional[int] = None, col_indices: Optional[Dict] = None, source_item_cols: Optional[Tuple[int, int]] = None, preprocess_row_idx: Optional[int] = None, has_preprocess: bool = False, num_flags_c: int = 1):
    """Setup new columns with section headers (1.1/1.2, 2.1, 2.2, 2.3, 3.1, 3.2)
    
    Args:
        ws: Worksheet
        section_row_idx: Section header row index (row 8)
        header_row_idx: Column header row index (row 10)
        max_col: Max column of original data (including inserted source/item cols)
        filter_row_idx: Filter row index (row 11) - for writing default/active formulas
        col_indices: Detected column indices from original data (for dynamic formula generation)
        source_item_cols: Tuple of (source_col, item_col) column indices inserted next to Mã NPL/SP
        preprocess_row_idx: Row index for preprocess formulas (row 9, above header) - templates only
        has_preprocess: If True, the 4 MIN/MAX 60-day formulas at filter_row use preprocess versions
                       (overwriting default). Only affects columns with 2 formula types.
        num_flags_c: Number of Flag-C columns (dynamic based on actual data, default 1)
    
    Returns column indices for all new columns
    """
    # FIXED layout: Separator ALWAYS at BE (col 57), Flag ALWAYS at BF (col 58)
    FIXED_SEPARATOR_COL = 57  # BE - always separator here
    FIXED_FLAG_COL = 58       # BF - always Flag here
    
    empty_col_0 = FIXED_SEPARATOR_COL     # Always BE (57)
    sec_11_flag_col = FIXED_FLAG_COL      # Always BF (58)
    
    # Empty separator after Flag
    empty_col_1 = sec_11_flag_col + 1
    
    # Section 2.1: RPT, "&" (for VLOOKUP), Flag
    sec_21_rpt_col = empty_col_1 + 1
    sec_21_ampersand_col = sec_21_rpt_col + 1
    sec_21_flag_col = sec_21_ampersand_col + 1
    
    # Empty separator
    empty_col_3 = sec_21_flag_col + 1
    
    # Section 2.2: Flow, MIN/MAX values, etc.
    flow_col = empty_col_3 + 1
    
    min_before_col = flow_col + 1
    max_before_col = min_before_col + 1
    min_after_col = max_before_col + 1
    max_after_col = min_after_col + 1
    min_120_col = max_after_col + 1
    max_120_col = min_120_col + 1
    variance_col = max_120_col + 1
    hs_max_duty_col = variance_col + 1
    duty_rate_col = hs_max_duty_col + 1
    impact_col = duty_rate_col + 1
    
    # Empty separator
    empty_col_4 = impact_col + 1
    
    # Section 2.3: Flag
    sec_23_flag_col = empty_col_4 + 1
    
    # Empty separator
    empty_col_5 = sec_23_flag_col + 1
    
    # Section 3.1: Transaction notes, Chemical notes, &, Exclusion, Flag 1-5, Flag 1-C (dynamic count)
    NUM_FLAGS = 5  # Flag 1-5
    NUM_FLAGS_C = max(num_flags_c, 1) if num_flags_c > 0 else 0  # Use dynamic count, minimum 1 if any, 0 if none
    
    sec_31_transaction_notes_col = empty_col_5 + 1
    sec_31_chemical_notes_col = sec_31_transaction_notes_col + 1
    sec_31_ampersand_col = sec_31_chemical_notes_col + 1
    sec_31_exclusion_col = sec_31_ampersand_col + 1
    
    # Flag 1-5 columns
    sec_31_flag_cols = []
    current_col = sec_31_exclusion_col + 1
    for i in range(NUM_FLAGS):
        sec_31_flag_cols.append(current_col)
        current_col += 1
    
    # Flag 1-C to 3-C columns (chemical flags)
    sec_31_flag_c_cols = []
    for i in range(NUM_FLAGS_C):
        sec_31_flag_c_cols.append(current_col)
        current_col += 1
    
    last_col = current_col - 1
    
    # For backward compatibility, keep sec_31_flag_col pointing to first flag
    sec_31_flag_col = sec_31_flag_cols[0] if sec_31_flag_cols else sec_31_exclusion_col + 1
    
    # Set column widths
    column_widths = {
        empty_col_0: 2,           # BE (57) - separator
        sec_11_flag_col: 12,      # BF (58) - Yellow header
        empty_col_1: 2,
        sec_21_rpt_col: 12,       # Yellow header
        sec_21_ampersand_col: 25, # Yellow header - "&" for VLOOKUP
        sec_21_flag_col: 12,      # Yellow header
        empty_col_3: 2,
        flow_col: 10,
        min_before_col: 15,
        max_before_col: 15,
        min_after_col: 15,
        max_after_col: 15,
        min_120_col: 15,
        max_120_col: 15,
        variance_col: 12,
        hs_max_duty_col: 12,      # Yellow header
        duty_rate_col: 12,        # Yellow header
        impact_col: 12,           # Yellow header
        empty_col_4: 2,
        sec_23_flag_col: 12,      # Yellow header
        empty_col_5: 2,
        sec_31_transaction_notes_col: 18,  # Transaction notes
        sec_31_chemical_notes_col: 15,     # Chemical notes
        sec_31_ampersand_col: 25,          # & for VLOOKUP
        sec_31_exclusion_col: 15,          # Exclusion
    }
    
    # Add widths for Flag columns
    for flag_col in sec_31_flag_cols:
        column_widths[flag_col] = 12
    for flag_c_col in sec_31_flag_c_cols:
        column_widths[flag_c_col] = 12
    
    for col_idx, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Write section headers at section_row_idx (1 row gap from column headers)
    # Section headers: yellow on black, CENTER aligned in first cell only (no merge)
    
    # Section 1.1/1.2
    cell = ws.cell(row=section_row_idx, column=sec_11_flag_col, value="1.1 / 1.2")
    cell.font = SECTION_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = SECTION_HEADER_ALIGNMENT
    
    # Section 2.1 - text centered in first cell, fill all cells in range
    cell = ws.cell(row=section_row_idx, column=sec_21_rpt_col, value="2.1")
    cell.font = SECTION_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = SECTION_HEADER_ALIGNMENT
    # Fill remaining cells in 2.1 range (RPT, "&", Flag)
    for col in range(sec_21_rpt_col + 1, sec_21_flag_col + 1):
        cell = ws.cell(row=section_row_idx, column=col, value="")
        cell.fill = HEADER_FILL
    
    # Section 2.2 - text centered in first cell, fill all cells in range
    cell = ws.cell(row=section_row_idx, column=flow_col, value="2.2")
    cell.font = SECTION_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = SECTION_HEADER_ALIGNMENT
    # Fill remaining cells in 2.2 range
    for col in range(flow_col + 1, impact_col + 1):
        cell = ws.cell(row=section_row_idx, column=col, value="")
        cell.fill = HEADER_FILL
    
    # Section 2.3
    cell = ws.cell(row=section_row_idx, column=sec_23_flag_col, value="2.3")
    cell.font = SECTION_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = SECTION_HEADER_ALIGNMENT
    
    # Section 3.1 (Transaction notes, Chemical notes, &, Exclusion, Flags)
    cell = ws.cell(row=section_row_idx, column=sec_31_transaction_notes_col, value="3.1")
    cell.font = SECTION_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = SECTION_HEADER_ALIGNMENT
    # Fill remaining cells in 3.1 range
    for col in range(sec_31_transaction_notes_col + 1, last_col + 1):
        cell = ws.cell(row=section_row_idx, column=col, value="")
        cell.fill = HEADER_FILL
    
    # Write column headers at header_row_idx
    # Empty separators
    for col in [empty_col_0, empty_col_1, empty_col_3, empty_col_4, empty_col_5]:
        ws.cell(row=header_row_idx, column=col, value="").border = NO_BORDER
    
    # Section 1.1/1.2 header: Flag
    cell = ws.cell(row=header_row_idx, column=sec_11_flag_col, value="Flag")
    cell.font = NEW_COL_HEADER_FONT
    cell.fill = NEW_COL_HEADER_FILL
    cell.alignment = NEW_COL_HEADER_ALIGNMENT
    cell.border = THIN_BORDER
    
    # Section 2.1 headers: RPT, "&", Flag
    for col, text in [(sec_21_rpt_col, "RPT"), (sec_21_ampersand_col, "&"), (sec_21_flag_col, "Flag")]:
        cell = ws.cell(row=header_row_idx, column=col, value=text)
        cell.font = NEW_COL_HEADER_FONT
        cell.fill = NEW_COL_HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Section 2.2 headers - YELLOW text on BLACK background
    sec_22_headers_dark = [
        (flow_col, "Flow"),
        (min_before_col, "MIN value in\nthe 60-day period,\nBEFORE the\nCD date"),
        (max_before_col, "MAX value in\nthe 60-day period,\nBEFORE the\nCD date"),
        (min_after_col, "MIN value in\nthe 60-day period,\nAFTER the CD\ndate"),
        (max_after_col, "MAX value in\nthe 60-day period,\nAFTER the CD\ndate"),
        (min_120_col, "MIN value in\nthe\nentire 120-day\nperiod"),
        (max_120_col, "MAX value in\nthe\nentire 120-day\nperiod"),
        (variance_col, "Variance\nRange\n(120-day\nperiod)"),
    ]
    
    # Yellow text on black background
    for col_idx, header_text in sec_22_headers_dark:
        cell = ws.cell(row=header_row_idx, column=col_idx, value=header_text)
        cell.font = HEADER_FONT  # Yellow text
        cell.fill = HEADER_FILL  # Black background
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Last 3 columns - BLACK text on YELLOW background
    sec_22_headers_light = [
        (hs_max_duty_col, "HS Code\n(with highest\nImport Duty\nrate)"),
        (duty_rate_col, "Import Duty\nrate (MAX)"),
        (impact_col, "Impact\namount"),
    ]
    
    for col_idx, header_text in sec_22_headers_light:
        cell = ws.cell(row=header_row_idx, column=col_idx, value=header_text)
        cell.font = NEW_COL_HEADER_FONT  # Black text
        cell.fill = NEW_COL_HEADER_FILL  # Yellow background
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Section 2.3 Flag header
    cell = ws.cell(row=header_row_idx, column=sec_23_flag_col, value="Flag")
    cell.font = NEW_COL_HEADER_FONT
    cell.fill = NEW_COL_HEADER_FILL
    cell.alignment = NEW_COL_HEADER_ALIGNMENT
    cell.border = THIN_BORDER
    
    # Section 3.1 headers: Transaction notes, Chemical notes, &, Exclusion
    sec_31_headers = [
        (sec_31_transaction_notes_col, "Transaction\nnotes"),
        (sec_31_chemical_notes_col, "Chemical\nnotes"),
        (sec_31_ampersand_col, "&"),
        (sec_31_exclusion_col, "Exclusion"),
    ]
    for col, text in sec_31_headers:
        cell = ws.cell(row=header_row_idx, column=col, value=text)
        cell.font = NEW_COL_HEADER_FONT
        cell.fill = NEW_COL_HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Section 3.1 Flag 1-5 headers
    for i, flag_col in enumerate(sec_31_flag_cols, 1):
        cell = ws.cell(row=header_row_idx, column=flag_col, value=f"Flag {i}")
        cell.font = NEW_COL_HEADER_FONT
        cell.fill = NEW_COL_HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Section 3.1 Flag 1-C to 3-C headers (red background with gray text #c4c4cd)
    FLAG_C_FILL = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    FLAG_C_FONT = Font(name="Arial", bold=True, size=10, color="C4C4CD")
    for i, flag_c_col in enumerate(sec_31_flag_c_cols, 1):
        cell = ws.cell(row=header_row_idx, column=flag_c_col, value=f"Flag {i}-C")
        cell.font = FLAG_C_FONT
        cell.fill = FLAG_C_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Write formulas as text in TWO rows:
    # Row preprocess_row_idx (9): Preprocess formula TEMPLATES (blue bold) - reference only
    # Row filter_row_idx (11): ACTIVE formulas (red bold) - default uses NPL/Flow/HS criteria
    #   If has_preprocess=True, the 4 MIN/MAX 60-day cols at filter_row are overwritten
    #   with preprocess versions (Source/Item criteria). Only those cols that have 2 types.
    if filter_row_idx:
        # Font for formula text (bold red for active, bold blue for preprocess template)
        FORMULA_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")
        PREPROCESS_FORMULA_FONT = Font(name="Arial", size=10, bold=True, color="0000FF")
        
        # Get column letters for new columns (for MIN/MAX 120-day and variance formulas)
        min_before_letter = get_column_letter(min_before_col)
        max_before_letter = get_column_letter(max_before_col)
        min_after_letter = get_column_letter(min_after_col)
        max_after_letter = get_column_letter(max_after_col)
        min_120_letter = get_column_letter(min_120_col)
        max_120_letter = get_column_letter(max_120_col)
        
        # Build dynamic column letters from detected col_indices
        npl_letter = get_column_letter(col_indices['npl_col_idx']) if col_indices and col_indices.get('npl_col_idx') else 'U'
        don_gia_letter = get_column_letter(col_indices['don_gia_tinh_thue_col_idx']) if col_indices and col_indices.get('don_gia_tinh_thue_col_idx') else 'Z'
        ma_hs_letter = get_column_letter(col_indices['ma_hs_col_idx']) if col_indices and col_indices.get('ma_hs_col_idx') else 'R'
        ngay_dk_letter = get_column_letter(col_indices['ngay_dk_col_idx']) if col_indices and col_indices.get('ngay_dk_col_idx') else 'C'
        rpt_letter = get_column_letter(sec_21_rpt_col)
        ampersand_letter = get_column_letter(sec_21_ampersand_col)
        flow_letter = get_column_letter(flow_col)
        source_letter = get_column_letter(source_item_cols[0]) if source_item_cols else 'BG'
        item_letter = get_column_letter(source_item_cols[1]) if source_item_cols else 'BH'
        ten_doi_tac_letter = get_column_letter(col_indices['ten_doi_tac_col_idx']) if col_indices and col_indices.get('ten_doi_tac_col_idx') else 'AK'
        dieu_kien_letter = get_column_letter(col_indices['dieu_kien_col_idx']) if col_indices and col_indices.get('dieu_kien_col_idx') else 'AB'
        ma_loai_hinh_letter = get_column_letter(col_indices['ma_loai_hinh_col_idx']) if col_indices and col_indices.get('ma_loai_hinh_col_idx') else 'E'
        
        # First data row (always row 12 with fixed layout)
        data_row = filter_row_idx + 1
        
        # Helper to build MINIFS/MAXIFS formula for a given check column (NPL or Source)
        # Pattern from CSV: =IF(ISBLANK(check), FUNC(price, check="", RPT="Not related", Flow=flow, HS=hs, Date>=..., Date<=...), FUNC(price, check=val, ...))
        def _build_minmax(func, check_letter, period_op, period_val):
            """Build MINIFS/MAXIFS formula matching CSV structure.
            func: 'MINIFS' or 'MAXIFS'
            check_letter: column letter for ISBLANK check and first criteria (NPL or Source)
            period_op: 'before' or 'after' (determines date range direction)
            """
            if period_op == 'before':
                date_start = f"\">=\"&({ngay_dk_letter}{data_row}-60)"
                date_end = f"\"<=\"&{ngay_dk_letter}{data_row}"
            else:  # after
                date_start = f"\">=\"&{ngay_dk_letter}{data_row}"
                date_end = f"\"<=\"&({ngay_dk_letter}{data_row}+60)"
            
            blank_branch = (
                f"{func}(${don_gia_letter}:${don_gia_letter},"
                f"${check_letter}:${check_letter},\"\","
                f"${rpt_letter}:${rpt_letter},\"Not related\","
                f"${flow_letter}:${flow_letter},{flow_letter}{data_row},"
                f"${ma_hs_letter}:${ma_hs_letter},{ma_hs_letter}{data_row},"
                f"${ngay_dk_letter}:${ngay_dk_letter},{date_start},"
                f"${ngay_dk_letter}:${ngay_dk_letter},{date_end})"
            )
            filled_branch = (
                f"{func}(${don_gia_letter}:${don_gia_letter},"
                f"${check_letter}:${check_letter},{check_letter}{data_row},"
                f"${rpt_letter}:${rpt_letter},\"Not related\","
                f"${flow_letter}:${flow_letter},{flow_letter}{data_row},"
                f"${ma_hs_letter}:${ma_hs_letter},{ma_hs_letter}{data_row},"
                f"${ngay_dk_letter}:${ngay_dk_letter},{date_start},"
                f"${ngay_dk_letter}:${ngay_dk_letter},{date_end})"
            )
            return f"'=IF(ISBLANK({check_letter}{data_row}), {blank_branch}, {filled_branch})"
        
        # === NPL-based formulas (CSV row 2 pattern): ISBLANK(NPL), criteria: NPL+RPT+Flow+HS+Date ===
        npl_min_before = _build_minmax('MINIFS', npl_letter, 'before', 60)
        npl_max_before = _build_minmax('MAXIFS', npl_letter, 'before', 60)
        npl_min_after  = _build_minmax('MINIFS', npl_letter, 'after', 60)
        npl_max_after  = _build_minmax('MAXIFS', npl_letter, 'after', 60)
        npl_ampersand  = f"'={npl_letter}{data_row}&\"/\"&{ten_doi_tac_letter}{data_row}&\"/\"&{flow_letter}{data_row}&\"/\"&{dieu_kien_letter}{data_row}"
        
        # === Source-based formulas (CSV row 4 pattern): ISBLANK(Source), criteria: Source+RPT+Flow+HS+Date ===
        src_min_before = _build_minmax('MINIFS', source_letter, 'before', 60)
        src_max_before = _build_minmax('MAXIFS', source_letter, 'before', 60)
        src_min_after  = _build_minmax('MINIFS', source_letter, 'after', 60)
        src_max_after  = _build_minmax('MAXIFS', source_letter, 'after', 60)
        # For ampersand when has_preprocess=True: use Source column (filled by LLM prefill)
        # This ensures the & value matches the data in 2.1 sheet which also uses the prefilled values
        src_ampersand  = f"'={source_letter}{data_row}&\"/\"&{ten_doi_tac_letter}{data_row}&\"/\"&{flow_letter}{data_row}&\"/\"&{dieu_kien_letter}{data_row}"
        
        # === SHARED formulas (same regardless of NPL or Source) ===
        formula_min_120 = f"'=MIN({min_before_letter}{data_row}:{max_after_letter}{data_row})"
        formula_max_120 = f"'=MAX({min_before_letter}{data_row}:{max_after_letter}{data_row})"
        formula_variance = f"'=IFERROR(({max_120_letter}{data_row}-{min_120_letter}{data_row})/{min_120_letter}{data_row},\"-\")"
        # RPT formula: VLOOKUP to get value from Column L of sheet 2.1 using & as lookup key
        # O=& (lookup), L=RPT. Since L is to the LEFT of O, use VLOOKUP with CHOOSE to create virtual array
        # CHOOSE({1,2},'2.1'!$O:$O,'2.1'!$L:$L) creates array where col1=O (lookup), col2=L (return)
        formula_21_rpt = f"'=IFERROR(VLOOKUP({ampersand_letter}{data_row},CHOOSE({{1,2}},'2.1'!$O:$O,'2.1'!$L:$L),2,0),\"To fill\")"
        formula_21_flag = f"'=IFERROR(VLOOKUP({ampersand_letter}{data_row},'2.1'!$O:$P,COLUMNS('2.1'!$O:$P),0),\"\")"
        
        # --- Row filter_row_idx (11): ACTIVE formulas (always written, red bold) ---
        # When has_preprocess=True (Source filled by prefill): use Source-based formulas
        # When has_preprocess=False (Source empty): use NPL-based formulas as fallback
        active_min_before = src_min_before if has_preprocess else npl_min_before
        active_max_before = src_max_before if has_preprocess else npl_max_before
        active_min_after  = src_min_after  if has_preprocess else npl_min_after
        active_max_after  = src_max_after  if has_preprocess else npl_max_after
        active_ampersand  = src_ampersand  if has_preprocess else npl_ampersand
        
        active_formula_cols = [
            (sec_21_rpt_col, formula_21_rpt),  # RPT formula to get value from sheet 2.1
            (sec_21_ampersand_col, active_ampersand),
            (sec_21_flag_col, formula_21_flag),
            (min_before_col, active_min_before),
            (max_before_col, active_max_before),
            (min_after_col, active_min_after),
            (max_after_col, active_max_after),
            (min_120_col, formula_min_120),
            (max_120_col, formula_max_120),
            (variance_col, formula_variance),
        ]
        
        for col_idx, formula in active_formula_cols:
            cell = ws.cell(row=filter_row_idx, column=col_idx, value=formula)
            cell.font = FORMULA_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        
        ws.row_dimensions[filter_row_idx].height = STANDARD_ROW_HEIGHT
        
        # --- Row preprocess_row_idx (9): LEFT EMPTY ---
        # Reserved for user reference. The NPL/Source formula variants above
        # are selected at generation time based on has_preprocess flag.
        
        # === Section 3.1 formulas ===
        # Get column letter for & column in section 3.1
        sec_31_ampersand_letter = get_column_letter(sec_31_ampersand_col)
        
        # & column formula: fixed column letters U, V, B
        # - With LLM/rule base filter (has_preprocess): =V{row}&"/"&B{row}  (V=Mã NPL/SP suggested)
        # - Default (no filter): =U{row}&"/"&B{row}  (U=Tên hàng original)
        # - B = Số TK
        if has_preprocess:
            # LLM/rule base filter used: V (Mã NPL/SP suggested) / B (Số TK)
            formula_31_ampersand = f"'=V{data_row}&\"/\"&B{data_row}"
        else:
            # Default: U (Tên hàng) / B (Số TK)
            formula_31_ampersand = f"'=U{data_row}&\"/\"&B{data_row}"
        
        # Exclusion formula: =VLOOKUP(&,'3.1'!$O:$P,COLUMNS('3.1'!$O:$P),0)
        formula_31_exclusion = f"'=IFERROR(VLOOKUP({sec_31_ampersand_letter}{data_row},'3.1'!$O:$P,COLUMNS('3.1'!$O:$P),0),\"\")"
        
        # Flag 1-5 formulas: VLOOKUP to sheet 3.1
        # New 3.1 structure (NO separator between VN Tariff and NTM for chemical):
        # O=&, P=Exclusion, Q=Reason, R=TRAIN ref, S=VN Tariff ref
        # T=NTM for chemical, U=CAS No., V=CAS sources
        # W=empty, X=Measure 1, Y=Client's fulfilment 1, Z=Assessment 1, AA=Flag 1
        # AB=empty, AC=Measure 2, AD=Client's fulfilment 2, AE=Assessment 2, AF=Flag 2
        # AG=empty, AH=Measure 3, AI=Client's fulfilment 3, AJ=Assessment 3, AK=Flag 3
        # AL=empty, AM=Measure 4, AN=Client's fulfilment 4, AO=Assessment 4, AP=Flag 4
        # AQ=empty, AR=Measure 5, AS=Client's fulfilment 5, AT=Assessment 5, AU=Flag 5
        flag_end_letters = ['AA', 'AF', 'AK', 'AP', 'AU']
        formulas_31_flags = []
        for i, end_letter in enumerate(flag_end_letters):
            formula = f"'=IFERROR(VLOOKUP({sec_31_ampersand_letter}{data_row},'3.1'!$O:${end_letter},COLUMNS('3.1'!$O:${end_letter}),0),\"\")"
            formulas_31_flags.append(formula)
        
        # Flag 1-C to 3-C formulas: VLOOKUP to sheet 3.1 (Chemical section)
        # AV=empty, AW=Chemical measure 1, AX=Client's fulfilment 1-C, AY=Assessment 1-C, AZ=Flag 1-C
        # BA=empty, BB=Chemical measure 2, BC=Client's fulfilment 2-C, BD=Assessment 2-C, BE=Flag 2-C
        # BF=empty, BG=Chemical measure 3, BH=Client's fulfilment 3-C, BI=Assessment 3-C, BJ=Flag 3-C
        flag_c_end_letters = ['AZ', 'BE', 'BJ']
        formulas_31_flags_c = []
        for i, end_letter in enumerate(flag_c_end_letters):
            formula = f"'=IFERROR(VLOOKUP({sec_31_ampersand_letter}{data_row},'3.1'!$O:${end_letter},COLUMNS('3.1'!$O:${end_letter}),0),\"\")"
            formulas_31_flags_c.append(formula)
        
        # Write section 3.1 formulas
        sec_31_formula_cols = [
            (sec_31_ampersand_col, formula_31_ampersand),
            (sec_31_exclusion_col, formula_31_exclusion),
        ]
        # Add Flag 1-5 formulas
        for i, flag_col in enumerate(sec_31_flag_cols):
            if i < len(formulas_31_flags):
                sec_31_formula_cols.append((flag_col, formulas_31_flags[i]))
        
        # Add Flag 1-C to 3-C formulas
        for i, flag_c_col in enumerate(sec_31_flag_c_cols):
            if i < len(formulas_31_flags_c):
                sec_31_formula_cols.append((flag_c_col, formulas_31_flags_c[i]))
        
        for col_idx, formula in sec_31_formula_cols:
            cell = ws.cell(row=filter_row_idx, column=col_idx, value=formula)
            cell.font = FORMULA_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    
    return {
        'empty_col_0': empty_col_0,
        'sec_11_flag_col': sec_11_flag_col,
        'empty_col_1': empty_col_1,
        'sec_21_rpt_col': sec_21_rpt_col,
        'sec_21_ampersand_col': sec_21_ampersand_col,
        'sec_21_flag_col': sec_21_flag_col,
        'empty_col_3': empty_col_3,
        'flow_col': flow_col,
        'min_before_col': min_before_col,
        'max_before_col': max_before_col,
        'min_after_col': min_after_col,
        'max_after_col': max_after_col,
        'min_120_col': min_120_col,
        'max_120_col': max_120_col,
        'variance_col': variance_col,
        'hs_max_duty_col': hs_max_duty_col,
        'duty_rate_col': duty_rate_col,
        'impact_col': impact_col,
        'empty_col_4': empty_col_4,
        'sec_23_flag_col': sec_23_flag_col,
        'empty_col_5': empty_col_5,
        'sec_31_transaction_notes_col': sec_31_transaction_notes_col,
        'sec_31_chemical_notes_col': sec_31_chemical_notes_col,
        'sec_31_ampersand_col': sec_31_ampersand_col,
        'sec_31_exclusion_col': sec_31_exclusion_col,
        'sec_31_flag_col': sec_31_flag_col,  # First flag (backward compatibility)
        'sec_31_flag_cols': sec_31_flag_cols,  # List of Flag 1-5 columns
        'sec_31_flag_c_cols': sec_31_flag_c_cols,  # List of Flag 1-C to 3-C columns
        'last_col': last_col,
    }


def _write_computed_row(
    ws, row_idx: int, 
    data: Dict, 
    computed: Dict,
    cols: Dict,
    npl_to_ip_hs: Dict[str, str],
    flow_dieu_kien_npl_to_ip_vv: Dict[str, str],
    npl_to_hs_codes: Dict[str, Set[str]],
    tariff_rates: Dict[str, str],
    tong_so_luong_col_idx: Optional[int],
    npl_to_23_flag: Dict[str, str] = None,
    enabled_sections: Optional[Set[str]] = None,
    flag_31_mapping: Dict[Tuple, str] = None,
    flag_32_mapping: Dict[Tuple, str] = None,
    npl_col_idx: Optional[int] = None,
    exclusion_31_mapping: Dict[Tuple, str] = None,
    source_item_cols: Optional[Tuple[int, int]] = None
):
    """Write computed values to a row
    
    Args:
        enabled_sections: Set of enabled section numbers ("1", "2", "3").
                         None means all sections enabled.
                         - "1" enables Tariff Classification (1.1/1.2)
                         - "2" enables Customs Valuation (2.1, 2.2, 2.3)
                         - "3" enables Non-Tariff Measures (3.1, 3.2)
        flag_31_mapping: Mapping for section 3.1 flag - key is (flow, hs_code_6, ma_npl_sp, ten_hang)
        flag_32_mapping: Mapping for section 3.2 flag - key is (flow, hs_code_6, ma_npl_sp, ten_hang)
    """
    if npl_to_23_flag is None:
        npl_to_23_flag = {}
    if flag_31_mapping is None:
        flag_31_mapping = {}
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if exclusion_31_mapping is None:
        exclusion_31_mapping = {}
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3"}  # All enabled by default
    
    flow_str = data.get('flow', '')
    dieu_kien_str = data.get('dieu_kien', '')
    npl_str = data.get('npl', '')
    index_value = data.get('index', '')
    
    # Get HS code with fallback
    ma_hs_str = data.get('ma_hs', '')
    if not ma_hs_str and npl_str:
        hs_codes = npl_to_hs_codes.get(npl_str, set())
        if hs_codes:
            ma_hs_str = next(iter(hs_codes))
    
    # Get pre-computed values
    min_before = computed.get('min_before', 0)
    max_before = computed.get('max_before', 0)
    min_after = computed.get('min_after', 0)
    max_after = computed.get('max_after', 0)
    
    # Section 2.2 columns - only fill if "2" (Customs Valuation) is enabled
    if "2" in enabled_sections:
        # Write Flow (center aligned)
        _write_cell(ws, row_idx, cols['flow_col'], flow_str, CENTER_ALIGNMENT)
        
        # Section 2.2 formula columns: write "[To fill]" in italic (data rows)
        ITALIC_FONT = Font(name="Arial", size=10, italic=True)
        to_fill_cols = [
            cols['min_before_col'], cols['max_before_col'],
            cols['min_after_col'], cols['max_after_col'],
            cols['min_120_col'], cols['max_120_col'],
            cols['variance_col']
        ]
        for col_idx in to_fill_cols:
            cell = ws.cell(row=row_idx, column=col_idx, value="[To fill]")
            cell.font = ITALIC_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGNMENT
        
        # Find HS code with highest duty rate for this NPL/SP
        # Same NPL/SP should always have the same representative HS code
        # Note: empty NPL/SP ("") is also a valid group key
        hs_max_duty = ""
        duty_rate_max = ""
        if npl_str in npl_to_hs_codes:
            # NPL/SP exists in mapping (including empty string) - use highest rate HS code
            hs_codes = npl_to_hs_codes[npl_str]
            max_rate = -1
            best_hs = ""
            first_hs = ""  # Keep track of first HS code as fallback
            for hs_code in sorted(hs_codes):  # Sort for consistent first_hs selection
                hs_8 = hs_code[:8] if len(hs_code) >= 8 else hs_code
                if not first_hs:
                    first_hs = hs_8
                tax_str = tariff_rates.get(hs_8, "")
                if tax_str:
                    numeric_val, _ = parse_tax_value(str(tax_str))
                    if numeric_val is not None and numeric_val > max_rate:
                        max_rate = numeric_val
                        best_hs = hs_8
                        duty_rate_max = numeric_val
            if best_hs:
                hs_max_duty = best_hs
            elif first_hs:
                # If no HS code has duty rate, use first HS code and show "N/A"
                hs_max_duty = first_hs
                duty_rate_max = "N/A"
        elif ma_hs_str:
            # Fallback: NPL/SP empty or not in mapping, but row has its own HS code
            hs_8 = ma_hs_str[:8] if len(ma_hs_str) >= 8 else ma_hs_str
            hs_max_duty = hs_8
            tax_str = tariff_rates.get(hs_8, "")
            if tax_str:
                numeric_val, _ = parse_tax_value(str(tax_str))
                if numeric_val is not None:
                    duty_rate_max = numeric_val
                else:
                    duty_rate_max = "N/A"
            else:
                duty_rate_max = "N/A"
        
        # Write HS code with highest duty rate (short code - center aligned)
        cell = ws.cell(row=row_idx, column=cols['hs_max_duty_col'], value=hs_max_duty)
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = CELL_ALIGNMENT  # HS code should be left-aligned
        
        # Write Import Duty rate (MAX) - numeric value, right aligned
        cell = ws.cell(row=row_idx, column=cols['duty_rate_col'], value=duty_rate_max)
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = NUMBER_ALIGNMENT
        
        # Impact amount column: leave empty (not "[To fill]") - numeric value, right aligned
        cell = ws.cell(row=row_idx, column=cols['impact_col'], value="")
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = NUMBER_ALIGNMENT
    else:
        # Section 2.2 not enabled - write empty cells with borders
        # Use appropriate alignment for each column type
        sec_22_center_cols = [cols['flow_col']]  # Only Flow is centered
        sec_22_left_cols = [cols['hs_max_duty_col']]  # HS code is left-aligned
        sec_22_number_cols = [
            cols['min_before_col'], cols['max_before_col'],
            cols['min_after_col'], cols['max_after_col'], cols['min_120_col'],
            cols['max_120_col'], cols['variance_col'],
            cols['duty_rate_col'], cols['impact_col']
        ]
        for col_idx in sec_22_center_cols:
            cell = ws.cell(row=row_idx, column=col_idx, value="")
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGNMENT
        for col_idx in sec_22_left_cols:
            cell = ws.cell(row=row_idx, column=col_idx, value="")
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = CELL_ALIGNMENT
        for col_idx in sec_22_number_cols:
            cell = ws.cell(row=row_idx, column=col_idx, value="")
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = NUMBER_ALIGNMENT
    
    # Empty separators
    for col_key in ['empty_col_0', 'empty_col_1', 'empty_col_3', 'empty_col_4', 'empty_col_5']:
        if col_key in cols:
            ws.cell(row=row_idx, column=cols[col_key], value="").border = NO_BORDER
    
    # Source and Item columns (next to Mã NPL/SP)
    # NOTE: These are already written earlier with prefill_map fallback logic.
    # Only write here if data has actual values (from raw file preprocess columns).
    # Do NOT overwrite with empty values — that would erase prefill_map data.
    if source_item_cols:
        source_val = data.get('source', '')
        item_val = data.get('item', '')
        if source_val or item_val:
            _write_cell(ws, row_idx, source_item_cols[0], source_val, CELL_ALIGNMENT)
            _write_cell(ws, row_idx, source_item_cols[1], item_val, CELL_ALIGNMENT)
    
    # Section 1.1/1.2 Flag column - only fill if "1" (Tariff Classification) is enabled
    if 'sec_11_flag_col' in cols:
        if "1" in enabled_sections:
            ip_value = npl_to_ip_hs.get(npl_str, "") if npl_str else ""
            _write_cell(ws, row_idx, cols['sec_11_flag_col'], ip_value, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_11_flag_col'], "", CELL_ALIGNMENT)
    
    # Section 2.1 columns: RPT, "&", Flag - only fill if "2" (Customs Valuation) is enabled
    # RPT column is empty (to be filled manually)
    if 'sec_21_rpt_col' in cols:
        _write_cell(ws, row_idx, cols['sec_21_rpt_col'], "", CELL_ALIGNMENT)
    
    # "&" column: concatenation of Mã NPL/SP + Tên đối tác + Flow + Điều kiện for VLOOKUP key
    if 'sec_21_ampersand_col' in cols:
        if "2" in enabled_sections:
            ten_doi_tac_str = data.get('ten_doi_tac', '')
            # Use source value (LLM-filled) if available, otherwise use npl_str (original)
            source_val = data.get('source', '')
            npl_for_ampersand = source_val if source_val else npl_str
            ampersand_val = f"{npl_for_ampersand}/{ten_doi_tac_str}/{flow_str}/{dieu_kien_str}"
            _write_cell(ws, row_idx, cols['sec_21_ampersand_col'], ampersand_val, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_21_ampersand_col'], "", CELL_ALIGNMENT)
    
    # Flag column uses VLOOKUP formula via "&" column to look up in sheet 2.1
    if 'sec_21_flag_col' in cols:
        if "2" in enabled_sections and 'sec_21_ampersand_col' in cols:
            # VLOOKUP using "&" column: =IFERROR(VLOOKUP(ampersand_cell,'2.1'!$O:$P,COLUMNS('2.1'!$O:$P),0),"")
            ampersand_col_letter = get_column_letter(cols['sec_21_ampersand_col'])
            formula = f"=IFERROR(VLOOKUP({ampersand_col_letter}{row_idx},'2.1'!$O:$P,COLUMNS('2.1'!$O:$P),0),\"\")"
            cell = ws.cell(row=row_idx, column=cols['sec_21_flag_col'], value=formula)
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = CELL_ALIGNMENT
        else:
            _write_cell(ws, row_idx, cols['sec_21_flag_col'], "", CELL_ALIGNMENT)
    
    # Section 2.3 Flag column - only fill if "2" (Customs Valuation) is enabled
    if 'sec_23_flag_col' in cols:
        if "2" in enabled_sections:
            flag_23_value = npl_to_23_flag.get(npl_str, "") if npl_str else ""
            _write_cell(ws, row_idx, cols['sec_23_flag_col'], flag_23_value, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_23_flag_col'], "", CELL_ALIGNMENT)
    
    # Section 3.1 columns - only fill if "3" (Non-Tariff Measures) is enabled
    # Build key for flag_31/exclusion lookup: (flow, hs_code_6, ma_npl_sp, ten_hang)
    flow_vn = "Nhập" if flow_str == "Nhập" or flow_str == "NHAP" else "Xuất" if flow_str else ""
    hs_code_6 = ma_hs_str[:6] if ma_hs_str and len(ma_hs_str) >= 6 else ma_hs_str
    ten_hang = data.get('ten_hang', '')
    so_tk = data.get('so_tk', '')
    flag_31_key = (flow_vn, hs_code_6, npl_str, ten_hang)
    
    # Import helper functions from output module for consistency
    from .output import _get_transaction_notes, _get_chemical_notes
    
    # Transaction notes column
    if 'sec_31_transaction_notes_col' in cols:
        if "3" in enabled_sections:
            ma_hieu_ptvc = data.get('ma_hieu_ptvc', '')
            transaction_notes = _get_transaction_notes(ma_hieu_ptvc)
            _write_cell(ws, row_idx, cols['sec_31_transaction_notes_col'], transaction_notes, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_31_transaction_notes_col'], "", CELL_ALIGNMENT)
    
    # Chemical notes column
    if 'sec_31_chemical_notes_col' in cols:
        if "3" in enabled_sections:
            chemical_notes = _get_chemical_notes(ma_hs_str)
            _write_cell(ws, row_idx, cols['sec_31_chemical_notes_col'], chemical_notes, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_31_chemical_notes_col'], "", CELL_ALIGNMENT)
    
    # "&" column for 3.1: concatenation of Mã NPL/SP + "/" + Số TK
    if 'sec_31_ampersand_col' in cols:
        if "3" in enabled_sections:
            ampersand_31_val = f"{npl_str}/{so_tk}"
            _write_cell(ws, row_idx, cols['sec_31_ampersand_col'], ampersand_31_val, CELL_ALIGNMENT)
        else:
            _write_cell(ws, row_idx, cols['sec_31_ampersand_col'], "", CELL_ALIGNMENT)
    
    # Section 3.1 Exclusion column - use VLOOKUP to get value from sheet 3.1 (human filled)
    if 'sec_31_exclusion_col' in cols:
        if "3" in enabled_sections:
            # Use VLOOKUP formula to get Exclusion from sheet 3.1 using & as lookup key
            # Sheet 3.1 structure: O=&, P=Exclusion
            sec_31_ampersand_letter = get_column_letter(cols['sec_31_ampersand_col'])
            exclusion_formula = f'=IFERROR(VLOOKUP({sec_31_ampersand_letter}{row_idx},\'3.1\'!$O:$P,2,0),"")'
            cell = ws.cell(row=row_idx, column=cols['sec_31_exclusion_col'], value=exclusion_formula)
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = CELL_ALIGNMENT
        else:
            _write_cell(ws, row_idx, cols['sec_31_exclusion_col'], "", CELL_ALIGNMENT)
    
    # Section 3.1 Flag columns (Flag 1-5) - placeholder, to be filled via VLOOKUP
    if 'sec_31_flag_cols' in cols:
        flag_31_value = flag_31_mapping.get(flag_31_key, "") if ("3" in enabled_sections and flag_31_mapping) else ""
        for flag_col in cols['sec_31_flag_cols']:
            _write_cell(ws, row_idx, flag_col, "[To fill]" if flag_31_value else "", CELL_ALIGNMENT)
    
    # Section 3.1 Flag-C columns (Flag 1-C to 3-C) - for chemical items only
    if 'sec_31_flag_c_cols' in cols:
        chemical_notes = _get_chemical_notes(ma_hs_str) if ma_hs_str else "Non-chemical"
        for flag_c_col in cols['sec_31_flag_c_cols']:
            # Only show "[To fill]" for Chemical items
            if "3" in enabled_sections and chemical_notes == "Chemical":
                _write_cell(ws, row_idx, flag_c_col, "[To fill]", CELL_ALIGNMENT)
            else:
                _write_cell(ws, row_idx, flag_c_col, "", CELL_ALIGNMENT)


def _write_cell(ws, row_idx: int, col_idx: int, value, alignment):
    """Write a standard cell with common formatting"""
    cell = ws.cell(row=row_idx, column=col_idx, value=value)
    cell.font = CELL_FONT
    cell.border = THIN_BORDER
    cell.alignment = alignment


def _write_number_cell(ws, row_idx: int, col_idx: int, value):
    """Write a number cell with formatting - comma-separated"""
    cell = ws.cell(row=row_idx, column=col_idx, value=value)
    cell.font = CELL_FONT
    cell.border = THIN_BORDER
    cell.alignment = NUMBER_ALIGNMENT
    cell.number_format = NUMBER_FORMAT


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def _create_input_sheet_optimized(
    wb: Workbook, 
    file_content: bytes, 
    sheet_title: str, 
    npl_to_ip_hs: Dict[str, str],
    flow_dieu_kien_npl_to_ip_vv: Dict[str, str],
    npl_to_23_flag: Dict[str, str] = None,
    enabled_sections: Optional[Set[str]] = None,
    flag_31_mapping: Dict[Tuple, str] = None,
    flag_32_mapping: Dict[Tuple, str] = None,
    exclusion_31_mapping: Dict[Tuple, str] = None,
    prefill_map: Dict[Tuple, Tuple] = None,
    num_flags_c: int = 1
) -> bool:
    """Create input sheet from file - optimized with streaming read
    
    Args:
        wb: Target workbook
        file_content: Original file bytes
        sheet_title: Sheet title
        npl_to_ip_hs: NPL to IP mapping for HS Inconsistency
        flow_dieu_kien_npl_to_ip_vv: Compound key to IP mapping for Value Variance
        npl_to_23_flag: NPL to flag mapping for section 2.3 (flag when all 3 tests > 0)
        enabled_sections: Set of enabled section numbers ("1", "2", "3").
                         None means all sections enabled.
                         - "1" enables Tariff Classification (1.1/1.2)
                         - "2" enables Customs Valuation (2.1, 2.2, 2.3)
                         - "3" enables Non-Tariff Measures (3.1, 3.2)
        flag_31_mapping: Mapping for section 3.1 flag - key is (flow, hs_code_6, ma_npl_sp, ten_hang)
        flag_32_mapping: Mapping for section 3.2 flag - key is (flow, hs_code_6, ma_npl_sp, ten_hang)
        
    Returns:
        True if successful, False otherwise
    """
    if npl_to_23_flag is None:
        npl_to_23_flag = {}
    if flag_31_mapping is None:
        flag_31_mapping = {}
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3"}  # All enabled by default
    tariff_rates = load_tariff_rates()
    
    if prefill_map is None:
        prefill_map = {}
    
    try:
        # Try openpyxl read_only mode first (for xlsx)
        try:
            logger.info("[INPUT_SHEET] Attempting xlsx path with openpyxl...")
            result = _create_input_from_xlsx(
                wb, file_content, sheet_title, 
                npl_to_ip_hs, flow_dieu_kien_npl_to_ip_vv, tariff_rates, npl_to_23_flag,
                enabled_sections, flag_31_mapping, flag_32_mapping, num_flags_c=num_flags_c,
                exclusion_31_mapping=exclusion_31_mapping,
                prefill_map=prefill_map
            )
            logger.info(f"[INPUT_SHEET] xlsx path completed: {result}")
            return result
        except Exception as e:
            logger.warning(f"[INPUT_SHEET] openpyxl/xlsx failed: {e}, trying pyxlsb...")
            import traceback
            logger.warning(f"[INPUT_SHEET] Traceback: {traceback.format_exc()}")
        
        # Try pyxlsb for xlsb files
        try:
            logger.info("[INPUT_SHEET] Attempting xlsb path with pyxlsb...")
            return _create_input_from_xlsb(
                wb, file_content, sheet_title,
                npl_to_ip_hs, flow_dieu_kien_npl_to_ip_vv, tariff_rates, npl_to_23_flag,
                enabled_sections, flag_31_mapping, flag_32_mapping, exclusion_31_mapping,
                prefill_map=prefill_map, num_flags_c=num_flags_c
            )
        except ImportError:
            logger.warning("[INPUT_SHEET] pyxlsb not installed")
        except Exception as e:
            logger.warning(f"[INPUT_SHEET] pyxlsb failed: {e}")
        
    except Exception as e:
        logger.error(f"[INPUT_SHEET] Failed to create input sheet: {e}")
    
    return False


def _create_input_from_xlsx(
    wb: Workbook,
    file_content: bytes,
    sheet_title: str,
    npl_to_ip_hs: Dict[str, str],
    flow_dieu_kien_npl_to_ip_vv: Dict[str, str],
    tariff_rates: Dict[str, str],
    npl_to_23_flag: Dict[str, str] = None,
    enabled_sections: Optional[Set[str]] = None,
    flag_31_mapping: Dict[Tuple, str] = None,
    flag_32_mapping: Dict[Tuple, str] = None,
    num_flags_c: int = 1,
    exclusion_31_mapping: Dict[Tuple, str] = None,
    prefill_map: Dict[Tuple, Tuple] = None
) -> bool:
    """Create input sheet from xlsx file"""
    if npl_to_23_flag is None:
        npl_to_23_flag = {}
    if flag_31_mapping is None:
        flag_31_mapping = {}
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3"}
    source_wb = load_workbook(BytesIO(file_content), read_only=True, data_only=True)
    source_ws = source_wb.worksheets[0]
    actual_title = source_ws.title
    
    max_row = source_ws.max_row or 0
    max_col = source_ws.max_column or 0
    
    if max_row == 0 or max_col == 0:
        source_wb.close()
        raise ValueError("Empty worksheet")
    
    logger.info(f"Creating input sheet: {max_row} rows x {max_col} cols")
    
    ws_input = wb.create_sheet(sheet_title, 0)  # Use provided sheet_title (VNACCs)
    ws_input.sheet_view.showGridLines = False
    ws_input.sheet_view.zoomScale = 80
    ws_input.sheet_properties.tabColor = "2E2E38"  # Black tab
    
    # Find header row and column indices
    header_row_idx = 1
    col_indices = {}
    
    # Track date and numeric columns for formatting
    date_columns = set()
    numeric_columns = set()
    
    for row_idx, row in enumerate(source_ws.iter_rows(max_row=20, values_only=True), 1):
        row_values = list(row)
        detected = _detect_columns(row_values, row_idx)
        if detected['npl_col_idx']:
            header_row_idx = row_idx
            col_indices = detected
            # Detect date columns
            if detected.get('ngay_dk_col_idx'):
                date_columns.add(detected['ngay_dk_col_idx'])
            # Detect numeric columns  
            if detected.get('don_gia_tinh_thue_col_idx'):
                numeric_columns.add(detected['don_gia_tinh_thue_col_idx'])
            if detected.get('tong_so_luong_col_idx'):
                numeric_columns.add(detected['tong_so_luong_col_idx'])
            break
    
    logger.info(f"[XLSX] Header found at row {header_row_idx}, max_col={max_col}")
    logger.info(f"[XLSX] Detected columns - NPL: {col_indices.get('npl_col_idx')}, "
                f"Source: {col_indices.get('source_col_idx')}, "
                f"Item: {col_indices.get('item_col_idx')}, "
                f"Preprocess skip: {col_indices.get('preprocess_skip_cols', set())}, "
                f"Mã HS: {col_indices.get('ma_hs_col_idx')}")
    
    # Collect all data from source FIRST to determine dynamic layout
    metadata_rows = []  # Rows before header row (report info)
    row_data_map = {}
    source_data = []  # List of (source_row_idx, row_values)
    header_row_values = None
    
    for row_idx, row in enumerate(source_ws.iter_rows(values_only=True), 1):
        row_values = list(row)
        
        if row_idx < header_row_idx:
            # Metadata rows (report title, company info, etc.)
            metadata_rows.append((row_idx, row_values))
        elif row_idx == header_row_idx:
            header_row_values = row_values
            # Detect date and numeric columns from header
            for col_idx, header_val in enumerate(header_row_values, 1):
                if header_val:
                    header_str = str(header_val).lower()
                    if any(kw in header_str for kw in ['ngày', 'ngay', 'date']):
                        date_columns.add(col_idx)
                    if any(kw in header_str for kw in ['trị giá', 'tri gia', 'tiền', 'tien', 'giá', 'gia', 'lượng', 'luong', 'thuế', 'thue', 'số lượng', 'so luong']):
                        numeric_columns.add(col_idx)
        else:  # row_idx > header_row_idx
            source_data.append((row_idx, row_values))
            data = _extract_row_data(row_values, col_indices)
            data['index'] = f"{data['flow']}_{data['npl']}_{data['so_tk']}_{data['tsl']}"
            row_data_map[row_idx] = data
    
    source_wb.close()
    
    # FIXED LAYOUT
    # Metadata rows 1-9 (metadata in cols 1-56, section headers in cols 57+ - no overlap)
    # Row 8: Section headers (1.1/1.2, 2.1, etc.) at cols 57+ | Metadata continues at cols 1-56
    # Row 9: Preprocess row at cols 57+ | Metadata continues at cols 1-56
    # Row 10: Column headers (Flag, RPT, &, Flow, etc.)
    # Row 11: Filter/formula row  
    # Row 12+: Data
    METADATA_MAX_ROW = 9
    SECTION_ROW = 8
    HEADER_ROW = 10
    FILTER_ROW = 11
    DATA_START_ROW = 12
    
    num_metadata_rows = len(metadata_rows)
    logger.info(f"[XLSX] Collected {num_metadata_rows} metadata rows (header at row {header_row_idx}), {len(source_data)} data rows")
    if header_row_values:
        last_headers = header_row_values[-5:] if len(header_row_values) >= 5 else header_row_values
        logger.info(f"[XLSX] Last 5 header columns: {last_headers}")
    
    # Build output column mapping: skip ALL preprocess columns, insert 2 new after NPL
    npl_col = col_indices.get('npl_col_idx')
    skip_cols: Set[int] = col_indices.get('preprocess_skip_cols', set()).copy()
    if col_indices.get('source_col_idx'):
        skip_cols.add(col_indices['source_col_idx'])
    if col_indices.get('item_col_idx'):
        skip_cols.add(col_indices['item_col_idx'])
    # Never skip the NPL column itself
    if npl_col and npl_col in skip_cols:
        skip_cols.discard(npl_col)
    
    col_map, max_col_output, source_item_cols = _build_output_col_map(max_col, npl_col, skip_cols)
    
    if skip_cols:
        logger.info(f"[XLSX] Skipping original preprocess columns at positions {skip_cols}")
    logger.info(f"[XLSX] col_map created: max_col_output={max_col_output}, source_item_cols={source_item_cols}")
    
    # Write metadata rows (rows 1 to min(N, 8)) WITH col_map for alignment
    # This ensures metadata aligns with header/data columns
    for src_row_idx, row_values in metadata_rows:
        if src_row_idx <= METADATA_MAX_ROW:
            for col_idx, val in enumerate(row_values, 1):
                out_col = col_map.get(col_idx)
                if out_col is None:
                    continue  # Skip old preprocess columns
                if val is not None:
                    ws_input.cell(row=src_row_idx, column=out_col, value=val)
    
    # Write original column headers at HEADER_ROW (with column mapping)
    if header_row_values:
        for col_idx, val in enumerate(header_row_values, 1):
            out_col = col_map.get(col_idx)
            if out_col is not None:
                cell = ws_input.cell(row=HEADER_ROW, column=out_col, value=val)
                cell.font = INPUT_HEADER_FONT
                cell.border = THIN_BORDER
                cell.alignment = HEADER_ALIGNMENT
    
    # Write headers for the 2 new columns (Mã NPL/SP Suggested + Rationale)
    if source_item_cols:
        for col, text in [(source_item_cols[0], "Mã NPL/SP\n(Suggested)"), (source_item_cols[1], "Rationale")]:
            cell = ws_input.cell(row=HEADER_ROW, column=col, value=text)
            cell.font = NEW_COL_HEADER_FONT
            cell.fill = NEW_COL_HEADER_FILL
            cell.alignment = NEW_COL_HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Write original data starting at DATA_START_ROW (with column mapping)
    output_row_mapping = {}  # Map source_row_idx -> output_row_idx
    so_tk_orig_col = col_indices.get('so_tk_col_idx')
    for idx, (source_row_idx, row_values) in enumerate(source_data):
        output_row = DATA_START_ROW + idx
        output_row_mapping[source_row_idx] = output_row
        
        for col_idx, val in enumerate(row_values, 1):
            out_col = col_map.get(col_idx)
            if out_col is None:
                continue  # Skip original Source/Item columns
            
            # Format Số TK column
            if so_tk_orig_col and col_idx == so_tk_orig_col and val is not None:
                cell = ws_input.cell(row=output_row, column=out_col, value=str(int(val) if isinstance(val, float) else val))
                cell.number_format = '@'
            else:
                cell = ws_input.cell(row=output_row, column=out_col, value=val)
            
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            
            # Apply alignment: numeric columns right-aligned, text columns left-aligned
            # All with vertical center (Middle Align)
            if col_idx in numeric_columns:
                cell.alignment = NUMBER_ALIGNMENT
            else:
                cell.alignment = CELL_ALIGNMENT
            
            # Apply date format for date columns (using ORIGINAL col positions)
            if col_idx in date_columns and val is not None:
                cell.number_format = DATE_FORMAT
            # Apply number format for numeric columns
            elif col_idx in numeric_columns and val is not None and isinstance(val, (int, float)):
                cell.number_format = NUMBER_FORMAT
    
    total_output_rows = DATA_START_ROW + len(source_data) - 1
    
    # Write source/item data for each data row (from raw file + prefill_map)
    if source_item_cols:
        prefill_matched = 0
        prefill_fallback = 0
        for source_row_idx, data in row_data_map.items():
            output_row = output_row_mapping.get(source_row_idx)
            if output_row:
                source_val = data.get('source', '')
                item_val = data.get('item', '')
                # Override with prefill data if available and raw file has no values
                if prefill_map and (not source_val):
                    so_tk_str = data.get('so_tk', '').strip()
                    ten_hang_str = data.get('ten_hang', '').strip()
                    key = (so_tk_str, ten_hang_str)
                    if key in prefill_map:
                        source_val, item_val = prefill_map[key]
                        prefill_matched += 1
                    elif ten_hang_str and ('__TH__', ten_hang_str) in prefill_map:
                        source_val, item_val = prefill_map[('__TH__', ten_hang_str)]
                        prefill_fallback += 1
                    # IMPORTANT: Update row_data_map with prefilled values so _write_computed_row can use them
                    data['source'] = source_val
                    data['item'] = item_val
                _write_cell(ws_input, output_row, source_item_cols[0], source_val, CELL_ALIGNMENT)
                _write_cell(ws_input, output_row, source_item_cols[1], item_val, CELL_ALIGNMENT)
        if prefill_map:
            logger.info(f"Prefill map: {prefill_matched} exact matches, {prefill_fallback} fallback matches")
        
        # Set column widths for new columns
        ws_input.column_dimensions[get_column_letter(source_item_cols[0])].width = 16
        ws_input.column_dimensions[get_column_letter(source_item_cols[1])].width = 12
    
    # Update col_indices to output positions
    for key in list(col_indices.keys()):
        if col_indices[key] is not None:
            mapped = col_map.get(col_indices[key])
            if mapped is not None:
                col_indices[key] = mapped
    
    # Update date/numeric column sets to output positions
    date_columns = {col_map[c] for c in date_columns if col_map.get(c) is not None}
    numeric_columns = {col_map[c] for c in numeric_columns if col_map.get(c) is not None}
    
    max_col = max_col_output
    
    # Set column widths for original columns
    for col_idx in range(1, max_col + 1):
        if source_item_cols and col_idx in source_item_cols:
            continue  # Already set above
        ws_input.column_dimensions[get_column_letter(col_idx)].width = STANDARD_COLUMN_WIDTH
    
    # Set row heights
    ws_input.row_dimensions[HEADER_ROW].height = TITLE_ROW_HEIGHT
    for row_idx in range(DATA_START_ROW, total_output_rows + 1):
        ws_input.row_dimensions[row_idx].height = STANDARD_ROW_HEIGHT
    
    # Group rows by Index
    index_groups = {}
    for source_row_idx, data in row_data_map.items():
        idx_key = data['index']
        if idx_key not in index_groups:
            index_groups[idx_key] = []
        index_groups[idx_key].append((source_row_idx, data))
    
    # Build NPL -> HS codes mapping
    npl_to_hs_codes = {}
    for source_row_idx, data in row_data_map.items():
        npl = data.get('npl', '')
        hs = data.get('ma_hs', '')
        # Include empty NPL/SP as valid group (empty string is also a valid key)
        if hs:
            if npl not in npl_to_hs_codes:
                npl_to_hs_codes[npl] = set()
            npl_to_hs_codes[npl].add(hs)
    
    # Pre-compute MIN/MAX values (using source row indices)
    computed_values = _compute_min_max_values(row_data_map, index_groups)
    logger.info(f"Pre-computed MIN/MAX values for {len(computed_values)} rows")
    
    # Determine if preprocess was used (prefill_map has data)
    _has_preprocess = bool(prefill_map)
    
    # Setup new columns (section headers at row 9, column headers at row 10, formulas at row 11)
    cols = _setup_new_columns(ws_input, SECTION_ROW, HEADER_ROW, max_col, FILTER_ROW, col_indices=col_indices, source_item_cols=source_item_cols, preprocess_row_idx=None, has_preprocess=_has_preprocess, num_flags_c=num_flags_c)
    
    # Add auto filter starting from FILTER_ROW
    filter_range = f"A{FILTER_ROW}:{get_column_letter(cols['last_col'])}{total_output_rows}"
    ws_input.auto_filter.ref = filter_range
    
    # Write computed values for each data row
    # Debug: log exclusion mapping info
    logger.info(f"[XLSX] Writing rows with exclusion_31_mapping: {len(exclusion_31_mapping) if exclusion_31_mapping else 0} entries, flag_31_mapping: {len(flag_31_mapping) if flag_31_mapping else 0} entries")
    if exclusion_31_mapping and len(exclusion_31_mapping) > 0:
        sample_keys = list(exclusion_31_mapping.keys())[:2]
        logger.info(f"[XLSX] Sample exclusion keys from mapping: {sample_keys}")
    
    for source_row_idx, data in row_data_map.items():
        output_row = output_row_mapping.get(source_row_idx)
        if output_row:
            computed = computed_values.get(source_row_idx, {})
            _write_computed_row(
                ws_input, output_row, data, computed, cols,
                npl_to_ip_hs, flow_dieu_kien_npl_to_ip_vv,
                npl_to_hs_codes, tariff_rates,
                col_indices.get('tong_so_luong_col_idx'),
                npl_to_23_flag,
                enabled_sections,
                flag_31_mapping,
                flag_32_mapping,
                col_indices.get('npl_col_idx'),
                exclusion_31_mapping,
                source_item_cols=source_item_cols
            )
    
    # Add dropdown list for RPT column with "Related" or "Not related"
    from openpyxl.worksheet.datavalidation import DataValidation
    rpt_col_letter = get_column_letter(cols['sec_21_rpt_col'])
    rpt_validation = DataValidation(
        type="list",
        formula1='"Related,Not related"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Invalid Input",
        error="Please select 'Related' or 'Not related'"
    )
    rpt_validation.add(f"{rpt_col_letter}{DATA_START_ROW}:{rpt_col_letter}{total_output_rows}")
    ws_input.add_data_validation(rpt_validation)
    
    # Freeze from data start row AFTER "Mã loại hình" column (include that column in freeze)
    ma_loai_hinh_col = col_indices.get('ma_loai_hinh_col_idx', 1)
    freeze_col = (ma_loai_hinh_col + 1) if ma_loai_hinh_col else 2
    freeze_col_letter = get_column_letter(freeze_col)
    ws_input.freeze_panes = f"{freeze_col_letter}{DATA_START_ROW}"
    
    logger.info(f"Created VNACCs sheet with {len(metadata_rows)} metadata rows + {len(source_data)} data rows, enabled_sections={enabled_sections}")
    return True


def _create_input_from_xlsb(
    wb: Workbook,
    file_content: bytes,
    sheet_title: str,
    npl_to_ip_hs: Dict[str, str],
    flow_dieu_kien_npl_to_ip_vv: Dict[str, str],
    tariff_rates: Dict[str, str],
    npl_to_23_flag: Dict[str, str] = None,
    enabled_sections: Optional[Set[str]] = None,
    flag_31_mapping: Dict[Tuple, str] = None,
    flag_32_mapping: Dict[Tuple, str] = None,
    exclusion_31_mapping: Dict[Tuple, str] = None,
    prefill_map: Dict[Tuple, Tuple] = None,
    num_flags_c: int = 1
) -> bool:
    """Create input sheet from xlsb file - OPTIMIZED VERSION
    
    Performance improvements:
    - Single pass through xlsb file (vs 2 passes before)
    - Use ws.append() for bulk row insertion
    - Apply styles in batch after data writing
    - Minimize individual cell operations
    """
    if npl_to_23_flag is None:
        npl_to_23_flag = {}
    if flag_31_mapping is None:
        flag_31_mapping = {}
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3"}
    from pyxlsb import open_workbook as open_xlsb
    import time
    
    start_time = time.time()
    
    with open_xlsb(BytesIO(file_content)) as xlsb_wb:
        if not xlsb_wb.sheets:
            return False
        
        actual_title = xlsb_wb.sheets[0]
        ws_input = wb.create_sheet(sheet_title, 0)
        ws_input.sheet_view.showGridLines = False
        ws_input.sheet_view.zoomScale = 80
        ws_input.sheet_properties.tabColor = "2E2E38"
        
        # ================================================================
        # TWO-PHASE READ: First detect header, then categorize rows
        # ================================================================
        # Phase 1: Find header row
        header_row_idx = 1
        col_indices = {}
        date_columns = set()
        numeric_columns = set()
        
        with xlsb_wb.get_sheet(actual_title) as sheet:
            for row_idx, row in enumerate(sheet.rows(), 1):
                if row_idx > 20:
                    break
                row_values = [cell.v for cell in row]
                detected = _detect_columns(row_values, row_idx)
                if detected['npl_col_idx']:
                    header_row_idx = row_idx
                    col_indices = detected
                    if detected.get('ngay_dk_col_idx'):
                        date_columns.add(detected['ngay_dk_col_idx'])
                    if detected.get('don_gia_tinh_thue_col_idx'):
                        numeric_columns.add(detected['don_gia_tinh_thue_col_idx'])
                    if detected.get('tong_so_luong_col_idx'):
                        numeric_columns.add(detected['tong_so_luong_col_idx'])
                    for col_idx_h, header_val in enumerate(row_values, 1):
                        if header_val:
                            header_str = str(header_val).lower()
                            if any(kw in header_str for kw in ['ngày', 'ngay', 'date']):
                                date_columns.add(col_idx_h)
                            if any(kw in header_str for kw in ['trị giá', 'tri gia', 'tiền', 'tien', 'giá', 'gia', 'lượng', 'luong', 'thuế', 'thue', 'số lượng', 'so luong']):
                                numeric_columns.add(col_idx_h)
                    break
        
        logger.info(f"[XLSB] Header found at row {header_row_idx}")
        
        # Phase 2: Read all data with correct categorization
        metadata_rows = []
        source_data = []
        row_data_map = {}
        header_row_values = None
        max_col = 0
        
        with xlsb_wb.get_sheet(actual_title) as sheet:
            for row_idx, row in enumerate(sheet.rows(), 1):
                row_values = [cell.v for cell in row]
                row_len = len(row_values)
                if row_len > max_col:
                    max_col = row_len
                
                # Categorize rows based on pre-detected header position
                if row_idx < header_row_idx:
                    metadata_rows.append((row_idx, row_values))
                elif row_idx == header_row_idx:
                    header_row_values = row_values
                else:
                    source_data.append((row_idx, row_values))
                    data = _extract_row_data(row_values, col_indices)
                    data['index'] = f"{data['flow']}_{data['npl']}_{data['so_tk']}_{data['tsl']}"
                    row_data_map[row_idx] = data
        
        read_time = time.time() - start_time
        logger.info(f"[XLSB] Read {len(source_data)} data rows in {read_time:.2f}s")
        
        # FIXED LAYOUT
        # Metadata rows 1-9 (metadata in cols 1-56, section headers in cols 57+ - no overlap)
        # Row 8: Section headers (1.1/1.2, 2.1, etc.) at cols 57+ | Metadata continues at cols 1-56
        # Row 9: Preprocess row at cols 57+ | Metadata continues at cols 1-56
        # Row 10: Column headers (Flag, RPT, &, Flow, etc.)
        # Row 11: Filter/formula row  
        # Row 12+: Data
        METADATA_MAX_ROW = 9
        SECTION_ROW = 8
        HEADER_ROW = 10
        FILTER_ROW = 11
        DATA_START_ROW = 12
        
        num_metadata_rows = len(metadata_rows)
        logger.info(f"[XLSB] Collected {num_metadata_rows} metadata rows, {len(source_data)} data rows")
        
        # ================================================================
        # PRE-COMPUTE ALL VALUES
        # ================================================================
        compute_start = time.time()
        
        # Group by Index
        index_groups = {}
        for source_row_idx, data in row_data_map.items():
            idx_key = data['index']
            if idx_key not in index_groups:
                index_groups[idx_key] = []
            index_groups[idx_key].append((source_row_idx, data))
        
        # Build NPL -> HS codes mapping
        npl_to_hs_codes = {}
        for source_row_idx, data in row_data_map.items():
            npl = data.get('npl', '')
            hs = data.get('ma_hs', '')
            if hs:
                if npl not in npl_to_hs_codes:
                    npl_to_hs_codes[npl] = set()
                npl_to_hs_codes[npl].add(hs)
        
        # Pre-compute all new column values for each row
        computed_rows = _precompute_all_row_values(
            row_data_map, npl_to_hs_codes, tariff_rates,
            npl_to_ip_hs, npl_to_23_flag, enabled_sections, flag_31_mapping, flag_32_mapping,
            exclusion_31_mapping
        )
        
        compute_time = time.time() - compute_start
        logger.info(f"[XLSB] Pre-computed values in {compute_time:.2f}s")
        
        # ================================================================
        # WRITE DATA - optimized but correct row positioning
        # ================================================================
        write_start = time.time()
        
        # Build output column mapping: skip ALL preprocess columns, insert 2 new after NPL
        npl_col = col_indices.get('npl_col_idx')
        skip_cols_xlsb: Set[int] = col_indices.get('preprocess_skip_cols', set()).copy()
        if col_indices.get('source_col_idx'):
            skip_cols_xlsb.add(col_indices['source_col_idx'])
        if col_indices.get('item_col_idx'):
            skip_cols_xlsb.add(col_indices['item_col_idx'])
        # Never skip the NPL column itself
        if npl_col and npl_col in skip_cols_xlsb:
            skip_cols_xlsb.discard(npl_col)
        
        col_map, max_col_output, source_item_cols = _build_output_col_map(max_col, npl_col, skip_cols_xlsb)
        
        if skip_cols_xlsb:
            logger.info(f"[XLSB] Skipping original preprocess columns at positions {skip_cols_xlsb}")
        
        # Save original so_tk col for Số TK formatting
        orig_so_tk_col = col_indices.get('so_tk_col_idx')
        
        # Update col_indices to output positions
        for key in list(col_indices.keys()):
            if col_indices[key] is not None:
                mapped = col_map.get(col_indices[key])
                if mapped is not None:
                    col_indices[key] = mapped
        
        # Update date/numeric column sets to output positions
        date_columns = {col_map[c] for c in date_columns if col_map.get(c) is not None}
        numeric_columns = {col_map[c] for c in numeric_columns if col_map.get(c) is not None}
        
        max_col = max_col_output
        
        # Determine if preprocess was used (prefill_map has data)
        _has_preprocess = bool(prefill_map)
        
        # Pre-calculate column layout (needed for filter row clearing)
        cols = _setup_new_columns(ws_input, SECTION_ROW, HEADER_ROW, max_col, filter_row_idx=None, col_indices=col_indices, source_item_cols=source_item_cols, preprocess_row_idx=None, has_preprocess=_has_preprocess, num_flags_c=num_flags_c)
        total_cols = cols['last_col']
        
        # Write metadata rows (rows 1 to min(N, 8)) WITH col_map for alignment
        # This ensures metadata aligns with header/data columns
        for src_row_idx, row_values in metadata_rows:
            if src_row_idx <= METADATA_MAX_ROW:
                for col_idx, val in enumerate(row_values, 1):
                    out_col = col_map.get(col_idx)
                    if out_col is None:
                        continue  # Skip old preprocess columns
                    if val is not None:
                        ws_input.cell(row=src_row_idx, column=out_col, value=val)
        
        # Write header row (original columns + new source/item columns)
        if header_row_values:
            for col_idx, val in enumerate(header_row_values, 1):
                out_col = col_map.get(col_idx)
                if out_col is not None:
                    cell = ws_input.cell(row=HEADER_ROW, column=out_col, value=val)
                    cell.font = INPUT_HEADER_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = HEADER_ALIGNMENT
            
            # Write headers for the 2 new columns next to Mã NPL/SP
            if source_item_cols:
                for col, text in [(source_item_cols[0], "Mã NPL/SP\n(Suggested)"), (source_item_cols[1], "Rationale")]:
                    cell = ws_input.cell(row=HEADER_ROW, column=col, value=text)
                    cell.font = NEW_COL_HEADER_FONT
                    cell.fill = NEW_COL_HEADER_FILL
                    cell.alignment = NEW_COL_HEADER_ALIGNMENT
                    cell.border = THIN_BORDER
        
        # Write filter row borders (empty cells for original data columns)
        # Build set of empty separator columns (exclude borders)
        # empty_col_0 is ALWAYS at BE (57) as separator
        empty_sep_cols = {cols['empty_col_0'], cols['empty_col_1'], cols['empty_col_3'], 
                          cols['empty_col_4'], cols['empty_col_5']}
        
        for col_idx in range(1, total_cols + 1):
            cell = ws_input.cell(row=FILTER_ROW, column=col_idx, value="")
            if col_idx not in empty_sep_cols:
                cell.border = THIN_BORDER
        
        # NOW write formulas AFTER filter row clearing (section headers at row 9, column headers at row 10)
        cols = _setup_new_columns(ws_input, SECTION_ROW, HEADER_ROW, max_col, FILTER_ROW, col_indices=col_indices, source_item_cols=source_item_cols, preprocess_row_idx=None, has_preprocess=_has_preprocess, num_flags_c=num_flags_c)
        
        # Write data rows at correct positions
        output_row_mapping = {}
        
        for idx, (source_row_idx, row_values) in enumerate(source_data):
            output_row = DATA_START_ROW + idx
            output_row_mapping[source_row_idx] = output_row
            
            # Get pre-computed values for new columns
            computed = computed_rows.get(source_row_idx, {})
            
            # Write original data columns (with column mapping, skip Source/Item)
            for col_idx, val in enumerate(row_values, 1):
                out_col = col_map.get(col_idx)
                if out_col is None:
                    continue  # Skip original Source/Item columns
                
                # Format Số TK column (use original position for matching)
                if orig_so_tk_col and col_idx == orig_so_tk_col and val is not None:
                    try:
                        val = str(int(val) if isinstance(val, float) else val)
                    except (ValueError, TypeError):
                        pass
                ws_input.cell(row=output_row, column=out_col, value=val)
            
            # Write source/item data to new columns next to Mã NPL/SP
            if source_item_cols:
                source_val = computed.get('source', '')
                item_val = computed.get('item', '')
                # Override with prefill data if available
                if prefill_map and not source_val:
                    data = row_data_map.get(source_row_idx, {})
                    so_tk_str = data.get('so_tk', '').strip()
                    ten_hang_str = data.get('ten_hang', '').strip()
                    key = (so_tk_str, ten_hang_str)
                    if key in prefill_map:
                        source_val, item_val = prefill_map[key]
                    elif ten_hang_str and ('__TH__', ten_hang_str) in prefill_map:
                        source_val, item_val = prefill_map[('__TH__', ten_hang_str)]
                    
                    # IMPORTANT: Recompute sec_21_ampersand with prefilled source value
                    if source_val:
                        data = row_data_map.get(source_row_idx, {})
                        ten_doi_tac_str = data.get('ten_doi_tac', '')
                        flow_str = computed.get('flow', '')
                        dieu_kien_str = data.get('dieu_kien', '')
                        computed['sec_21_ampersand'] = f"{source_val}/{ten_doi_tac_str}/{flow_str}/{dieu_kien_str}"
                
                cell_s = ws_input.cell(row=output_row, column=source_item_cols[0], value=source_val)
                cell_s.font = CELL_FONT
                cell_s.border = THIN_BORDER
                cell_s.alignment = CELL_ALIGNMENT
                cell_i = ws_input.cell(row=output_row, column=source_item_cols[1], value=item_val)
                cell_i.font = CELL_FONT
                cell_i.border = THIN_BORDER
                cell_i.alignment = CELL_ALIGNMENT
            
            # Write new column values (no longer includes source/item)
            # Start from sec_11_flag_col (skip empty_col_0 marker)
            new_col_values = _build_new_col_values(computed, cols, enabled_sections)
            for i, val in enumerate(new_col_values[1:]):  # Skip first value (empty_col_0)
                col_idx = cols['sec_11_flag_col'] + i
                ws_input.cell(row=output_row, column=col_idx, value=val)
        
        write_time = time.time() - write_start
        logger.info(f"[XLSB] Wrote {len(source_data)} rows in {write_time:.2f}s")
        
        # ================================================================
        # APPLY STYLES IN BATCH - much faster than per-cell
        # ================================================================
        style_start = time.time()
        
        total_output_rows = DATA_START_ROW + len(source_data) - 1
        
        # Apply styles to header row
        for col_idx in range(1, max_col + 1):
            cell = ws_input.cell(row=HEADER_ROW, column=col_idx)
            cell.font = INPUT_HEADER_FONT
            cell.border = THIN_BORDER
            cell.alignment = HEADER_ALIGNMENT
        
        # Apply styles to original data columns (batch by column)
        _apply_styles_batch(
            ws_input, DATA_START_ROW, total_output_rows,
            max_col, date_columns, numeric_columns, col_indices, cols
        )
        
        # Set column widths
        for col_idx in range(1, max_col + 1):
            if source_item_cols and col_idx in source_item_cols:
                continue  # Set separately below
            ws_input.column_dimensions[get_column_letter(col_idx)].width = STANDARD_COLUMN_WIDTH
        
        # Set column widths for new source/item columns
        if source_item_cols:
            ws_input.column_dimensions[get_column_letter(source_item_cols[0])].width = 16
            ws_input.column_dimensions[get_column_letter(source_item_cols[1])].width = 12
        
        # Set row heights
        ws_input.row_dimensions[HEADER_ROW].height = TITLE_ROW_HEIGHT
        for row_idx in range(DATA_START_ROW, total_output_rows + 1):
            ws_input.row_dimensions[row_idx].height = STANDARD_ROW_HEIGHT
        
        style_time = time.time() - style_start
        logger.info(f"[XLSB] Applied styles in {style_time:.2f}s")
        
        # Auto filter
        filter_range = f"A{FILTER_ROW}:{get_column_letter(cols['last_col'])}{total_output_rows}"
        ws_input.auto_filter.ref = filter_range
        
        # Add dropdown list for RPT column with "Related" or "Not related"
        from openpyxl.worksheet.datavalidation import DataValidation
        rpt_col_letter = get_column_letter(cols['sec_21_rpt_col'])
        rpt_validation = DataValidation(
            type="list",
            formula1='"Related,Not related"',
            allow_blank=True,
            showDropDown=False,
            showErrorMessage=True,
            errorTitle="Invalid Input",
            error="Please select 'Related' or 'Not related'"
        )
        rpt_validation.add(f"{rpt_col_letter}{DATA_START_ROW}:{rpt_col_letter}{total_output_rows}")
        ws_input.add_data_validation(rpt_validation)
        
        # Freeze panes
        ma_loai_hinh_col = col_indices.get('ma_loai_hinh_col_idx', 1)
        freeze_col = (ma_loai_hinh_col + 1) if ma_loai_hinh_col else 2
        freeze_col_letter = get_column_letter(freeze_col)
        ws_input.freeze_panes = f"{freeze_col_letter}{DATA_START_ROW}"
        
        total_time = time.time() - start_time
        logger.info(f"[XLSB] Created VNACCs sheet in {total_time:.2f}s (read={read_time:.2f}s, compute={compute_time:.2f}s, write={write_time:.2f}s, style={style_time:.2f}s)")
        
        return True


def _precompute_all_row_values(
    row_data_map: Dict[int, Dict],
    npl_to_hs_codes: Dict[str, Set[str]],
    tariff_rates: Dict[str, str],
    npl_to_ip_hs: Dict[str, str],
    npl_to_23_flag: Dict[str, str],
    enabled_sections: Set[str],
    flag_31_mapping: Dict[Tuple, str],
    flag_32_mapping: Dict[Tuple, str] = None,
    exclusion_31_mapping: Dict[Tuple, str] = None
) -> Dict[int, Dict]:
    """Pre-compute all values for new columns for all rows - OPTIMIZED
    
    Key optimization: Pre-compute best HS code (highest duty rate) for each NPL/SP
    ONCE instead of for each row. This reduces O(rows × hs_codes) to O(npl_groups × hs_codes).
    
    Returns dict mapping source_row_idx to computed values dict
    """
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if exclusion_31_mapping is None:
        exclusion_31_mapping = {}
    # OPTIMIZATION: Pre-compute best HS code for each NPL/SP group
    npl_to_best_hs = {}  # {npl: (best_hs_code, duty_rate)}
    
    if "2" in enabled_sections:
        for npl_str, hs_codes in npl_to_hs_codes.items():
            max_rate = -1
            best_hs = ""
            first_hs = ""
            
            for hs_code in sorted(hs_codes):
                hs_8 = hs_code[:8] if len(hs_code) >= 8 else hs_code
                if not first_hs:
                    first_hs = hs_8
                tax_str = tariff_rates.get(hs_8, "")
                if tax_str:
                    numeric_val, _ = parse_tax_value(str(tax_str))
                    if numeric_val is not None and numeric_val > max_rate:
                        max_rate = numeric_val
                        best_hs = hs_8
            
            if best_hs:
                npl_to_best_hs[npl_str] = (best_hs, max_rate)
            elif first_hs:
                npl_to_best_hs[npl_str] = (first_hs, "N/A")
            else:
                npl_to_best_hs[npl_str] = ("", "")
    
    # Now compute per-row values using pre-computed lookups
    computed_rows = {}
    
    for source_row_idx, data in row_data_map.items():
        flow_str = data.get('flow', '')
        npl_str = data.get('npl', '')
        ma_hs_str = data.get('ma_hs', '')
        ten_hang = data.get('ten_hang', '')
        
        # Get HS code with fallback
        if not ma_hs_str and npl_str:
            hs_codes = npl_to_hs_codes.get(npl_str, set())
            if hs_codes:
                ma_hs_str = next(iter(hs_codes))
        
        dieu_kien_str = data.get('dieu_kien', '')
        ten_doi_tac_str = data.get('ten_doi_tac', '')
        
        computed = {
            'flow': flow_str,
            'source': data.get('source', ''),
            'item': data.get('item', ''),
            'sec_11_flag': '',
            'sec_21_rpt': '',
            'sec_21_ampersand': '',
            'sec_21_flag': '',
            'hs_max_duty': '',
            'duty_rate_max': '',
            'sec_23_flag': '',
            'sec_31_transaction_notes': '',
            'sec_31_chemical_notes': '',
            'sec_31_flag': '',
            'sec_31_exclusion': '',
            'sec_32_flag': '',
        }
        
        # Section 2.1 "&" concatenation for VLOOKUP key
        if "2" in enabled_sections:
            # Use source value (LLM-filled) if available, otherwise use npl_str (original)
            source_str = data.get('source', '')
            npl_for_ampersand = source_str if source_str else npl_str
            computed['sec_21_ampersand'] = f"{npl_for_ampersand}/{ten_doi_tac_str}/{flow_str}/{dieu_kien_str}"
        
        # Section 1.1/1.2 Flag
        if "1" in enabled_sections:
            computed['sec_11_flag'] = npl_to_ip_hs.get(npl_str, "") if npl_str else ""
        
        # Section 2.2 - HS code with highest duty rate (use pre-computed)
        if "2" in enabled_sections:
            if npl_str in npl_to_best_hs:
                hs_max_duty, duty_rate_max = npl_to_best_hs[npl_str]
            elif ma_hs_str:
                # Fallback for rows without NPL/SP
                hs_8 = ma_hs_str[:8] if len(ma_hs_str) >= 8 else ma_hs_str
                hs_max_duty = hs_8
                tax_str = tariff_rates.get(hs_8, "")
                if tax_str:
                    numeric_val, _ = parse_tax_value(str(tax_str))
                    duty_rate_max = numeric_val if numeric_val is not None else "N/A"
                else:
                    duty_rate_max = "N/A"
            else:
                hs_max_duty = ""
                duty_rate_max = ""
            
            computed['hs_max_duty'] = hs_max_duty
            computed['duty_rate_max'] = duty_rate_max
            computed['sec_23_flag'] = npl_to_23_flag.get(npl_str, "") if npl_str else ""
        
        # Section 3.1 Transaction notes, Chemical notes, Flag + Exclusion
        if "3" in enabled_sections:
            # Import helper functions for notes
            from .output import _get_transaction_notes, _get_chemical_notes
            
            # Transaction notes based on Mã hiệu PTVC
            ma_hieu_ptvc = data.get('ma_hieu_ptvc', '')
            computed['sec_31_transaction_notes'] = _get_transaction_notes(ma_hieu_ptvc)
            
            # Chemical notes based on HS code
            computed['sec_31_chemical_notes'] = _get_chemical_notes(ma_hs_str)
            
            flow_vn = "Nhập" if flow_str == "Nhập" or flow_str == "NHAP" else "Xuất" if flow_str else ""
            hs_code_6 = ma_hs_str[:6] if ma_hs_str and len(ma_hs_str) >= 6 else ma_hs_str
            flag_31_key = (flow_vn, hs_code_6, npl_str, ten_hang)
            if flag_31_mapping:
                computed['sec_31_flag'] = flag_31_mapping.get(flag_31_key, "")
            if exclusion_31_mapping:
                computed['sec_31_exclusion'] = exclusion_31_mapping.get(flag_31_key, "")
        
        # Section 3.2 Flag
        if "3" in enabled_sections and flag_32_mapping:
            flow_vn = "Nhập" if flow_str == "Nhập" or flow_str == "NHAP" else "Xuất" if flow_str else ""
            hs_code_6 = ma_hs_str[:6] if ma_hs_str and len(ma_hs_str) >= 6 else ma_hs_str
            flag_32_key = (flow_vn, hs_code_6, npl_str, ten_hang)
            computed['sec_32_flag'] = flag_32_mapping.get(flag_32_key, "")
        
        computed_rows[source_row_idx] = computed
    
    return computed_rows


def _setup_new_columns_headers_only(ws, section_row_idx: int, header_row_idx: int, max_col: int, filter_row_idx: Optional[int] = None, num_flags_c: int = 1):
    """Setup new columns - headers only, returns column indices
    
    Optimized version that only sets up headers, doesn't style data rows
    
    Args:
        num_flags_c: Number of Flag-C columns (dynamic based on actual data, default 1)
    """
    # Column indices - no 1.0 section (Source/Item are now next to Mã NPL/SP)
    # FIXED layout: Separator ALWAYS at BE (col 57), Flag ALWAYS at BF (col 58)
    FIXED_SEPARATOR_COL = 57  # BE - always separator here
    FIXED_FLAG_COL = 58       # BF - always Flag here
    
    empty_col_0 = FIXED_SEPARATOR_COL     # Always BE (57)
    sec_11_flag_col = FIXED_FLAG_COL      # Always BF (58)
    
    empty_col_1 = sec_11_flag_col + 1
    sec_21_rpt_col = empty_col_1 + 1
    sec_21_ampersand_col = sec_21_rpt_col + 1
    sec_21_flag_col = sec_21_ampersand_col + 1
    empty_col_3 = sec_21_flag_col + 1
    flow_col = empty_col_3 + 1
    min_before_col = flow_col + 1
    max_before_col = min_before_col + 1
    min_after_col = max_before_col + 1
    max_after_col = min_after_col + 1
    min_120_col = max_after_col + 1
    max_120_col = min_120_col + 1
    variance_col = max_120_col + 1
    hs_max_duty_col = variance_col + 1
    duty_rate_col = hs_max_duty_col + 1
    impact_col = duty_rate_col + 1
    empty_col_4 = impact_col + 1
    sec_23_flag_col = empty_col_4 + 1
    empty_col_5 = sec_23_flag_col + 1
    
    # Section 3.1: Transaction notes, Chemical notes, &, Exclusion, Flag 1-5, Flag 1-C (dynamic)
    NUM_FLAGS = 5
    NUM_FLAGS_C = max(num_flags_c, 1) if num_flags_c > 0 else 0  # Use dynamic count
    
    sec_31_transaction_notes_col = empty_col_5 + 1
    sec_31_chemical_notes_col = sec_31_transaction_notes_col + 1
    sec_31_ampersand_col = sec_31_chemical_notes_col + 1
    sec_31_exclusion_col = sec_31_ampersand_col + 1
    
    # Flag 1-5 columns
    sec_31_flag_cols = []
    current_col = sec_31_exclusion_col + 1
    for i in range(NUM_FLAGS):
        sec_31_flag_cols.append(current_col)
        current_col += 1
    
    # Flag 1-C to 3-C columns
    sec_31_flag_c_cols = []
    for i in range(NUM_FLAGS_C):
        sec_31_flag_c_cols.append(current_col)
        current_col += 1
    
    last_col = current_col - 1
    sec_31_flag_col = sec_31_flag_cols[0] if sec_31_flag_cols else sec_31_exclusion_col + 1
    
    # Set column widths
    column_widths = {
        empty_col_0: 2,           # BE (57) - separator
        sec_11_flag_col: 12, empty_col_1: 2,
        sec_21_rpt_col: 12, sec_21_ampersand_col: 25, sec_21_flag_col: 12, empty_col_3: 2,
        flow_col: 10, min_before_col: 15, max_before_col: 15,
        min_after_col: 15, max_after_col: 15, min_120_col: 15,
        max_120_col: 15, variance_col: 12, hs_max_duty_col: 12,
        duty_rate_col: 12, impact_col: 12, empty_col_4: 2,
        sec_23_flag_col: 12, empty_col_5: 2,
        sec_31_transaction_notes_col: 18,
        sec_31_chemical_notes_col: 15,
        sec_31_ampersand_col: 25,
        sec_31_exclusion_col: 15,
    }
    for flag_col in sec_31_flag_cols:
        column_widths[flag_col] = 12
    for flag_c_col in sec_31_flag_c_cols:
        column_widths[flag_c_col] = 12
    
    for col_idx, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Write section headers (minimal styling)
    section_headers = [
        (sec_11_flag_col, "1.1 / 1.2"),
        (sec_21_rpt_col, "2.1"),
        (flow_col, "2.2"),
        (sec_23_flag_col, "2.3"),
        (sec_31_transaction_notes_col, "3.1"),
    ]
    for col, text in section_headers:
        cell = ws.cell(row=section_row_idx, column=col, value=text)
        cell.font = SECTION_HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = SECTION_HEADER_ALIGNMENT
    
    # Fill section header ranges
    for col in range(sec_21_rpt_col + 1, sec_21_flag_col + 1):
        ws.cell(row=section_row_idx, column=col).fill = HEADER_FILL
    for col in range(flow_col + 1, impact_col + 1):
        ws.cell(row=section_row_idx, column=col).fill = HEADER_FILL
    # Fill 3.1 range
    for col in range(sec_31_transaction_notes_col + 1, last_col + 1):
        ws.cell(row=section_row_idx, column=col).fill = HEADER_FILL
    
    # Write column headers
    # Empty columns
    empty_cols_list = [empty_col_0, empty_col_1, empty_col_3, empty_col_4, empty_col_5]
    for col in empty_cols_list:
        ws.cell(row=header_row_idx, column=col, value="").border = NO_BORDER
    
    # Yellow headers (yellow bg black text)
    yellow_headers = [
        (sec_11_flag_col, "Flag"),
        (sec_21_rpt_col, "RPT"), (sec_21_ampersand_col, "&"), (sec_21_flag_col, "Flag"),
        (hs_max_duty_col, "HS Code\n(with highest\nImport Duty\nrate)"),
        (duty_rate_col, "Import Duty\nrate (MAX)"),
        (impact_col, "Impact\namount"),
        (sec_23_flag_col, "Flag"),
        (sec_31_transaction_notes_col, "Transaction\nnotes"),
        (sec_31_chemical_notes_col, "Chemical\nnotes"),
        (sec_31_ampersand_col, "&"),
        (sec_31_exclusion_col, "Exclusion"),
    ]
    for col, text in yellow_headers:
        cell = ws.cell(row=header_row_idx, column=col, value=text)
        cell.font = NEW_COL_HEADER_FONT
        cell.fill = NEW_COL_HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Flag 1-5 headers
    for i, flag_col in enumerate(sec_31_flag_cols, 1):
        cell = ws.cell(row=header_row_idx, column=flag_col, value=f"Flag {i}")
        cell.font = NEW_COL_HEADER_FONT
        cell.fill = NEW_COL_HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Flag 1-C to 3-C headers (red background with gray text #c4c4cd)
    FLAG_C_FILL = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    FLAG_C_FONT = Font(name="Arial", bold=True, size=10, color="C4C4CD")
    for i, flag_c_col in enumerate(sec_31_flag_c_cols, 1):
        cell = ws.cell(row=header_row_idx, column=flag_c_col, value=f"Flag {i}-C")
        cell.font = FLAG_C_FONT
        cell.fill = FLAG_C_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    # Dark headers (yellow text black bg)
    dark_headers = [
        (flow_col, "Flow"),
        (min_before_col, "MIN value in\nthe 60-day period,\nBEFORE the\nCD date"),
        (max_before_col, "MAX value in\nthe 60-day period,\nBEFORE the\nCD date"),
        (min_after_col, "MIN value in\nthe 60-day period,\nAFTER the CD\ndate"),
        (max_after_col, "MAX value in\nthe 60-day period,\nAFTER the CD\ndate"),
        (min_120_col, "MIN value in\nthe\nentire 120-day\nperiod"),
        (max_120_col, "MAX value in\nthe\nentire 120-day\nperiod"),
        (variance_col, "Variance\nRange\n(120-day\nperiod)"),
    ]
    for col, text in dark_headers:
        cell = ws.cell(row=header_row_idx, column=col, value=text)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = NEW_COL_HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    
    return {
        'empty_col_0': empty_col_0, 'sec_11_flag_col': sec_11_flag_col,
        'empty_col_1': empty_col_1, 'sec_21_rpt_col': sec_21_rpt_col,
        'sec_21_ampersand_col': sec_21_ampersand_col,
        'sec_21_flag_col': sec_21_flag_col, 'empty_col_3': empty_col_3,
        'flow_col': flow_col, 'min_before_col': min_before_col,
        'max_before_col': max_before_col, 'min_after_col': min_after_col,
        'max_after_col': max_after_col, 'min_120_col': min_120_col,
        'max_120_col': max_120_col, 'variance_col': variance_col,
        'hs_max_duty_col': hs_max_duty_col, 'duty_rate_col': duty_rate_col,
        'impact_col': impact_col, 'empty_col_4': empty_col_4,
        'sec_23_flag_col': sec_23_flag_col, 'empty_col_5': empty_col_5,
        'sec_31_transaction_notes_col': sec_31_transaction_notes_col,
        'sec_31_chemical_notes_col': sec_31_chemical_notes_col,
        'sec_31_ampersand_col': sec_31_ampersand_col,
        'sec_31_exclusion_col': sec_31_exclusion_col,
        'sec_31_flag_col': sec_31_flag_col,
        'sec_31_flag_cols': sec_31_flag_cols,
        'sec_31_flag_c_cols': sec_31_flag_c_cols,
        'last_col': last_col,
    }


def _build_new_col_values(computed: Dict, cols: Dict, enabled_sections: Set[str]) -> List:
    """Build list of values for new columns from pre-computed data"""
    # Placeholder for "[To fill]" columns (data rows)
    TO_FILL = "[To fill]"
    
    # Number of flag columns from cols dict (dynamic)
    NUM_FLAGS = len(cols.get('sec_31_flag_cols', [])) or 5
    NUM_FLAGS_C = len(cols.get('sec_31_flag_c_cols', []))  # Dynamic based on actual data
    
    values = [
        None,  # empty_col_0
        computed.get('sec_11_flag', ''),  # sec_11_flag_col
        None,  # empty_col_1
        '',  # sec_21_rpt_col (RPT)
        computed.get('sec_21_ampersand', ''),  # sec_21_ampersand_col (&)
        '',  # sec_21_flag_col
        None,  # empty_col_3
        computed.get('flow', ''),  # flow_col
        TO_FILL if "2" in enabled_sections else '',  # min_before_col
        TO_FILL if "2" in enabled_sections else '',  # max_before_col
        TO_FILL if "2" in enabled_sections else '',  # min_after_col
        TO_FILL if "2" in enabled_sections else '',  # max_after_col
        TO_FILL if "2" in enabled_sections else '',  # min_120_col
        TO_FILL if "2" in enabled_sections else '',  # max_120_col
        TO_FILL if "2" in enabled_sections else '',  # variance_col
        computed.get('hs_max_duty', ''),  # hs_max_duty_col
        computed.get('duty_rate_max', ''),  # duty_rate_col
        '',  # impact_col
        None,  # empty_col_4
        computed.get('sec_23_flag', ''),  # sec_23_flag_col
        None,  # empty_col_5
        computed.get('sec_31_transaction_notes', ''),  # sec_31_transaction_notes_col
        computed.get('sec_31_chemical_notes', ''),  # sec_31_chemical_notes_col
        computed.get('sec_31_ampersand', ''),  # sec_31_ampersand_col (&)
        computed.get('sec_31_exclusion', ''),  # sec_31_exclusion_col
    ]
    
    # Flag 1-5 columns
    for i in range(NUM_FLAGS):
        flag_val = computed.get('sec_31_flag', '')
        values.append(TO_FILL if flag_val else '')
    
    # Flag 1-C columns (chemical only) - dynamic count
    is_chemical = computed.get('sec_31_chemical_notes', '') == 'Chemical'
    for i in range(NUM_FLAGS_C):
        if "3" in enabled_sections and is_chemical:
            values.append(TO_FILL)
        else:
            values.append('')
    
    return values


def _apply_styles_batch(
    ws, start_row: int, end_row: int, 
    original_max_col: int, date_columns: Set[int], 
    numeric_columns: Set[int], col_indices: Dict, cols: Dict
):
    """Apply styles to data cells in batch - OPTIMIZED VERSION
    
    Applies borders and alignment to ALL data cells (both original and new columns).
    All cells get Middle Align (vertical="center").
    """
    # Empty separator columns (exclude from borders)
    # empty_col_0 is ALWAYS at BE (57) as separator
    empty_cols = {cols['empty_col_0'], cols['empty_col_1'], cols['empty_col_3'], 
                  cols['empty_col_4'], cols['empty_col_5']}
    
    total_cols = cols['last_col']
    num_rows = end_row - start_row + 1
    
    # Italic font for "[To fill]" columns (data rows)
    ITALIC_FONT = Font(name="Arial", size=10, italic=True)
    to_fill_cols = {cols['min_before_col'], cols['max_before_col'], 
                    cols['min_after_col'], cols['max_after_col'],
                    cols['min_120_col'], cols['max_120_col'], cols['variance_col']}
    
    # All added/new columns start from section columns (sec_11_flag_col)
    new_col_start = cols['sec_11_flag_col']
    
    # New columns that should be RIGHT-aligned (numeric values)
    right_align_new_cols = {cols['duty_rate_col'], cols['impact_col']}
    
    logger.info(f"Applying styles to {total_cols} columns × {num_rows} rows")
    
    # Apply borders and alignment to ALL cells (both original and new columns)
    for row_idx in range(start_row, end_row + 1):
        for col_idx in range(1, total_cols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            
            if col_idx in empty_cols:
                # Empty separator columns - no border
                pass
            else:
                cell.border = THIN_BORDER
                
                # Apply italic font to "[To fill]" columns (data rows)
                if col_idx in to_fill_cols:
                    cell.font = ITALIC_FONT
                    cell.alignment = CENTER_ALIGNMENT
                elif col_idx in right_align_new_cols:
                    # Import Duty rate (MAX), Impact amount - RIGHT aligned
                    cell.alignment = NUMBER_ALIGNMENT
                elif col_idx >= new_col_start:
                    # Apply alignment to added columns
                    cell.alignment = CELL_ALIGNMENT
                else:
                    # Apply alignment to ORIGINAL data columns (Middle Align)
                    # Numeric columns: right-aligned, Text columns: left-aligned
                    if col_idx in numeric_columns:
                        cell.alignment = NUMBER_ALIGNMENT
                    else:
                        cell.alignment = CELL_ALIGNMENT
                
                # Apply date format
                if col_idx in date_columns and cell.value is not None:
                    cell.number_format = DATE_FORMAT
                # Apply number format
                elif col_idx in numeric_columns and isinstance(cell.value, (int, float)):
                    cell.number_format = NUMBER_FORMAT


def _create_input_from_dataframe(
    wb: Workbook,
    df: pd.DataFrame,
    sheet_title: str,
    npl_to_ip_hs: Dict[str, str],
    flow_dieu_kien_npl_to_ip_vv: Dict[str, str],
    npl_to_23_flag: Dict[str, str] = None,
    enabled_sections: Optional[Set[str]] = None,
    flag_31_mapping: Dict[Tuple, str] = None,
    flag_32_mapping: Dict[Tuple, str] = None,
    exclusion_31_mapping: Dict[Tuple, str] = None,
    prefill_map: Dict[Tuple, Tuple] = None,
    num_flags_c: int = 1
) -> bool:
    """Create input sheet from DataFrame - fallback method
    
    This method uses Excel formulas instead of pre-computed values
    for MIN/MAX calculations.
    """
    if npl_to_23_flag is None:
        npl_to_23_flag = {}
    if flag_31_mapping is None:
        flag_31_mapping = {}
    if flag_32_mapping is None:
        flag_32_mapping = {}
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3"}
    tariff_rates = load_tariff_rates()
    
    try:
        ws_input = wb.create_sheet(sheet_title, 0)
        ws_input.sheet_view.showGridLines = False
        ws_input.sheet_view.zoomScale = 80
        ws_input.sheet_properties.tabColor = "2E2E38"  # Black tab
        
        columns = list(df.columns)
        
        # Find column indices
        col_mapping = _find_dataframe_columns(columns)
        
        # Detect date and numeric columns
        date_columns = set()
        numeric_columns = set()
        
        for col_idx, header in enumerate(columns, 1):
            header_str = str(header).lower()
            if any(kw in header_str for kw in ['ngày', 'ngay', 'date']):
                date_columns.add(col_idx)
            if any(kw in header_str for kw in ['trị giá', 'tri gia', 'tiền', 'tien', 'giá', 'gia', 'lượng', 'luong', 'thuế', 'thue', 'số lượng', 'so luong']):
                numeric_columns.add(col_idx)
        
        max_col = len(columns)
        
        # FIXED LAYOUT (matches xlsx/xlsb paths):
        # Rows 1-9: Empty (no metadata for DataFrame path)
        # Row 8: Section headers (1.1/1.2, 2.1, etc.) at cols 57+
        # Row 9: Preprocess row at cols 57+
        # Row 10: Column headers (Flag, RPT, &, Flow, etc.)
        # Row 11: Filter/formula row
        # Row 12+: Data
        SECTION_ROW = 8
        HEADER_ROW = 10
        FILTER_ROW = 11
        DATA_START_ROW = 12
        
        # Build output column mapping: skip ALL preprocess columns, insert 2 new after NPL
        # Save original col_mapping for DataFrame row access (before shifting)
        orig_col_mapping = dict(col_mapping)
        npl_col_orig = col_mapping.get('npl_col_idx')
        
        skip_cols_df: Set[int] = col_mapping.get('preprocess_skip_cols', set()).copy()
        if col_mapping.get('source_col_idx'):
            skip_cols_df.add(col_mapping['source_col_idx'])
        if col_mapping.get('item_col_idx'):
            skip_cols_df.add(col_mapping['item_col_idx'])
        # Never skip the NPL column itself
        if npl_col_orig and npl_col_orig in skip_cols_df:
            skip_cols_df.discard(npl_col_orig)
        
        col_map_df, max_col_output, source_item_cols = _build_output_col_map(max_col, npl_col_orig, skip_cols_df)
        
        # Update col_mapping to output positions
        for key in list(col_mapping.keys()):
            if col_mapping[key] is not None:
                mapped = col_map_df.get(col_mapping[key])
                if mapped is not None:
                    col_mapping[key] = mapped
        
        # Update date/numeric column sets to output positions
        date_columns = {col_map_df[c] for c in date_columns if col_map_df.get(c) is not None}
        numeric_columns = {col_map_df[c] for c in numeric_columns if col_map_df.get(c) is not None}
        
        max_col = max_col_output
        
        # Write original headers (with column mapping, skip Source/Item)
        for col_idx, header in enumerate(columns, 1):
            out_col = col_map_df.get(col_idx)
            if out_col is not None:
                cell = ws_input.cell(row=HEADER_ROW, column=out_col, value=header)
                cell.font = INPUT_HEADER_FONT
                cell.border = THIN_BORDER
                cell.alignment = HEADER_ALIGNMENT
        
        # Write headers for the 2 new columns next to Mã NPL/SP
        if source_item_cols:
            for col, text in [(source_item_cols[0], "Mã NPL/SP\n(Suggested)"), (source_item_cols[1], "Rationale")]:
                cell = ws_input.cell(row=HEADER_ROW, column=col, value=text)
                cell.font = NEW_COL_HEADER_FONT
                cell.fill = NEW_COL_HEADER_FILL
                cell.alignment = NEW_COL_HEADER_ALIGNMENT
                cell.border = THIN_BORDER
        
        # Data will start at row 12
        max_row = DATA_START_ROW + len(df) - 1
        
        # Set column widths for original columns
        for col_idx in range(1, max_col + 1):
            if source_item_cols and col_idx in source_item_cols:
                continue  # Set separately
            ws_input.column_dimensions[get_column_letter(col_idx)].width = STANDARD_COLUMN_WIDTH
        
        # Set column widths for new source/item columns
        if source_item_cols:
            ws_input.column_dimensions[get_column_letter(source_item_cols[0])].width = 16
            ws_input.column_dimensions[get_column_letter(source_item_cols[1])].width = 12
        
        # Set header row height
        ws_input.row_dimensions[HEADER_ROW].height = TITLE_ROW_HEIGHT
        
        # Determine if preprocess was used (prefill_map has data)
        _has_preprocess = bool(prefill_map)
        
        # Setup new columns (section headers at row 10 same as column headers, formulas at row 11)
        cols = _setup_new_columns(ws_input, SECTION_ROW, HEADER_ROW, max_col, FILTER_ROW, col_indices=col_mapping, source_item_cols=source_item_cols, preprocess_row_idx=None, has_preprocess=_has_preprocess, num_flags_c=num_flags_c)
        
        # Add auto filter starting from row 4 (filter row) including all columns
        filter_range = f"A{FILTER_ROW}:{get_column_letter(cols['last_col'])}{max_row}"
        ws_input.auto_filter.ref = filter_range
        
        # Get column indices (use ORIGINAL mapping for DataFrame row access)
        tong_so_luong_col_idx = orig_col_mapping.get('tong_so_luong_col_idx')
        
        # Build NPL -> HS codes mapping (use original indices for DataFrame access)
        orig_npl_col_idx = orig_col_mapping.get('npl_col_idx')
        orig_ma_hs_col_idx = orig_col_mapping.get('ma_hs_col_idx')
        npl_to_hs_codes = {}
        
        if orig_ma_hs_col_idx:
            for row in df.itertuples(index=False):
                # Get NPL value (can be empty)
                npl = ""
                if orig_npl_col_idx and orig_npl_col_idx <= len(row):
                    npl_val = row[orig_npl_col_idx - 1]
                    if npl_val and not pd.isna(npl_val):
                        npl = str(npl_val).strip()
                
                # Get HS code
                ma_hs_val = row[orig_ma_hs_col_idx - 1] if orig_ma_hs_col_idx <= len(row) else None
                if ma_hs_val and not pd.isna(ma_hs_val):
                    ma_hs = str(ma_hs_val).strip()
                    if ma_hs.replace('.', '').replace(',', '').isdigit():
                        ma_hs = str(int(float(ma_hs))).zfill(8)
                    # Include empty NPL/SP as valid group (empty string is also a valid key)
                    if ma_hs:
                        if npl not in npl_to_hs_codes:
                            npl_to_hs_codes[npl] = set()
                        npl_to_hs_codes[npl].add(ma_hs)
        
        # Write data rows with formulas (start from row 12: row 8=section, row 9=preprocess, row 10=header, row 11=filter)
        for row_idx, row in enumerate(df.itertuples(index=False), DATA_START_ROW):
            # Write original data (with column mapping, skip Source/Item)
            for col_idx, value in enumerate(row, 1):
                out_col = col_map_df.get(col_idx)
                if out_col is None:
                    continue  # Skip original Source/Item columns
                if pd.isna(value):
                    value = None
                cell = ws_input.cell(row=row_idx, column=out_col, value=value)
                cell.font = CELL_FONT
                cell.border = THIN_BORDER
                
                # Apply alignment: numeric columns right-aligned, text columns left-aligned
                # All with vertical center (Middle Align)
                if out_col in numeric_columns:
                    cell.alignment = NUMBER_ALIGNMENT
                else:
                    cell.alignment = CELL_ALIGNMENT
                
                # Apply date format for date columns (date_columns has output positions)
                if out_col in date_columns and value is not None:
                    cell.number_format = DATE_FORMAT
                # Apply number format for numeric columns (numeric_columns has output positions)
                elif out_col in numeric_columns and value is not None and isinstance(value, (int, float)):
                    cell.number_format = NUMBER_FORMAT
            
            # Get values for new columns (use ORIGINAL col indices for DataFrame row access)
            flow_str = ""
            dieu_kien_str = ""
            npl_str = ""
            so_tk_str = ""
            tsl_str = ""
            ma_hs_str = ""
            
            if orig_col_mapping.get('ma_loai_hinh_col_idx'):
                idx = orig_col_mapping['ma_loai_hinh_col_idx'] - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        flow_str = get_flow_from_ma_loai_hinh(str(val).strip()).value
            
            if orig_col_mapping.get('dieu_kien_col_idx'):
                idx = orig_col_mapping['dieu_kien_col_idx'] - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        dieu_kien_str = str(val).strip()
            
            if orig_npl_col_idx:
                idx = orig_npl_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        npl_str = str(val).strip()
            
            if orig_col_mapping.get('so_tk_col_idx'):
                idx = orig_col_mapping['so_tk_col_idx'] - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        so_tk_str = str(int(val) if isinstance(val, float) else val).strip()
            
            # Extract Mã hiệu PTVC for Transaction notes
            ma_hieu_ptvc_str = ""
            if orig_col_mapping.get('ma_hieu_ptvc_col_idx'):
                idx = orig_col_mapping['ma_hieu_ptvc_col_idx'] - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        ma_hieu_ptvc_str = str(int(val) if isinstance(val, float) else val).strip()
            
            if tong_so_luong_col_idx:
                idx = tong_so_luong_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        tsl_str = str(val).strip()
            
            if orig_ma_hs_col_idx:
                idx = orig_ma_hs_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        ma_hs_str = str(val).strip()
                        if ma_hs_str.replace('.', '').replace(',', '').isdigit():
                            ma_hs_str = str(int(float(ma_hs_str))).zfill(8)
            
            ten_hang_str = ""
            ten_hang_col_idx = orig_col_mapping.get('ten_hang_col_idx')
            if ten_hang_col_idx:
                idx = ten_hang_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        ten_hang_str = str(val).strip()
            
            # Fallback HS code
            if not ma_hs_str and npl_str:
                hs_codes = npl_to_hs_codes.get(npl_str, set())
                if hs_codes:
                    ma_hs_str = next(iter(hs_codes))
            
            # Extract source/item from preprocess columns (original indices)
            source_str = ""
            item_str = ""
            orig_source_col_idx = orig_col_mapping.get('source_col_idx')
            orig_item_col_idx = orig_col_mapping.get('item_col_idx')
            if orig_source_col_idx:
                idx = orig_source_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        source_str = str(val).strip()
            if orig_item_col_idx:
                idx = orig_item_col_idx - 1
                if idx < len(row):
                    val = row[idx]
                    if val and not pd.isna(val):
                        item_str = str(val).strip()
            
            # Write source/item to new columns next to Mã NPL/SP
            if source_item_cols:
                # Override with prefill data if available
                if prefill_map and not source_str:
                    key = (so_tk_str.strip(), ten_hang_str.strip())
                    if key in prefill_map:
                        source_str, item_str = prefill_map[key]
                    elif ten_hang_str.strip() and ('__TH__', ten_hang_str.strip()) in prefill_map:
                        source_str, item_str = prefill_map[('__TH__', ten_hang_str.strip())]
                _write_cell(ws_input, row_idx, source_item_cols[0], source_str, CELL_ALIGNMENT)
                _write_cell(ws_input, row_idx, source_item_cols[1], item_str, CELL_ALIGNMENT)
            
            # Write new columns based on enabled_sections
            # Empty separators first
            for col_key in ['empty_col_0', 'empty_col_1', 'empty_col_3', 'empty_col_4', 'empty_col_5']:
                if col_key in cols:
                    ws_input.cell(row=row_idx, column=cols[col_key], value="").border = NO_BORDER
            
            # Section 1.1/1.2 Flag column - only fill if "1" (Tariff Classification) is enabled
            if 'sec_11_flag_col' in cols:
                if "1" in enabled_sections:
                    ip_value = npl_to_ip_hs.get(npl_str, "") if npl_str else ""
                    _write_cell(ws_input, row_idx, cols['sec_11_flag_col'], ip_value, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_11_flag_col'], "", CELL_ALIGNMENT)
            
            # Section 2.1 columns: RPT, "&", Flag
            if 'sec_21_rpt_col' in cols:
                _write_cell(ws_input, row_idx, cols['sec_21_rpt_col'], "", CELL_ALIGNMENT)
            if 'sec_21_ampersand_col' in cols:
                if "2" in enabled_sections:
                    ten_doi_tac_str = ""
                    orig_tdt_idx = orig_col_mapping.get('ten_doi_tac_col_idx')
                    if orig_tdt_idx:
                        idx_val = orig_tdt_idx - 1
                        if idx_val < len(row):
                            val = row[idx_val]
                            if val and not pd.isna(val):
                                ten_doi_tac_str = str(val).strip()
                    # Use source_str (LLM-filled) if available, otherwise use npl_str (original)
                    npl_for_ampersand = source_str if source_str else npl_str
                    ampersand_val = f"{npl_for_ampersand}/{ten_doi_tac_str}/{flow_str}/{dieu_kien_str}"
                    _write_cell(ws_input, row_idx, cols['sec_21_ampersand_col'], ampersand_val, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_21_ampersand_col'], "", CELL_ALIGNMENT)
            if 'sec_21_flag_col' in cols:
                if "2" in enabled_sections and 'sec_21_ampersand_col' in cols:
                    ampersand_col_letter = get_column_letter(cols['sec_21_ampersand_col'])
                    formula = f"=IFERROR(VLOOKUP({ampersand_col_letter}{row_idx},'2.1'!$O:$P,COLUMNS('2.1'!$O:$P),0),\"\")"
                    cell = ws_input.cell(row=row_idx, column=cols['sec_21_flag_col'], value=formula)
                    cell.font = CELL_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CELL_ALIGNMENT
                else:
                    _write_cell(ws_input, row_idx, cols['sec_21_flag_col'], "", CELL_ALIGNMENT)
            
            # Section 2.2 columns - only fill if "2" (Customs Valuation) is enabled
            if "2" in enabled_sections:
                _write_cell(ws_input, row_idx, cols['flow_col'], flow_str, CENTER_ALIGNMENT)
                
                # Section 2.2 formula columns: write "[To fill]" in italic (data rows)
                ITALIC_FONT = Font(name="Arial", size=10, italic=True)
                to_fill_cols = [
                    cols['min_before_col'], cols['max_before_col'],
                    cols['min_after_col'], cols['max_after_col'],
                    cols['min_120_col'], cols['max_120_col'],
                    cols['variance_col']
                ]
                for col_idx in to_fill_cols:
                    cell = ws_input.cell(row=row_idx, column=col_idx, value="[To fill]")
                    cell.font = ITALIC_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CENTER_ALIGNMENT
                
                # Find HS code with highest duty rate for this NPL/SP
                hs_max_duty = ""
                duty_rate_max = ""
                if npl_str in npl_to_hs_codes:
                    hs_codes = npl_to_hs_codes[npl_str]
                    max_rate = -1
                    best_hs = ""
                    first_hs = ""
                    for hs_code in sorted(hs_codes):
                        hs_8 = hs_code[:8] if len(hs_code) >= 8 else hs_code
                        if not first_hs:
                            first_hs = hs_8
                        tax_str = tariff_rates.get(hs_8, "")
                        if tax_str:
                            numeric_val, _ = parse_tax_value(str(tax_str))
                            if numeric_val is not None and numeric_val > max_rate:
                                max_rate = numeric_val
                                best_hs = hs_8
                                duty_rate_max = numeric_val
                    if best_hs:
                        hs_max_duty = best_hs
                    elif first_hs:
                        hs_max_duty = first_hs
                        duty_rate_max = "N/A"
                elif ma_hs_str:
                    hs_8 = ma_hs_str[:8] if len(ma_hs_str) >= 8 else ma_hs_str
                    hs_max_duty = hs_8
                    tax_str = tariff_rates.get(hs_8, "")
                    if tax_str:
                        numeric_val, _ = parse_tax_value(str(tax_str))
                        if numeric_val is not None:
                            duty_rate_max = numeric_val
                        else:
                            duty_rate_max = "N/A"
                    else:
                        duty_rate_max = "N/A"
                
                # Write HS code with highest duty rate (left aligned)
                cell = ws_input.cell(row=row_idx, column=cols['hs_max_duty_col'], value=hs_max_duty)
                cell.font = CELL_FONT
                cell.border = THIN_BORDER
                cell.alignment = CELL_ALIGNMENT
                
                # Write Import Duty rate (MAX) - numeric value, right aligned
                cell = ws_input.cell(row=row_idx, column=cols['duty_rate_col'], value=duty_rate_max)
                cell.font = CELL_FONT
                cell.border = THIN_BORDER
                cell.alignment = NUMBER_ALIGNMENT
                
                # Impact amount column - numeric value, right aligned
                cell = ws_input.cell(row=row_idx, column=cols['impact_col'], value="")
                cell.font = CELL_FONT
                cell.border = THIN_BORDER
                cell.alignment = NUMBER_ALIGNMENT
            else:
                # Section 2.2 not enabled - write empty cells with borders
                # Use appropriate alignment for each column type
                sec_22_center_cols = [cols['flow_col']]  # Only Flow is centered
                sec_22_left_cols = [cols['hs_max_duty_col']]  # HS code is left-aligned
                sec_22_number_cols = [
                    cols['min_before_col'], cols['max_before_col'],
                    cols['min_after_col'], cols['max_after_col'], cols['min_120_col'],
                    cols['max_120_col'], cols['variance_col'],
                    cols['duty_rate_col'], cols['impact_col']
                ]
                for col_idx in sec_22_center_cols:
                    cell = ws_input.cell(row=row_idx, column=col_idx, value="")
                    cell.font = CELL_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CENTER_ALIGNMENT
                for col_idx in sec_22_left_cols:
                    cell = ws_input.cell(row=row_idx, column=col_idx, value="")
                    cell.font = CELL_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CELL_ALIGNMENT
                for col_idx in sec_22_number_cols:
                    cell = ws_input.cell(row=row_idx, column=col_idx, value="")
                    cell.font = CELL_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = NUMBER_ALIGNMENT
            
            # Section 2.3 Flag column - only fill if "2" (Customs Valuation) is enabled
            if 'sec_23_flag_col' in cols:
                if "2" in enabled_sections:
                    flag_23_value = npl_to_23_flag.get(npl_str, "") if npl_str else ""
                    _write_cell(ws_input, row_idx, cols['sec_23_flag_col'], flag_23_value, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_23_flag_col'], "", CELL_ALIGNMENT)
            
            # Section 3.1 Flag + Exclusion columns - only fill if "3" (Non-Tariff Measures) is enabled
            flow_vn = "Nhập" if flow_str == "Nhập" or flow_str == "NHAP" else "Xuất" if flow_str else ""
            hs_code_6 = ma_hs_str[:6] if ma_hs_str and len(ma_hs_str) >= 6 else ma_hs_str
            flag_31_key = (flow_vn, hs_code_6, npl_str, ten_hang_str)
            
            if 'sec_31_flag_col' in cols:
                if "3" in enabled_sections and flag_31_mapping:
                    flag_31_value = flag_31_mapping.get(flag_31_key, "")
                    _write_cell(ws_input, row_idx, cols['sec_31_flag_col'], flag_31_value, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_31_flag_col'], "", CELL_ALIGNMENT)
            
            # Import helper functions for consistency
            from .output import _get_transaction_notes, _get_chemical_notes
            
            # Section 3.1 Transaction notes column
            if 'sec_31_transaction_notes_col' in cols:
                if "3" in enabled_sections:
                    transaction_notes = _get_transaction_notes(ma_hieu_ptvc_str)
                    _write_cell(ws_input, row_idx, cols['sec_31_transaction_notes_col'], transaction_notes, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_31_transaction_notes_col'], "", CELL_ALIGNMENT)
            
            # Section 3.1 Chemical notes column
            if 'sec_31_chemical_notes_col' in cols:
                if "3" in enabled_sections:
                    chemical_notes = _get_chemical_notes(ma_hs_str)
                    _write_cell(ws_input, row_idx, cols['sec_31_chemical_notes_col'], chemical_notes, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_31_chemical_notes_col'], "", CELL_ALIGNMENT)
            
            # Section 3.1 "&" column
            if 'sec_31_ampersand_col' in cols:
                if "3" in enabled_sections:
                    # Use so_tk_str already extracted above
                    ampersand_31_val = f"{npl_str}/{so_tk_str}"
                    _write_cell(ws_input, row_idx, cols['sec_31_ampersand_col'], ampersand_31_val, CELL_ALIGNMENT)
                else:
                    _write_cell(ws_input, row_idx, cols['sec_31_ampersand_col'], "", CELL_ALIGNMENT)
            
            # Section 3.1 Exclusion column - use VLOOKUP to get value from sheet 3.1 (human filled)
            if 'sec_31_exclusion_col' in cols:
                if "3" in enabled_sections:
                    # Use VLOOKUP formula to get Exclusion from sheet 3.1 using & as lookup key
                    sec_31_ampersand_letter = get_column_letter(cols['sec_31_ampersand_col'])
                    exclusion_formula = f'=IFERROR(VLOOKUP({sec_31_ampersand_letter}{row_idx},\'3.1\'!$O:$P,2,0),"")'
                    cell = ws_input.cell(row=row_idx, column=cols['sec_31_exclusion_col'], value=exclusion_formula)
                    cell.font = CELL_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CELL_ALIGNMENT
                else:
                    _write_cell(ws_input, row_idx, cols['sec_31_exclusion_col'], "", CELL_ALIGNMENT)
            
            # Section 3.1 Flag columns (Flag 1-5)
            if 'sec_31_flag_cols' in cols:
                flag_31_value = flag_31_mapping.get(flag_31_key, "") if ("3" in enabled_sections and flag_31_mapping) else ""
                for flag_col in cols['sec_31_flag_cols']:
                    _write_cell(ws_input, row_idx, flag_col, "[To fill]" if flag_31_value else "", CELL_ALIGNMENT)
            
            # Section 3.1 Flag-C columns (Flag 1-C to 3-C) - chemical only
            if 'sec_31_flag_c_cols' in cols:
                chemical_notes = _get_chemical_notes(ma_hs_str) if ma_hs_str else "Non-chemical"
                for flag_c_col in cols['sec_31_flag_c_cols']:
                    if "3" in enabled_sections and chemical_notes == "Chemical":
                        _write_cell(ws_input, row_idx, flag_c_col, "[To fill]", CELL_ALIGNMENT)
                    else:
                        _write_cell(ws_input, row_idx, flag_c_col, "", CELL_ALIGNMENT)
        
        # Set standard row height for data rows (row 4+)
        for row_idx in range(4, max_row + 1):
            ws_input.row_dimensions[row_idx].height = STANDARD_ROW_HEIGHT
        
        # Add dropdown list for RPT column with "Related" or "Not related"
        from openpyxl.worksheet.datavalidation import DataValidation
        rpt_col_letter = get_column_letter(cols['sec_21_rpt_col'])
        rpt_validation = DataValidation(
            type="list",
            formula1='"Related,Not related"',
            allow_blank=True,
            showDropDown=False,
            showErrorMessage=True,
            errorTitle="Invalid Input",
            error="Please select 'Related' or 'Not related'"
        )
        rpt_validation.add(f"{rpt_col_letter}{DATA_START_ROW}:{rpt_col_letter}{max_row}")
        ws_input.add_data_validation(rpt_validation)
        
        # Freeze from data start row AFTER "Mã loại hình" column (include that column in freeze)
        ma_loai_hinh_col = col_mapping.get('ma_loai_hinh_col_idx', 1)
        freeze_col = (ma_loai_hinh_col + 1) if ma_loai_hinh_col else 2
        freeze_col_letter = get_column_letter(freeze_col)
        ws_input.freeze_panes = f"{freeze_col_letter}{DATA_START_ROW}"
        return True
        
    except Exception as e:
        logger.error(f"Failed to create input from DataFrame: {e}")
        return False


def _write_formula_cell(ws, row_idx: int, col_idx: int, formula: str):
    """Write a formula cell with number formatting"""
    cell = ws.cell(row=row_idx, column=col_idx, value=formula)
    cell.font = CELL_FONT
    cell.border = THIN_BORDER
    cell.alignment = NUMBER_ALIGNMENT
    cell.number_format = NUMBER_FORMAT


def _find_dataframe_columns(columns: List) -> Dict[str, Optional[int]]:
    """Find column indices in a DataFrame"""
    result = {
        'npl_col_idx': None,
        'dieu_kien_col_idx': None,
        'ma_loai_hinh_col_idx': None,
        'ngay_dk_col_idx': None,
        'don_gia_tinh_thue_col_idx': None,
        'tong_so_luong_col_idx': None,
        'ma_hs_col_idx': None,
        'so_tk_col_idx': None,
        'ten_hang_col_idx': None,
        'ten_doi_tac_col_idx': None,
        'ma_hieu_ptvc_col_idx': None,
        'source_col_idx': None,
        'item_col_idx': None,
    }
    
    for idx, col in enumerate(columns, 1):
        col_str = str(col).strip()
        col_lower = col_str.lower()
        
        if result['npl_col_idx'] is None and (
            col_str in ['Mã NPL/SP', 'Ma NPL/SP', 'Mã NPL', 'Mã SP', 'ma_npl_sp'] or
            ('npl' in col_lower and 'suggested' not in col_lower)
        ):
            result['npl_col_idx'] = idx
        elif col_str in ['Điều kiện giá hóa đơn', 'Dieu kien gia hoa don', 'ĐKGHĐ', 'dieu_kien_gia_hoa_don']:
            result['dieu_kien_col_idx'] = idx
        elif col_str in ['Mã loại hình', 'Ma loai hinh', 'Loại hình', 'ma_loai_hinh']:
            result['ma_loai_hinh_col_idx'] = idx
        elif col_str in ['Ngày ĐK', 'Ngay DK', 'Ngày đăng ký', 'ngay_dk']:
            result['ngay_dk_col_idx'] = idx
        elif col_str in ['Đơn giá tính thuế', 'Don gia tinh thue', 'don_gia_tinh_thue']:
            result['don_gia_tinh_thue_col_idx'] = idx
        elif result['tong_so_luong_col_idx'] is None and (
            col_str in ['Tổng số lượng', 'Tong so luong', 'tong_so_luong', 'Tổng SL', 'TSL'] or 
            col_lower.startswith('tổng số lượng') or col_lower.startswith('tong so luong')
        ):
            result['tong_so_luong_col_idx'] = idx
        elif result['ma_hs_col_idx'] is None and (
            col_str in ['Mã HS', 'Ma HS', 'HS Code', 'ma_hs', 'HS', 'Mã số HS'] or 
            col_lower == 'mã hs' or col_lower == 'ma hs' or col_lower == 'hs'
        ):
            result['ma_hs_col_idx'] = idx
        elif col_str in ['Số TK', 'So TK', 'SỐ TK', 'Số tờ khai', 'so_tk']:
            result['so_tk_col_idx'] = idx
        elif result['ten_hang_col_idx'] is None and (
            col_str in ['Tên hàng', 'Ten hang', 'TÊN HÀNG', 'ten_hang'] or 
            col_lower == 'tên hàng' or col_lower == 'ten hang'
        ):
            result['ten_hang_col_idx'] = idx
        elif result['ten_doi_tac_col_idx'] is None and (
            col_str in ['Tên đối tác', 'Ten doi tac', 'TÊN ĐỐI TÁC', 'ten_doi_tac'] or
            col_lower == 'tên đối tác' or col_lower == 'ten doi tac'
        ):
            result['ten_doi_tac_col_idx'] = idx
        elif result['ma_hieu_ptvc_col_idx'] is None and (
            col_str in ['Mã hiệu PTVC', 'Ma hieu PTVC', 'MÃ HIỆU PTVC', 'ma_hieu_ptvc'] or
            col_lower == 'mã hiệu ptvc' or col_lower == 'ma hieu ptvc' or
            'ptvc' in col_lower
        ):
            result['ma_hieu_ptvc_col_idx'] = idx
        # Mã NPL/SP (Suggested) / Source (from preprocess)
        elif result['source_col_idx'] is None and (
            col_str in ['Source', 'source', 'SOURCE', 'Nguồn', 'Mã NPL/SP (Suggested)', 'Mã NPL/SP\n(Suggested)'] or
            col_lower == 'source' or col_lower == 'nguồn' or
            'suggested' in col_lower or 'mã npl/sp (suggested)' in col_lower
        ):
            result['source_col_idx'] = idx
        # Rationale / Item / Final Item Code (from preprocess)
        elif result['item_col_idx'] is None and (
            col_str in ['Rationale', 'rationale', 'RATIONALE', 'Final Item Code', 'Item', 'item', 'ITEM', 'Final_Item_Code', 'final_item_code'] or
            col_lower == 'rationale' or col_lower == 'final item code' or col_lower == 'item'
        ):
            result['item_col_idx'] = idx
        
        # Track ALL preprocess/extra columns for skipping (separate from elif chain)
        if (col_lower in ['source', 'rationale', 'final_item_code'] or
            col_lower == 'final item code' or
            'suggested' in col_lower or
            'final item' in col_lower):
            result.setdefault('preprocess_skip_cols', set()).add(idx)
    
    return result

