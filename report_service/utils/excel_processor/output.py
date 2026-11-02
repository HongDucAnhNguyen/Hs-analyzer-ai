"""Excel output generation

Generates combined Excel reports with multiple sheets:
- 1.0 (EXIM Overview)
- 1.1 (HS Inconsistency)
- 1.2 (HS Inconsistency to collect)
- 2.1 (RPT check)
- 2.3 (Additions/deductions check)
- Non-Tariff Measures
- Input Data (VNACCs)
"""

import json
import logging
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.chart import PieChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import FilterColumn

from report_service.core.models import (
    ExcelRowData,
    HSConsistencyReport,
    NTMReport,
    ValueVarianceReport,
    get_flow_from_ma_loai_hinh,
)

from openpyxl.styles import Alignment, Font, PatternFill

from .constants import (
    CELL_ALIGNMENT,
    CELL_FONT,
    CENTER_ALIGNMENT,
    HEADER_ALIGNMENT,
    HEADER_FILL,
    HEADER_FONT,
    LINK_FONT,
    NO_BORDER,
    NUMBER_ALIGNMENT,
    THIN_BORDER,
)
from .tariff import load_tariff_rates, parse_tax_value
from .cas_extractor import (
    extract_cas_from_ten_hang,
    check_cas_in_appendix_iii,
    check_hs_chapter_28_29,
    batch_extract_cas_via_llm_sync,
    get_chemical_appendix_info,
)

# Table of Contents styles (matching reference file exactly)
TOC_TITLE_FONT = Font(name="Arial", bold=True, color="FFE600", size=24)
TOC_TOC_TITLE_FONT = Font(name="Arial", bold=True, color="FFE600", size=30)
TOC_LABEL_FONT = Font(name="Arial", bold=True, color="FFE600", size=10)
TOC_HEADER_FONT = Font(name="Arial", bold=True, color="FFE600", size=11)
TOC_DATA_REF_FONT = Font(name="Arial", bold=True, size=11)  # Black text for Sheet Ref
TOC_DATA_FONT = Font(name="Arial", size=11)  # Black text for Contents/PIC
TOC_DARK_FILL = PatternFill(start_color="2E2E38", end_color="2E2E38", fill_type="solid")

# New columns header style - black text on yellow background (FFE600 - same as header text yellow)
NEW_COL_HEADER_FONT = Font(name="Arial", bold=True, size=10, color="000000")
NEW_COL_HEADER_FILL = PatternFill(start_color="FFE600", end_color="FFE600", fill_type="solid")
NEW_COL_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# EXIM overview styles
EXIM_TITLE_FONT = Font(name="Arial", bold=True, size=12, color="FFFFFF")
EXIM_TITLE_FILL = PatternFill(start_color="2E2E38", end_color="2E2E38", fill_type="solid")
EXIM_SECTION_FONT = Font(name="Arial", bold=True, size=9, color="FFFFFF")
EXIM_SECTION_FILL = PatternFill(start_color="2E2E38", end_color="2E2E38", fill_type="solid")
EXIM_TABLE_HEADER_FONT = Font(name="Arial", bold=True, size=9, color="FFE600")
EXIM_TABLE_HEADER_FILL = PatternFill(start_color="2E2E38", end_color="2E2E38", fill_type="solid")
EXIM_LABEL_FONT = Font(name="Arial", bold=True, size=9)

EXIM_CHART_COLORS = [
    "750E5C",  # Maroon
    "FF4136",  # Red
    "FF6D00",  # Orange
    "2DB757",  # Green
    "27ACAA",  # Teal
    "188CE5",  # Blue
    "3D108A",  # Purple
]


def _as_srgb(color: str) -> str:
    return color[-6:]

# Header row height (same as input sheet)
HEADER_ROW_HEIGHT = 80

# Italic font for "[the Company to fill]"
ITALIC_FONT = Font(name="Arial", italic=True, size=10)
TOC_DATA_ALIGNMENT = Alignment(horizontal="general", vertical="center", wrap_text=True)

logger = logging.getLogger(__name__)


# ============================================================================
# COMMODITY POLICY LOADER
# ============================================================================

_COMMODITY_POLICY_CACHE: Dict[str, str] = {}


def load_commodity_policy() -> Dict[str, str]:
    """Load commodity policy data from JSON file
    
    Returns:
        Dictionary mapping HS codes (7 digits) to policy text
    """
    global _COMMODITY_POLICY_CACHE
    
    if _COMMODITY_POLICY_CACHE:
        return _COMMODITY_POLICY_CACHE
    
    # Try multiple paths for the JSON file
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'commodity_policy_2026.json'),
        os.path.join(os.path.dirname(__file__), '..', 'data', 'commodity_policy_2026.json'),
        'report_service/data/commodity_policy_2026.json',
    ]
    
    for path in possible_paths:
        try:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    _COMMODITY_POLICY_CACHE = json.load(f)
                logger.info(f"Loaded commodity policy from {abs_path}: {len(_COMMODITY_POLICY_CACHE)} entries")
                return _COMMODITY_POLICY_CACHE
        except Exception as e:
            logger.debug(f"Failed to load commodity policy from {path}: {e}")
    
    logger.warning("Could not load commodity_policy.json from any path")
    return {}


def get_commodity_policy(hs_code: str) -> str:
    """Get commodity policy for an HS code
    
    Tries matching with first 7 digits of the HS code.
    
    Args:
        hs_code: HS code (8 digits typically)
        
    Returns:
        Policy text or empty string if not found
    """
    if not hs_code:
        return ""
    
    policy_data = load_commodity_policy()
    
    # Clean the HS code (remove any dots/spaces)
    hs_clean = hs_code.replace('.', '').replace(' ', '').strip()
    
    # Try exact match first
    if hs_clean in policy_data:
        return policy_data[hs_clean]
    
    # Try first 7 digits
    if len(hs_clean) >= 7:
        hs_7 = hs_clean[:7]
        if hs_7 in policy_data:
            return policy_data[hs_7]
    
    # Try first 6 digits
    if len(hs_clean) >= 6:
        hs_6 = hs_clean[:6]
        # Look for any key starting with these 6 digits
        for key in policy_data:
            if key.startswith(hs_6):
                return policy_data[key]
    
    return ""


def get_max_policy_count() -> int:
    """Get the maximum number of policies for any HS code
    
    Returns:
        Maximum count of policies (split by ';')
    """
    policy_data = load_commodity_policy()
    max_count = 0
    
    for policy_text in policy_data.values():
        if policy_text:
            count = len([p.strip() for p in policy_text.split(';') if p.strip()])
            if count > max_count:
                max_count = count
    
    return max_count


# ============================================================================
# NĐ24/2026 PHỤ LỤC DATABASE LOADER
# ============================================================================

_ND24_PHU_LUC_CACHE: Dict = {}


def load_nd24_phu_luc_database() -> Dict:
    """Load NĐ24/2026 Phụ lục database from JSON file
    
    Returns:
        Dictionary containing all appendix data:
        - phu_luc_i: Basic chemicals (by CAS)
        - phu_luc_ii: Conditional business chemicals (by CAS)
        - phu_luc_iii: Special control chemicals (by CAS)
        - phu_luc_iv_a: Emergency response chemicals Table A (by CAS)
        - phu_luc_iv_b: Emergency response chemicals Table B (by hazard class)
        - phu_luc_ii_1: Banned chemicals (by HS code)
    """
    global _ND24_PHU_LUC_CACHE
    
    if _ND24_PHU_LUC_CACHE:
        return _ND24_PHU_LUC_CACHE
    
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'nd24_phu_luc_database.json'),
        os.path.join(os.path.dirname(__file__), '..', 'data', 'nd24_phu_luc_database.json'),
        'report_service/data/nd24_phu_luc_database.json',
    ]
    
    for path in possible_paths:
        try:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    _ND24_PHU_LUC_CACHE = json.load(f)
                logger.info(f"Loaded NĐ24 Phụ lục database from {abs_path}")
                return _ND24_PHU_LUC_CACHE
        except Exception as e:
            logger.debug(f"Failed to load NĐ24 Phụ lục from {path}: {e}")
    
    logger.warning("Could not load nd24_phu_luc_database.json from any path")
    return {}


def check_cas_in_nd24_appendices(cas_number: str) -> List[Dict]:
    """Check if CAS number exists in any NĐ24 appendix
    
    Args:
        cas_number: CAS number to check
        
    Returns:
        List of dictionaries with appendix info:
        [{'appendix': 'I/II/III/IV', 'name': '...', 'data': {...}}]
    """
    if not cas_number:
        return []
    
    db = load_nd24_phu_luc_database()
    results = []
    
    # Clean CAS number
    cas_clean = cas_number.strip().replace(' ', '')
    
    # Check Phụ lục I
    for item in db.get('phu_luc_i', []):
        if item.get('cas', '').strip() == cas_clean:
            results.append({
                'appendix': 'I',
                'name': 'Phụ lục I - DANH MỤC HOÁ CHẤT CƠ BẢN THUỘC LĨNH VỰC CÔNG NGHIỆP HOÁ CHẤT TRỌNG ĐIỂM',
                'data': item
            })
            break
    
    # Check Phụ lục II
    for item in db.get('phu_luc_ii', []):
        if item.get('cas', '').strip() == cas_clean:
            results.append({
                'appendix': 'II',
                'name': 'Phụ lục II - DANH MỤC HÓA CHẤT SẢN XUẤT, KINH DOANH CÓ ĐIỀU KIỆN',
                'data': item
            })
            break
    
    # Check Phụ lục III
    for item in db.get('phu_luc_iii', []):
        if item.get('cas', '').strip() == cas_clean:
            results.append({
                'appendix': 'III',
                'name': 'Phụ lục III - DANH MỤC HÓA CHẤT CẦN KIỂM SOÁT ĐẶC BIỆT',
                'data': item
            })
            break
    
    # Check Phụ lục IV Bảng A
    for item in db.get('phu_luc_iv_a', []):
        if item.get('cas', '').strip() == cas_clean:
            results.append({
                'appendix': 'IV',
                'name': 'Phụ lục IV - DANH MỤC HOÁ CHẤT PHẢI XÂY DỰNG KẾ HOẠCH PHÒNG NGỪA, ỨNG PHÓ SỰ CỐ HOÁ CHẤT',
                'data': item,
                'nguong_khoi_luong': item.get('nguong_khoi_luong', '')
            })
            break
    
    return results


def check_hs_in_nd24_banned(hs_code: str) -> Optional[Dict]:
    """Check if HS code matches banned chemicals in Phụ lục II.1
    
    Matches by 8-6-4 digit HS code prefixes
    
    Args:
        hs_code: HS code to check (typically 8 digits)
        
    Returns:
        Dictionary with banned chemical info if found, None otherwise
    """
    if not hs_code:
        return None
    
    db = load_nd24_phu_luc_database()
    
    # Clean HS code
    hs_clean = hs_code.replace('.', '').replace(' ', '').strip()
    
    # Check Phụ lục II.1 (banned chemicals by HS code)
    for item in db.get('phu_luc_ii_1', []):
        item_hs = item.get('hs_code', '').replace('.', '').replace(' ', '').strip()
        if not item_hs:
            continue
        
        # Match by 8-6-4 digit prefixes
        if hs_clean == item_hs:
            return item
        if len(hs_clean) >= 8 and item_hs == hs_clean[:8]:
            return item
        if len(hs_clean) >= 6 and item_hs == hs_clean[:6]:
            return item
        if len(hs_clean) >= 4 and item_hs == hs_clean[:4]:
            return item
        # Also check if item_hs is a prefix of hs_clean
        if hs_clean.startswith(item_hs):
            return item
    
    return None


# Sheet type constants (matching ReportSheet enum values)
SHEET_EXIM = "exim_overview"
SHEET_INPUT_DATA = "input_data"
SHEET_HS_INCONSISTENCY = "hs_inconsistency"
SHEET_HS_TO_COLLECT = "hs_to_collect"
SHEET_VALUE_VARIANCE = "value_variance"
SHEET_NON_TARIFF_MEASURES = "ntm"

# All available sheets
ALL_SHEETS = [
    SHEET_EXIM,
    SHEET_INPUT_DATA,
    SHEET_HS_INCONSISTENCY,
    SHEET_HS_TO_COLLECT,
    SHEET_VALUE_VARIANCE,
    SHEET_NON_TARIFF_MEASURES,
]


def apply_sheet_settings(ws):
    """Apply common settings to worksheets"""
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 80
    ws.column_dimensions['A'].width = 2
    # Set tab color to dark theme for all sheets
    ws.sheet_properties.tabColor = "2E2E38"


def _create_table_of_contents_sheet(wb: Workbook, *, include_exim: bool = True) -> None:
    """Create Table of Contents sheet at the beginning (matching reference file exactly)."""
    from openpyxl.styles import Border, Side
    
    ws = wb.create_sheet("Table of Contents", 0)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 80
    
    # Set sheet tab color to yellow
    ws.sheet_properties.tabColor = "FFE600"
    
    # Set column widths (matching reference file)
    ws.column_dimensions['A'].width = 2.71
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 63.85
    ws.column_dimensions['D'].width = 30.71
    
    # Header section with dark background (rows 1-4 and 6, columns B-D only - NOT column A, row 5 empty)
    for row in [1, 2, 3, 4, 6]:  # Skip row 5
        for col in range(2, 5):  # Start from column B (2), skip column A
            cell = ws.cell(row=row, column=col)
            cell.fill = TOC_DARK_FILL
    
    # Row 1: CLIENT NAME
    cell = ws.cell(row=1, column=2, value="CLIENT NAME")
    cell.font = TOC_TITLE_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="general", vertical="center")
    ws.row_dimensions[1].height = 29.15
    
    # Row 2: Service
    cell = ws.cell(row=2, column=2, value="Service:")
    cell.font = TOC_LABEL_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    cell = ws.cell(row=2, column=3, value="[To fill]")
    cell.font = TOC_LABEL_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 13.8
    
    # Row 3: Period Under Review
    cell = ws.cell(row=3, column=2, value="Period Under Review:")
    cell.font = TOC_LABEL_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    cell = ws.cell(row=3, column=3, value="[To fill]")
    cell.font = TOC_LABEL_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[3].height = 13.8
    
    # Row 4: Table of Contents title
    cell = ws.cell(row=4, column=2, value="Table of Contents")
    cell.font = TOC_TOC_TITLE_FONT
    cell.fill = TOC_DARK_FILL
    cell.alignment = Alignment(horizontal="general", vertical="center")
    ws.row_dimensions[4].height = 36.25
    
    # Row 5: Empty row (no fill)
    ws.row_dimensions[5].height = 12
    
    # Row 6: Table headers (dark background with yellow text)
    headers = [("", None), ("Sheet Ref", "center"), ("Contents", "center"), ("PIC", "center")]
    for col_idx, (header, h_align) in enumerate(headers, 1):
        if col_idx > 1:  # Skip column A
            cell = ws.cell(row=6, column=col_idx, value=header)
            cell.font = TOC_HEADER_FONT
            cell.fill = TOC_DARK_FILL
            cell.alignment = Alignment(horizontal=h_align or "general", vertical="center")
    ws.row_dimensions[6].height = 14.15
    
    # Bottom border for data rows
    bottom_border = Border(bottom=Side(style='thin', color='000000'))
    
    # Table of Contents data rows
    toc_items = []
    if include_exim:
        toc_items.append((1.0, "EXIM Statistics", "[To fill]"))
    toc_items.extend(
        [
            (1.1, "Tariff Classification - Consistency test", "[To fill]"),
            (1.2, "Tarriff Classification - Accuracy test", "[To fill]"),
            (2.1, "Customs Valuation - Related Party Transactions (RPT) check", "[To fill]"),
            (2.2, "Customs Valuation - Variance check", "[To fill]"),
            ("2.2a", "Customs Valuation - RPT Questionnaire", "[To fill]"),
            (2.3, "Customs Valuation - Additions/deductions/mark-up check", "[To fill]"),
            (3.1, "Non-Tariff Measures check", "[To fill]"),
        ]
    )
    
    for row_idx, (sheet_ref, contents, pic) in enumerate(toc_items, 7):
        # Sheet Ref (numeric, bold, centered)
        cell = ws.cell(row=row_idx, column=2, value=sheet_ref)
        cell.font = TOC_DATA_REF_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = bottom_border
        
        # Contents (regular font, general alignment)
        cell = ws.cell(row=row_idx, column=3, value=contents)
        cell.font = TOC_DATA_FONT
        cell.alignment = Alignment(horizontal="general", vertical="center")
        cell.border = bottom_border
        
        # PIC (regular font, general alignment)
        cell = ws.cell(row=row_idx, column=4, value=pic)
        cell.font = TOC_DATA_FONT
        cell.alignment = Alignment(horizontal="general", vertical="center")
        cell.border = bottom_border
        
        ws.row_dimensions[row_idx].height = 42
    
    # Freeze panes: 6 rows (header section) and 3 columns (A, B, C)
    # D7 means rows 1-6 and columns A-C are frozen
    ws.freeze_panes = "D7"


# This function is not currently used

# def _normalize_sheets(sheets) -> List[str]:
#     """Normalize sheets parameter to list of string values
    
#     Args:
#         sheets: Can be None, list of ReportSheet enum, or list of strings
        
#     Returns:
#         List of sheet name strings
#     """
#     if sheets is None:
#         return ALL_SHEETS
    
#     result = []
#     for s in sheets:
#         # Handle both enum and string values
#         if hasattr(s, 'value'):
#             result.append(s.value)
#         else:
#             result.append(str(s))
#     return result


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except Exception:
        return 0.0


def _get_row_value(row: ExcelRowData) -> float:
    """Get best-effort value for summary tables."""
    if row.tong_tri_gia is not None:
        return _safe_float(row.tong_tri_gia)
    if row.tri_gia_nt is not None:
        return _safe_float(row.tri_gia_nt)
    return 0.0


def _aggregate_by_flow(
    rows: List[ExcelRowData],
    key_getter,
) -> Dict[str, Dict[str, float]]:
    totals: Dict[str, Dict[str, float]] = {"Nhập": {}, "Xuất": {}}
    skipped_flow = 0
    skipped_value = 0
    missing_key = 0

    for row in rows or []:
        flow = row.flow or get_flow_from_ma_loai_hinh(row.ma_loai_hinh).value
        if flow not in ("Nhập", "Xuất"):
            skipped_flow += 1
            continue

        value = _get_row_value(row)
        if value <= 0:
            skipped_value += 1
            continue

        key = key_getter(row) or "UNKNOWN"
        if key == "UNKNOWN":
            missing_key += 1
        totals[flow][key] = totals[flow].get(key, 0.0) + value

    if rows:
        logger.info(
            "EXIM aggregate: rows=%d skipped_flow=%d skipped_value=%d missing_key=%d",
            len(rows),
            skipped_flow,
            skipped_value,
            missing_key,
        )

    return totals


def _prepare_summary_rows(
    values_by_key: Dict[str, float],
    top_n: int = 10
) -> List[Tuple[str, float, float]]:
    items = sorted(values_by_key.items(), key=lambda x: x[1], reverse=True)
    total_value = sum(value for _, value in items)

    top_items = items[:top_n]
    top_total = sum(value for _, value in top_items)
    others_value = max(total_value - top_total, 0.0)

    rows = []
    for name, value in top_items:
        percent = (value / total_value) if total_value > 0 else 0.0
        rows.append((name, value, percent))

    if others_value > 0:
        percent = (others_value / total_value) if total_value > 0 else 0.0
        rows.append(("OTHERS", others_value, percent))

    rows.append(("Tổng", total_value, 1.0 if total_value > 0 else 0.0))
    return rows

# This function is not currently used

# def _prepare_chart_rows(values_by_key: Dict[str, float], max_rows: int) -> List[Tuple[str, float]]:
#     """Prepare chart rows with optional OTHERS to fit a fixed range."""
#     if max_rows <= 0:
#         return []

#     items = sorted(values_by_key.items(), key=lambda x: x[1], reverse=True)
#     if len(items) <= max_rows:
#         return [(name, value) for name, value in items[:max_rows]]

#     top_items = items[: max_rows - 1]
#     others_value = sum(value for _, value in items[max_rows - 1 :])
#     rows = [(name, value) for name, value in top_items]
#     rows.append(("OTHERS", others_value))
#     return rows


def _write_exim_summary_table(
    ws,
    start_row: int,
    start_col: int,
    header_label: str,
    rows: List[Tuple[str, float, float]],
) -> Tuple[int, int]:
    name_col = start_col
    value_col = start_col + 1
    pct_col = start_col + 2

    headers = [header_label, "Giá trị", "%"]
    for offset, header in enumerate(headers):
        cell = ws.cell(row=start_row, column=start_col + offset, value=header)
        cell.font = EXIM_TABLE_HEADER_FONT
        cell.fill = EXIM_TABLE_HEADER_FILL
        cell.alignment = CENTER_ALIGNMENT
        cell.border = THIN_BORDER

    data_start = start_row + 1
    for idx, (name, value, pct) in enumerate(rows, data_start):
        name_cell = ws.cell(row=idx, column=name_col, value=name)
        val_cell = ws.cell(row=idx, column=value_col, value=value)
        pct_cell = ws.cell(row=idx, column=pct_col, value=pct)

        if name == "Tổng":
            name_cell.font = Font(name="Arial", bold=True, size=10)
            val_cell.font = Font(name="Arial", bold=True, size=10)
            pct_cell.font = Font(name="Arial", bold=True, size=10)
        else:
            name_cell.font = CELL_FONT
            val_cell.font = CELL_FONT
            pct_cell.font = CELL_FONT

        for cell in (name_cell, val_cell, pct_cell):
            cell.border = THIN_BORDER

        name_cell.alignment = CELL_ALIGNMENT
        val_cell.alignment = NUMBER_ALIGNMENT
        pct_cell.alignment = CENTER_ALIGNMENT
        val_cell.number_format = "#,##0"
        pct_cell.number_format = "0.00%"

    data_end = data_start + len(rows) - 1
    return data_start, data_end


def _add_exim_pie_chart(
    ws,
    *,
    title: str,
    name_col: int,
    value_col: int,
    start_row: int,
    end_row: int,
    anchor: str,
) -> None:
    if end_row < start_row:
        return

    # Exclude total row if present at the end.
    last_label = ws.cell(row=end_row, column=name_col).value
    if str(last_label).strip() == "Tổng" and end_row > start_row:
        end_row -= 1

    if end_row < start_row:
        return

    chart = PieChart()
    chart.title = title
    chart.varyColors = True

    data = Reference(ws, min_col=value_col, min_row=start_row, max_row=end_row)
    labels = Reference(ws, min_col=name_col, min_row=start_row, max_row=end_row)
    chart.add_data(data, titles_from_data=False)
    chart.set_categories(labels)
    chart.height = 7
    chart.width = 11

    point_count = end_row - start_row + 1
    if chart.series:
        series = chart.series[0]
        data_points = []
        for idx in range(point_count):
            color = _as_srgb(EXIM_CHART_COLORS[idx % len(EXIM_CHART_COLORS)])
            dp = DataPoint(idx=idx)
            dp.graphicalProperties = GraphicalProperties(solidFill=color)
            data_points.append(dp)

        series.dPt = data_points
        logger.info(
            "EXIM chart colors applied: title=%s points=%d colors=%s",
            title,
            point_count,
            EXIM_CHART_COLORS,
        )
    else:
        logger.info(
            "EXIM chart colors skipped (no series): title=%s points=%d",
            title,
            point_count,
        )

    ws.add_chart(chart, anchor)


def _create_exim_sheet(
    wb: Workbook,
    rows: Optional[List[ExcelRowData]] = None,
) -> None:
    ws = wb.create_sheet("1.0")
    apply_sheet_settings(ws)

    for col, width in zip(
        ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"],
        [2, 42, 18, 10, 2, 42, 18, 10, 2, 16, 16, 16, 16]
    ):
        ws.column_dimensions[col].width = width

    current_row = 2
    chart_height = 12

    # Statistics broken down by CD Type
    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=8)
    section_cell = ws.cell(row=current_row, column=2, value="Statistics broken down by CD Type")
    section_cell.font = EXIM_TABLE_HEADER_FONT
    section_cell.fill = EXIM_TABLE_HEADER_FILL
    section_cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.cell(row=current_row + 1, column=2, value="IMPORTS").font = EXIM_LABEL_FONT
    ws.cell(row=current_row + 1, column=6, value="EXPORTS").font = EXIM_LABEL_FONT

    type_totals = _aggregate_by_flow(
        rows or [],
        lambda r: r.ma_loai_hinh or "UNKNOWN",
    )
    import_type_rows = _prepare_summary_rows(type_totals.get("Nhập", {}))
    export_type_rows = _prepare_summary_rows(type_totals.get("Xuất", {}))

    header_row = current_row + 2
    left_data_start, left_data_end = _write_exim_summary_table(
        ws,
        header_row,
        2,
        "Mã loại hình",
        import_type_rows,
    )
    right_data_start, right_data_end = _write_exim_summary_table(
        ws,
        header_row,
        6,
        "Mã loại hình",
        export_type_rows,
    )

    chart_row = max(left_data_end, right_data_end) + 2
    _add_exim_pie_chart(
        ws,
        title="Nhập - Theo mã loại hình",
        name_col=2,
        value_col=3,
        start_row=left_data_start,
        end_row=left_data_end,
        anchor=f"B{chart_row}",
    )
    _add_exim_pie_chart(
        ws,
        title="Xuất - Theo mã loại hình",
        name_col=6,
        value_col=7,
        start_row=right_data_start,
        end_row=right_data_end,
        anchor=f"F{chart_row}",
    )

    current_row = chart_row + chart_height + 4

    # Statistics broken down by vendors / customers
    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=8)
    section_cell = ws.cell(row=current_row, column=2, value="Statistics broken down by vendors / customers")
    section_cell.font = EXIM_TABLE_HEADER_FONT
    section_cell.fill = EXIM_TABLE_HEADER_FILL
    section_cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.cell(row=current_row + 1, column=2, value="IMPORTS").font = EXIM_LABEL_FONT
    ws.cell(row=current_row + 1, column=6, value="EXPORTS").font = EXIM_LABEL_FONT

    vendor_totals = _aggregate_by_flow(
        rows or [],
        lambda r: r.ten_doi_tac or "UNKNOWN",
    )
    import_vendor_rows = _prepare_summary_rows(vendor_totals.get("Nhập", {}))
    export_vendor_rows = _prepare_summary_rows(vendor_totals.get("Xuất", {}))

    header_row = current_row + 2
    left_data_start, left_data_end = _write_exim_summary_table(
        ws,
        header_row,
        2,
        "Nhà cung cấp",
        import_vendor_rows,
    )
    right_data_start, right_data_end = _write_exim_summary_table(
        ws,
        header_row,
        6,
        "Khách hàng",
        export_vendor_rows,
    )

    chart_row = max(left_data_end, right_data_end) + 2
    _add_exim_pie_chart(
        ws,
        title="Nhập - Theo vendor",
        name_col=2,
        value_col=3,
        start_row=left_data_start,
        end_row=left_data_end,
        anchor=f"B{chart_row}",
    )
    _add_exim_pie_chart(
        ws,
        title="Xuất - Theo vendor",
        name_col=6,
        value_col=7,
        start_row=right_data_start,
        end_row=right_data_end,
        anchor=f"F{chart_row}",
    )

    current_row = chart_row + chart_height + 4

    # Statistics broken down by origin
    ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=8)
    section_cell = ws.cell(row=current_row, column=2, value="Statistics broken down by origin")
    section_cell.font = EXIM_TABLE_HEADER_FONT
    section_cell.fill = EXIM_TABLE_HEADER_FILL
    section_cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.cell(row=current_row + 1, column=2, value="IMPORTS").font = EXIM_LABEL_FONT
    ws.cell(row=current_row + 1, column=6, value="EXPORTS").font = EXIM_LABEL_FONT

    origin_totals = _aggregate_by_flow(
        rows or [],
        lambda r: r.xuat_xu or "UNKNOWN",
    )
    import_origin_rows = _prepare_summary_rows(origin_totals.get("Nhập", {}))
    export_origin_rows = _prepare_summary_rows(origin_totals.get("Xuất", {}))

    header_row = current_row + 2
    left_data_start, left_data_end = _write_exim_summary_table(
        ws,
        header_row,
        2,
        "Xuất xứ",
        import_origin_rows,
    )
    right_data_start, right_data_end = _write_exim_summary_table(
        ws,
        header_row,
        6,
        "Xuất xứ",
        export_origin_rows,
    )

    chart_row = max(left_data_end, right_data_end) + 2
    _add_exim_pie_chart(
        ws,
        title="Nhập - Theo xuất xứ",
        name_col=2,
        value_col=3,
        start_row=left_data_start,
        end_row=left_data_end,
        anchor=f"B{chart_row}",
    )
    _add_exim_pie_chart(
        ws,
        title="Xuất - Theo xuất xứ",
        name_col=6,
        value_col=7,
        start_row=right_data_start,
        end_row=right_data_end,
        anchor=f"F{chart_row}",
    )


def generate_combined_excel(
    hs_consistency: HSConsistencyReport,
    value_variance: ValueVarianceReport = None,
    ntm_report: NTMReport = None,
    original_rows: List[ExcelRowData] = None,
    original_df: pd.DataFrame = None,
    original_file_content: bytes = None,
    original_sheet_name: str = None,
    sheets: Optional[List] = None,
    enabled_sections: Optional[set] = None,
) -> BytesIO:
    """Generate combined Excel with selected report sheets
    
    Args:
        hs_consistency: HS Consistency report data (generated only if section 1 is enabled)
        value_variance: Optional Value Variance report data (generated only if section 2 is enabled)
        ntm_report: Optional NTM report data (generated only if section 3 is enabled)
        original_rows: Optional original row data
        original_df: Optional original DataFrame
        original_file_content: Optional original file bytes
        original_sheet_name: Optional original sheet name
        sheets: Deprecated - use enabled_sections instead
        enabled_sections: Optional set of enabled section numbers ("1", "2", "3").
                         Controls which sheets are created and columns are filled.
                         - "1" enables Tariff Classification (sheets 1.1/1.2)
                         - "2" enables Customs Valuation (sheets 2.1, 2.3)
                         - "3" enables Non-Tariff Measures (NTM sheet)
                         Default: all sections enabled
    Returns:
        BytesIO containing the Excel file
    """
    # Default to all sections if not specified
    if enabled_sections is None:
        enabled_sections = {"1", "2", "3", "exim"}
    
    logger.info(f"Generating Excel for enabled sections: {enabled_sections}")
    
    wb = Workbook()
    default_sheet = wb.active
    
    include_exim = "exim" in enabled_sections 

    # Create Table of Contents sheet first
    _create_table_of_contents_sheet(wb, include_exim=include_exim)
    
    input_sheet_title = "VNACCs (2.1 - 2.2)"  # Fixed sheet name for input data
    
    # Create EXIM overview sheet (only if enabled and data is available)
    if original_rows and include_exim:
        _create_exim_sheet(wb, original_rows)

    # Get NPL to IP mapping for HS Inconsistency (only if section 1 is enabled)
    npl_to_ip_hs = {}
    if "1" in enabled_sections and hs_consistency and hs_consistency.items:
        for item in hs_consistency.items:
            if item.impact_refer and item.ma_npl_sp:
                npl_to_ip_hs[item.ma_npl_sp] = item.impact_refer
    
    # Get (flow + dieu_kien + npl_sp + ten_doi_tac) to IP mapping for Value Variance (only if section 2 is enabled)
    flow_dieu_kien_npl_to_ip_vv = {}
    if "2" in enabled_sections and value_variance and value_variance.items:
        for item in value_variance.items:
            if item.impact_refer:
                flow = item.flow or ""
                dieu_kien = item.dieu_kien_gia_hoa_don or ""
                npl_sp = item.ma_npl_sp or ""
                ten_doi_tac = item.ten_doi_tac or ""
                key = f"{flow}|{dieu_kien}|{npl_sp}|{ten_doi_tac}"
                flow_dieu_kien_npl_to_ip_vv[key] = item.impact_refer
    
    # Create HS Inconsistency sheet (Section 1 - Tariff Classification)
    # ALWAYS create sheets 1.1 and 1.2 when section "1" is enabled (even if no data)
    if "1" in enabled_sections:
        _create_hs_inconsistency_sheet(wb, hs_consistency)
    
    # Create sheets 2.1, 2.2a, and 2.3 (Section 2 - Customs Valuation)
    npl_to_23_flag = {}  # Mapping for section 2.3 flag in input sheet
    if "2" in enabled_sections and value_variance and value_variance.items:
        _create_sheet_21(wb, value_variance)
        _create_sheet_22a(wb)  # RPT Questionnaire
        npl_to_23_flag = _create_sheet_23(wb, value_variance)
    
    # Create NTM sheet (Section 3 - Non-Tariff Measures) - merged 3.1 and 3.2
    flag_31_mapping = {}  # Mapping for section 3.1 flag in input sheet
    exclusion_31_mapping = {}  # Mapping for section 3.1 exclusion reasons
    flag_32_mapping = {}  # Deprecated - merged into 3.1
    num_flags_c = 1  # Default: 1 Flag-C column (or 0 if no chemical items)
    if "3" in enabled_sections and ntm_report and ntm_report.items:
        flag_31_mapping, exclusion_31_mapping, num_flags_c = _create_sheet_31(wb, ntm_report, original_rows)  # Sheet 3.1 (merged NTM)
    
    # Build prefill mapping from original_rows (source/item from prefill_item_codes)
    # Key: (so_tk, ten_hang) → Value: (suggested_code, rationale)
    # Also builds a ten_hang-only fallback map for robustness
    # (calamine/pandas and openpyxl may produce different so_tk formats)
    prefill_map = {}
    if original_rows:
        for row in original_rows:
            if row.source or row.item:
                so_tk_str = str(row.so_tk or '').strip()
                ten_hang_str = str(row.ten_hang or '').strip()
                val = (row.source or '', row.item or '')
                # Primary key: (so_tk, ten_hang)
                prefill_map[(so_tk_str, ten_hang_str)] = val
                # Fallback key: ten_hang only (prefixed to avoid collision)
                if ten_hang_str:
                    prefill_map[('__TH__', ten_hang_str)] = val
        logger.info(f"Built prefill_map with {len(prefill_map)} entries")
    
    # Create Input Data sheet (always created)
    input_sheet_created = False
    logger.info(f"Input sheet creation: original_file_content={'YES' if original_file_content else 'NO'} ({len(original_file_content) if original_file_content else 0} bytes), original_df={'YES' if original_df is not None else 'NO'}")
    if original_file_content is not None:
        logger.info("Attempting xlsx/xlsb path for input sheet...")
        input_sheet_created = _create_input_sheet_optimized(
            wb, original_file_content, input_sheet_title, npl_to_ip_hs, flow_dieu_kien_npl_to_ip_vv, npl_to_23_flag,
            enabled_sections, flag_31_mapping, flag_32_mapping, exclusion_31_mapping,
            prefill_map=prefill_map, num_flags_c=num_flags_c
        )
        logger.info(f"xlsx/xlsb path result: {'SUCCESS' if input_sheet_created else 'FAILED'}")
    
    if not input_sheet_created and original_df is not None and not original_df.empty:
        logger.info(f"Using DataFrame path for input sheet (columns: {list(original_df.columns)[:5]}...)")
        input_sheet_created = _create_input_from_dataframe(
            wb, original_df, input_sheet_title, npl_to_ip_hs, flow_dieu_kien_npl_to_ip_vv, npl_to_23_flag,
            enabled_sections, flag_31_mapping, flag_32_mapping, exclusion_31_mapping,
            prefill_map=prefill_map, num_flags_c=num_flags_c
        )
    
    if not input_sheet_created:
        ws_input = wb.create_sheet(input_sheet_title, 0)
        ws_input.sheet_view.showGridLines = False
        ws_input.sheet_view.zoomScale = 80
        ws_input.sheet_properties.tabColor = "2E2E38"
        ws_input.cell(row=1, column=1, value="Input data could not be loaded")
        input_sheet_created = True
    
    # Create HS Inconsistency (to collect) sheet (Section 1 - part 1.2)
    # ALWAYS create sheet 1.2 when section "1" is enabled (even if no data)
    if "1" in enabled_sections:
        _create_hs_to_collect_sheet(wb, hs_consistency)
    
    # Create CHC reference sheet (NĐ24.2026) at the end
    _create_chc_reference_sheet(wb)
    
    # Remove default sheet
    if default_sheet.title == "Sheet" and default_sheet.title in wb.sheetnames:
        try:
            wb.remove(default_sheet)
        except Exception:
            pass
    
    # Reorder sheets
    _reorder_sheets(wb, input_sheet_title)
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output


def _create_hs_inconsistency_sheet(wb: Workbook, hs_consistency: HSConsistencyReport) -> None:
    """Create 1.1 sheet (formerly HS Inconsistency)
    
    ALWAYS creates the sheet, even if there's no data (just headers).
    """
    # Column order with 2 empty separator columns:
    # "", STT, Flow, Mã NPL/SP, Mã loại hình, Mã HS, Import duty rate, Tên hàng, Total value, "", Impact amount, Samples to pick, Flag
    headers_hs = [
        "", "STT", "Flow", "Mã NPL/SP", "Mã loại hình", "Mã HS", 
        "Import duty\nrate", "Tên hàng", "Total value",
        "", "Impact\namount", "Samples to\npick", "Flag"
    ]
    column_widths_hs = [2, 8, 10, 25, 15, 15, 15, 50, 18, 2, 12, 12, 12]
    
    # Columns with yellow header (black text on yellow background)
    yellow_header_cols = [11, 12, 13]  # Impact amount, Samples to pick, Flag
    # Empty separator columns
    empty_cols = [1, 10]
    
    ws1 = wb.create_sheet("1.1")
    apply_sheet_settings(ws1)
    
    # Row 1: Headers
    for col_idx, header in enumerate(headers_hs, 1):
        cell = ws1.cell(row=1, column=col_idx, value=header)
        if col_idx in empty_cols:
            cell.border = NO_BORDER
        elif col_idx in yellow_header_cols:
            cell.font = NEW_COL_HEADER_FONT
            cell.fill = NEW_COL_HEADER_FILL
            cell.alignment = NEW_COL_HEADER_ALIGNMENT
            cell.border = THIN_BORDER
        else:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Row 2: Filter row (empty) - filter applied here
    for col_idx in range(1, len(headers_hs) + 1):
        cell = ws1.cell(row=2, column=col_idx, value="")
        if col_idx not in empty_cols:
            cell.border = THIN_BORDER
    
    # If no data, create sheet with headers only and return
    if not hs_consistency or not hs_consistency.items:
        # Set column widths
        for col_idx, width in enumerate(column_widths_hs, 1):
            ws1.column_dimensions[get_column_letter(col_idx)].width = width
        # Set header row height
        ws1.row_dimensions[1].height = HEADER_ROW_HEIGHT
        # Add auto filter on row 2 (header only)
        ws1.auto_filter.ref = f"B2:M2"
        # Freeze at J3
        ws1.freeze_panes = "J3"
        logger.info("Created 1.1 sheet with headers only (no data)")
        return
    
    # Aggregate items by (ten_hang, ma_hs, ma_npl_sp) - sum total and impact_amount
    aggregated_data = {}
    for item in hs_consistency.items:
        # Create key from ten_hang, ma_hs, ma_npl_sp
        key = (
            item.ten_hang or "",
            item.ma_hs or "",
            item.ma_npl_sp or ""
        )
        
        if key not in aggregated_data:
            aggregated_data[key] = {
                'flow': item.flow or "",
                'ma_npl_sp': item.ma_npl_sp or "",
                'ma_loai_hinh': item.ma_loai_hinh or "",
                'ma_hs': item.ma_hs or "",
                'tax': item.tax,
                'ten_hang': item.ten_hang or "",
                'total': item.total or 0,
                'impact_amount': item.impact_amount or 0,
                'to_pic': item.to_pic or "",
                'impact_refer': item.impact_refer or "",
            }
        else:
            # Sum total and impact_amount
            aggregated_data[key]['total'] = (aggregated_data[key]['total'] or 0) + (item.total or 0)
            aggregated_data[key]['impact_amount'] = (aggregated_data[key]['impact_amount'] or 0) + (item.impact_amount or 0)
            # Keep the first non-empty values for other fields
            if not aggregated_data[key]['to_pic'] and item.to_pic:
                aggregated_data[key]['to_pic'] = item.to_pic
            if not aggregated_data[key]['impact_refer'] and item.impact_refer:
                aggregated_data[key]['impact_refer'] = item.impact_refer
    
    # Convert to list
    aggregated_items = list(aggregated_data.values())
    
    # Build STT mapping
    npl_sp_to_stt = {}
    stt_counter = 0
    for item in aggregated_items:
        npl_sp_key = item['ma_npl_sp'] if item['ma_npl_sp'] else "__NULL__"
        if npl_sp_key not in npl_sp_to_stt:
            stt_counter += 1
            npl_sp_to_stt[npl_sp_key] = stt_counter
    
    # Write data rows starting at row 3
    for row_idx, item in enumerate(aggregated_items, 3):
        npl_sp = item['ma_npl_sp']
        npl_sp_key = npl_sp if npl_sp else "__NULL__"
        stt = npl_sp_to_stt.get(npl_sp_key, "")
        
        # Column order with empty separators
        row_data = [
            "",                                      # 1: Empty separator
            stt,                                     # 2: STT
            item['flow'],                            # 3: Flow
            npl_sp,                                  # 4: Mã NPL/SP
            item['ma_loai_hinh'],                    # 5: Mã loại hình
            item['ma_hs'],                           # 6: Mã HS
            item['tax'] if item['tax'] else "N/A",  # 7: Import duty rate
            item['ten_hang'],                        # 8: Tên hàng
            item['total'],                           # 9: Total value
            "",                                      # 10: Empty separator
            item['impact_amount'],                   # 11: Impact amount
            item['to_pic'],                          # 12: Samples to pick
            item['impact_refer']                     # 13: Flag (was Ref - IP1-10 values)
        ]
        
        for col_idx, value in enumerate(row_data, 1):
            cell = ws1.cell(row=row_idx, column=col_idx, value=value)
            cell.font = CELL_FONT
            
            if col_idx in empty_cols:
                cell.border = NO_BORDER
            else:
                cell.border = THIN_BORDER
            
            if col_idx == 9:  # Total value
                cell.alignment = NUMBER_ALIGNMENT
                cell.number_format = '#,##0'
            elif col_idx == 11:  # Impact amount
                cell.alignment = NUMBER_ALIGNMENT
                cell.number_format = '#,##0.00'
            elif col_idx == 2:  # STT
                cell.alignment = CENTER_ALIGNMENT
            elif col_idx in empty_cols:
                pass  # No alignment for empty cols
            else:
                cell.alignment = CELL_ALIGNMENT
    
    # Set column widths
    for col_idx, width in enumerate(column_widths_hs, 1):
        ws1.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Add auto filter on row 2 (filter row) - all columns with headers
    last_row = 2 + len(aggregated_items)
    ws1.auto_filter.ref = f"B2:M{last_row}"  # Columns B-M (skip empty col A)
    
    # Hide filter dropdown on empty separator column J (colId=8, 0-based from B)
    ws1.auto_filter.filterColumn.append(FilterColumn(colId=8, hiddenButton=True))
    
    # Freeze at J3 (columns A-I and rows 1-2 frozen, including filter row)
    ws1.freeze_panes = "J3"


def _create_sheet_21(wb: Workbook, value_variance: ValueVarianceReport) -> None:
    """Create sheet 2.1 - RPT check"""
    from openpyxl.cell.rich_text import TextBlock, CellRichText
    from openpyxl.cell.text import InlineFont
    
    ws = wb.create_sheet("2.1")
    apply_sheet_settings(ws)
    
    # Special fonts for this sheet
    ITALIC_FONT = Font(name="Arial", size=10, italic=True)
    FORMULA_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")  # Bold red
    
    # Inline fonts for rich text
    normal_inline = InlineFont(b=True, sz=10, color="000000")
    underline_inline = InlineFont(b=True, sz=10, color="000000", u="single")
    
    # Rich text headers with underlined MIN/MAX only
    header_variance_min = CellRichText(
        TextBlock(normal_inline, "Variance test\nfor "),
        TextBlock(underline_inline, "MIN"),
        TextBlock(normal_inline, " Unit\nPrice")
    )
    header_variance_max = CellRichText(
        TextBlock(normal_inline, "Variance test\nfor "),
        TextBlock(underline_inline, "MAX"),
        TextBlock(normal_inline, "\nPrice")
    )
    
    # Headers for 2.1
    # Dark headers (yellow on black)
    headers_dark = [
        "", "STT", "Mã NPL/SP", "Tên đối tác", "Flow", "Điều kiện giá\nhóa đơn",
        "Sum of Tổng\nsố lượng", "Min of Đơn giá tính\nthuế", "Max of Đơn giá tính\nthuế2"
    ]
    # Yellow headers (black on yellow)
    # Column 15 = "&" (concatenation for VLOOKUP)
    headers_yellow = [
        "", "Count", "RPT", None, None,  # None for rich text columns
        "&", "Flag for\nCustoms", "Flag for TP"
    ]
    
    all_headers = headers_dark + headers_yellow
    empty_cols = [1, 10]  # Empty separator columns
    yellow_header_cols = list(range(11, 18))  # Count, RPT, Variance MIN, Variance MAX, "&", Flag Customs, Flag TP
    
    column_widths = [2, 8, 20, 40, 10, 18, 18, 22, 22, 2, 12, 12, 12, 12, 25, 12, 12]
    
    # Layout: Row 1 = Instruction, Row 2 = Headers, Row 3 = Formulas, Row 4+ = Data
    INSTRUCTION_ROW = 1  # Instruction row
    HEADER_ROW_IDX = 2   # Column headers
    FILTER_ROW = 3       # Formula templates
    DATA_START_ROW = 4   # First data row
    
    # Row 1: Instruction text in column L (col 12) - white text on red background
    INSTRUCTION_FILL = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    INSTRUCTION_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    instruction_cell = ws.cell(row=INSTRUCTION_ROW, column=12, 
                               value='Please fill "Related" or "Not related", based on client\'s Local File (TP Doc)')
    instruction_cell.fill = INSTRUCTION_FILL
    instruction_cell.font = INSTRUCTION_FONT
    instruction_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    instruction_cell.border = THIN_BORDER
    ws.row_dimensions[INSTRUCTION_ROW].height = 120  # Taller row for wrapped text
    
    # Row 2: Headers
    for col_idx, header in enumerate(all_headers, 1):
        cell = ws.cell(row=HEADER_ROW_IDX, column=col_idx)
        
        # Handle rich text headers for MIN/MAX columns (cols 13, 14)
        if col_idx == 13:
            cell.value = header_variance_min
        elif col_idx == 14:
            cell.value = header_variance_max
        else:
            cell.value = header
        
        if col_idx in empty_cols:
            cell.border = NO_BORDER
        elif col_idx in yellow_header_cols:
            cell.font = NEW_COL_HEADER_FONT
            cell.fill = NEW_COL_HEADER_FILL
            # Wrap text for all yellow header columns including rich text
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = THIN_BORDER
        else:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Row 3: Formula row with formulas as text
    dr = DATA_START_ROW  # shorthand for formula row references
    FORMULA_MIN = f"'=IFERROR((MINIFS($H:$H,$L:$L,\"Related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr})-MAXIFS($H:$H,$L:$L,\"Not related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr}))/MAXIFS($H:$H,$L:$L,\"Not related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr}),\"\")"
    FORMULA_MAX = f"'=IFERROR((MINIFS($I:$I,$L:$L,\"Related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr})-MAXIFS($I:$I,$L:$L,\"Not related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr}))/MAXIFS($I:$I,$L:$L,\"Not related\",$C:$C,C{dr},$E:$E,E{dr},$F:$F,F{dr}),\"\")"
    FORMULA_AMPERSAND = f"'=C{dr}&\"/\"&D{dr}&\"/\"&E{dr}&\"/\"&F{dr}"
    FORMULA_FLAG_CUSTOMS = f"'=IFERROR(IF(AND(E{dr}=\"Nhập\",M{dr}>-100%,M{dr}<0%,N{dr}>-100%,N{dr}<0%),\"x\",\"\"),\"\")"
    FORMULA_FLAG_TP = f"'=IFERROR(IF(OR(AND(E{dr}=\"Nhập\",M{dr}>0%,M{dr}<100%,N{dr}>0%,N{dr}<100%),AND(E{dr}=\"Xuất\",M{dr}>-100%,M{dr}<0%,N{dr}>-100%,N{dr}<0%)),\"x\",\"\"),\"\")"
    
    for col_idx in range(1, len(all_headers) + 1):
        cell = ws.cell(row=FILTER_ROW, column=col_idx, value="")
        if col_idx == 13:  # Variance test MIN
            cell.value = FORMULA_MIN
            cell.font = FORMULA_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        elif col_idx == 14:  # Variance test MAX
            cell.value = FORMULA_MAX
            cell.font = FORMULA_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        elif col_idx == 15:  # "&" concatenation
            cell.value = FORMULA_AMPERSAND
            cell.font = FORMULA_FONT
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        elif col_idx == 16:  # Flag for Customs
            cell.value = FORMULA_FLAG_CUSTOMS
            cell.font = FORMULA_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        elif col_idx == 17:  # Flag for TP
            cell.value = FORMULA_FLAG_TP
            cell.font = FORMULA_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if col_idx not in empty_cols:
            cell.border = THIN_BORDER
    
    # Set filter row height same as data rows
    ws.row_dimensions[FILTER_ROW].height = 12
    
    # Sort items alphabetically by: Mã NPL/SP → Tên đối tác → Flow → Điều kiện giá hóa đơn
    sorted_items = sorted(value_variance.items, key=lambda x: (
        x.ma_npl_sp or "",
        x.ten_doi_tac or "",
        x.flow or "",
        x.dieu_kien_gia_hoa_don or ""
    ))
    
    # First pass: Write data rows starting at DATA_START_ROW (row 4 after instruction/header/formula rows)
    # Columns that need "To fill" in italic
    to_fill_cols = [12, 13, 14, 16, 17]  # RPT, Variance MIN, Variance MAX, Flag Customs, Flag TP
    
    for row_idx, item in enumerate(sorted_items, DATA_START_ROW):
        # Compute "&" concatenation for VLOOKUP key
        ampersand_val = f"{item.ma_npl_sp or ''}/{item.ten_doi_tac or ''}/{item.flow or ''}/{item.dieu_kien_gia_hoa_don or ''}"
        
        row_data = [
            "",                                    # 1: Empty separator
            0,                                     # 2: STT (placeholder, will update)
            item.ma_npl_sp or "",                  # 3: Mã NPL/SP
            item.ten_doi_tac or "",                # 4: Tên đối tác (from item)
            item.flow or "",                       # 5: Flow
            item.dieu_kien_gia_hoa_don or "",      # 6: Điều kiện giá hóa đơn
            item.sum_tong_so_luong,                # 7: Sum of Tổng số lượng (total of ALL quantities)
            item.min_don_gia_tinh_thue,            # 8: Min of Đơn giá tính thuế
            item.max_don_gia_tinh_thue,            # 9: Max of Đơn giá tính thuế2
            "",                                    # 10: Empty separator
            0,                                     # 11: Count (placeholder, will update)
            "[To fill]",                           # 12: RPT
            "[To fill]",                           # 13: Variance test MIN
            "[To fill]",                           # 14: Variance test MAX
            ampersand_val,                         # 15: "&" concatenation for VLOOKUP
            "[To fill]",                           # 16: Flag for Customs
            "[To fill]",                           # 17: Flag for TP
        ]
        
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            
            # Use italic font for "[To fill]" columns (data rows)
            if col_idx in to_fill_cols:
                cell.font = ITALIC_FONT
            else:
                cell.font = CELL_FONT
            
            if col_idx in empty_cols:
                cell.border = NO_BORDER
            else:
                cell.border = THIN_BORDER
            
            if col_idx in (2, 11):  # STT and Count
                cell.alignment = CENTER_ALIGNMENT
            elif col_idx in (7, 8, 9):  # Number columns
                cell.alignment = NUMBER_ALIGNMENT
                cell.number_format = '#,##0'
            elif col_idx in (13, 14):  # Percentage columns (but showing "[To fill]" text)
                cell.alignment = CENTER_ALIGNMENT
            elif col_idx == 15:  # "&" concatenation column
                cell.alignment = CELL_ALIGNMENT
            else:
                cell.alignment = CELL_ALIGNMENT
    
    # Second pass: Read ACTUAL data from worksheet to calculate STT and Count
    # STT and Count are based on Mã NPL/SP only (same Mã NPL/SP = same STT)
    actual_rows = []  # List of (row_idx, npl_sp) from actual worksheet
    
    # Find actual last row by checking if there's data
    row_idx = DATA_START_ROW
    while True:
        # Check if row has any data (column 4 = Tên đối tác should have value)
        ten_doi_tac = ws.cell(row=row_idx, column=4).value
        if ten_doi_tac is None or ten_doi_tac == "":
            break
        # Read Mã NPL/SP only for STT and Count
        npl_sp = ws.cell(row=row_idx, column=3).value or ""
        actual_rows.append((row_idx, npl_sp))
        row_idx += 1
    
    # Build STT mapping based on Mã NPL/SP only
    npl_to_stt = {}
    stt_counter = 0
    for row_idx, npl_sp in actual_rows:
        if npl_sp not in npl_to_stt:
            stt_counter += 1
            npl_to_stt[npl_sp] = stt_counter
    
    # Count based on Mã NPL/SP only (number of rows with same Mã NPL/SP)
    npl_count = {}
    for row_idx, npl_sp in actual_rows:
        npl_count[npl_sp] = npl_count.get(npl_sp, 0) + 1
    
    # Third pass: Update STT and Count columns with correct values
    for row_idx, npl_sp in actual_rows:
        stt = npl_to_stt[npl_sp]
        count = npl_count[npl_sp]
        
        # Update STT (column 2)
        ws.cell(row=row_idx, column=2, value=stt)
        
        # Update Count (column 11)
        ws.cell(row=row_idx, column=11, value=count)
    
    # Set column widths
    for col_idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Set header row height
    ws.row_dimensions[HEADER_ROW_IDX].height = HEADER_ROW_HEIGHT
    
    # Add auto filter on FILTER_ROW (row 3)
    last_row = FILTER_ROW + len(actual_rows)
    ws.auto_filter.ref = f"B{FILTER_ROW}:Q{last_row}"
    
    # Hide filter on empty separator column
    ws.auto_filter.filterColumn.append(FilterColumn(colId=8, hiddenButton=True))
    
    # Add dropdown list for RPT column (column L = 12) with "Related" or "Not related"
    from openpyxl.worksheet.datavalidation import DataValidation
    rpt_validation = DataValidation(
        type="list",
        formula1='"Related,Not related"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Invalid Input",
        error="Please select 'Related' or 'Not related'"
    )
    rpt_validation.add(f"L{DATA_START_ROW}:L{last_row}")
    ws.add_data_validation(rpt_validation)
    
    # Freeze at K4 (columns A-J and rows 1-3 frozen)
    ws.freeze_panes = f"K{DATA_START_ROW}"


def _create_sheet_22a(wb: Workbook) -> None:
    """Create sheet 2.2a - RPT Questionnaire
    
    This sheet contains questions for customs valuation consultation,
    PCA checklist, and AEO checklist.
    """
    ws = wb.create_sheet("2.2a")
    apply_sheet_settings(ws)
    
    # Headers - 4 Client's answer columns for different suppliers
    headers = [
        "", "STT", "Questions (for reference)", "Ref sources",
        "Client's answer\nfor Supplier [1]", "Client's answer\nfor Supplier [2]",
        "Client's answer\nfor Supplier [3]", "Client's answer\nfor Supplier [4]"
    ]
    
    # Column widths
    column_widths = [2, 8, 80, 30, 25, 25, 25, 25]
    
    # Set column widths
    for col_idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Row 1: Headers
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        if col_idx == 1:
            cell.border = NO_BORDER
        else:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT
    
    # Row 2: Filter row (empty)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx, value="")
        if col_idx != 1:
            cell.border = THIN_BORDER
    ws.row_dimensions[2].height = 12
    
    # Questionnaire data (copied from reference file)
    questions = [
        # Customs valuation consultation (1-12)
        (1, "Đề nghị Công ty trình bày mối quan hệ giữa Công ty và đối tác xuất khẩu?", "Customs valuation consultation"),
        (2, "Quá trình giao dịch đàm phán được thực hiện như thế nào?", "Customs valuation consultation"),
        (3, "Đề nghị đại diện Công ty cung cấp hồ sơ lô hàng đang tham vấn?", "Customs valuation consultation"),
        (4, "Đề nghị Công ty xuất trình chứng từ thanh toán của lô hàng?", "Customs valuation consultation"),
        (5, "Đề nghị Công ty xuất trình sổ hoặc bản chụp sổ kế toán thể hiện việc ghi chép các nghiệp vụ kế toán có liên quan đến hàng hóa đang tham vấn (sổ tiền gửi ngân hàng, sổ chi tiết thanh toán, sổ chi tiết thanh toán bằng ngoại tệ...)?", "Customs valuation consultation"),
        (6, "Đề nghị Công ty xuất trình các chứng từ kế toán thể hiện các chi phí phát sinh với hàng hóa nhập khẩu từ khi thông quan đến khi nhập kho (ví dụ: chi phí vận tải, phụ phí xếp dỡ hàng tại bãi, chi phí kiểm tra chất lượng, kiểm dịch hàng hóa nếu có...)?", "Customs valuation consultation"),
        (7, "Đề nghị Công ty cho biết việc bán hàng hay giá cả có phụ thuộc vào điều kiện nào dẫn dến việc không xác định được trị giá của hàng hóa nhập khẩu không?", "Customs valuation consultation"),
        (8, "Đề nghị Công ty xuất trình tài liệu xác thực trị giá lô hàng đang được kiểm tra trị giá do cơ quan có thẩm quyền nước đối tác cung cấp (ví dụ: tờ khai hải quan đã được thông quan khi kê khai xuất khẩu đến Việt Nam, bản khai để được cấp giấy chứng nhận xuất xứ hàng hóa tại nước xuất khẩu...)?", "Customs valuation consultation"),
        (9, "Đề nghị Công ty cho biết các yếu tố ảnh hưởng đến giá các lô hàng đang tham vấn?", "Customs valuation consultation"),
        (10, "Đề nghị Công ty xuất trình hóa đơn bán hàng của hàng hóa đang tham vấn trị giá hoặc của lô hàng giống hệt, tương tự đã nhập khẩu tại thời điểm gần nhất?", "Customs valuation consultation"),
        (11, "Chi cục Hải quan nghi vấn giá Công ty nhập khẩu thấp hơn mặt hàng tương tự tại cơ sở dữ liệu giá của cơ quan Hải quan, đề nghị Công ty cho ý kiến?", "Customs valuation consultation"),
        (12, "Đại diện Công ty có cam đoan giá khai báo tại các tờ khai Hải quan, các chứng từ xuất trình nộp cho Cơ quan Hải quan là trung thực không? Công ty có toàn quyền định đoạt hàng hoá sau khi nhập khẩu không? Ngoài khoản tiền Công ty phải thanh toán theo chứng từ xuất trình Công ty có phải trả cho đối tác khoản tiền nào nữa không?", "Customs valuation consultation"),
        # PCA checklist (13-41)
        (13, "Các mặt hàng Công ty đã nhập khẩu trong giai đoạn kiểm tra được NK từ những đối tác nào? Thống kê tên mặt hàng ,đối tác nước ngoài bán hàng hóa cho Công ty.", "PCA checklist"),
        (14, "Đề nghị cung cấp thư chào hàng, hợp đồng, phụ lục hợp đồng,hóa đơn thương mại, chứng từ vận tải, chứng từ bảo hiểm, chứng từ thanh toán, phương thức thanh toán bằng TTr hay L/C…., ngân hàng thanh toán, đồng tiền thanh toán, sao kê ngân hàng, hồ sơ tài liệu liên quan đến hàng hóa trong giai đoạn kiểm tra, thỏa thuận hỗ trợ, tài trợ ...(trong mọi lĩnh vực) mà Công ty đã ký với các đối tác.", "PCA checklist"),
        (15, "Đề nghị Công ty báo cáo Phương pháp xác định trị giá tính thuế của các mặt hàng trong giai đoạn kiểm tra? Cơ sở để kê khai, xác định trị giá tính thuế theo phương pháp đã khai báo?", "PCA checklist"),
        (16, "Đề nghị trình bày mối quan hệ giữa Công ty và từng đối tác xuất khẩu hàng hóa, cơ sở để Công ty khai báo tại mục Mã phân loại tờ khai trị giá vào mã 6 (không có mối quan hệ đặc biệt).", "PCA checklist"),
        (17, "Ai là người trực tiếp tham gia vào quá trình giao dịch ký kết hợp đồng với các đối tác? Công ty có khẳng định trị giá khai báo thuộc các tờ khai nhập khẩu trong giai đoạn kiểm tra là số tiền thực tế phải thanh toán của Công ty với đối tác không?", "PCA checklist"),
        (18, "Đề nghị đại diện Công ty cho biết quá trình đàm phán giao dịch, ký kết hợp đồng ngoại thương đối với các lô hàng nhập khẩu đến khi bán ra diễn ra như thế nào? Phương thức đàm phán giá qua FAX? Email? Hay phương thức nào khác?", "PCA checklist"),
        (19, "Công ty có tài liệu nào chứng minh quá trình đàm phám giao dịch ký kết hợp đồng với đối tác đã diễn ra như vừa trình bày? Trường hợp khai giá được giảm thì yêu cầu cung cấp tài liệu chứng minh giá được giảm?", "PCA checklist"),
        (20, "Khi đàm phán với đối tác thì mức giá cả thỏa thuận có phụ thuộc vào số lượng hàng hóa nhập khẩu không? Có các khung giá ví dụ như: mua 10 chiếc thì giá là 10 đồng; 50 chiếc thì giá là 30 đồng… không? Nếu có đề nghị Công ty xuất trình toàn bộ các thỏa thuận trên.", "PCA checklist"),
        (21, "Yếu tố mua với số lượng nhiều, mua từ nhà sản xuất có ảnh hưởng như đến giá mua như thế nào?", "PCA checklist"),
        (22, "Công ty có được phía đối tác ưu đãi gì về giá, lượng… khi mua hàng hóa không? Nếu có đề nghị Công ty giải trình chi tiết kèm hồ sơ những ưu đãi trên.", "PCA checklist"),
        (23, "Có quy định số lượng tối thiểu của mỗi đơn TNHH? Nếu có đề nghị công ty giải thích rõ lý do.", "PCA checklist"),
        (24, "Đề nghị Công ty kể rõ tên các chứng từ có liên quan mà phía đối tác gửi cho phía Công ty khi mua hàng hóa để nhập khẩu", "PCA checklist"),
        (25, "Các hợp đồng khung, Phụ lục giá, purchase order, invoice, packing list…. thì Công ty gửi cho phía đối tác, đối tác gửi cho phía Công ty bằng hình thức nào?", "PCA checklist"),
        (26, "Khi đàm phán, mua bán với các đối tác trên thì mức giá đàm phán có phụ thuộc vào những điều kiện hay các khoản thanh toán khác không?", "PCA checklist"),
        (27, "Công ty có thể cung cấp chính sách bán hàng của đối tác không?", "PCA checklist"),
        (28, "Đề nghị Công ty cung cấp về thông tin giá bán của đối tác với các khách hàng khác ngoài Công ty ở Việt Nam", "PCA checklist"),
        (29, "Công ty có toàn quyền quyết định đối với hàng hóa sau khi nhập khẩu? nếu không thì phải phụ thuộc quy định nào khác của đối tác?", "PCA checklist"),
        (30, "Ngoài khoản tiền phải thanh toán với người bán theo hóa đơn, hợp đồng, Công ty có phải thanh toán thêm bất kỳ khoản nào khác cho người bán hoặc người thứ 3 để nhập khẩu được các hàng hóa này không?", "PCA checklist"),
        (31, "Công ty có được đối tác nước ngoài chiết khấu, giảm giá đối với các mặt hàng nhập khẩu không? Nếu có thì cung cấp tài liệu giấy tờ chứng minh", "PCA checklist"),
        (32, "Việc bán hàng nhập khẩu của Công ty được thực hiện như thế nào? Việc bán hàng cho người mua có phụ thuộc quy định nào giữa Công ty và đối tác nước ngoài cung cấp hàng hóa nhập khẩu?", "PCA checklist"),
        (33, "Công ty theo dõi các mã kho của hàng hóa nhập về với mã kho của hàng hóa bán ra có thống nhất không? Nếu khác biệt đề nghị giải trình chi tiết.", "PCA checklist"),
        (34, "Công ty có mua bảo hiểm cho các lô hàng nhập khẩu hay không? Đề nghị xuất trình chứng từ tài liệu nếu có", "PCA checklist"),
        (35, "Trong quá trình làm thủ tục nhập khẩu, Công ty có được phía cơ quan hải quan tiến hành tham vấn/kiểm tra sau thông quan hay không? Kết quả có bao nhiêu tờ khai được chấp nhận trị giá/không chấp nhận trị giá khai báo?", "PCA checklist"),
        (36, "Đã có cơ quan hải quan hay Đoàn kiểm tra, thanh tra nào kiểm tra và có ý kiến về việc xác định trị giá tính thuế đối với các mặt hàng Công ty nhập khẩu? Đề nghị cung cấp Kết luận của Đoàn kiểm tra, thanh tra và kết quả thực hiện các ý kiến kết luận này (nếu có).", "PCA checklist"),
        (37, "Đề nghị Công ty tự rà soát và kê khai cho Đoàn kiểm tra các chi phí liên quan đến khoản phải cộng vào trị giá hàng hóa nhập khẩu theo quy định tại Thông tư 39/2015/TT-BTC ngày 25/03/2015 mà Công ty đã tính, hoặc chưa tính trong giai đoạn kiểm tra (Đề nghị ghi rõ đã tính/chưa tính)", "PCA checklist"),
        (38, "Đề nghị Công ty cung cấp các địa chỉ Email đặt hàng của Công ty, Email giao dịch của phía đối tác?", "PCA checklist"),
        (39, "Đề nghị Công ty xuất trình, cung cấp, mở các Email giao dịch với phía đối tác cho Đoàn kiểm tra?", "PCA checklist"),
        (40, "Đề nghị Công ty cung cấp sổ sách, chứng từ kế toán, báo cáo tài chính trong giai đoạn kiểm tra.", "PCA checklist"),
        (41, "Đề nghị công ty cung cấp cơ sở xác định trị giá giao dịch khi quan hệ giữa người mua và người bán có mối quan hệ đặc biệt nhưng không ảnh hưởng tới trị giá giao dịch.", "PCA checklist"),
        # AEO Checklist (42-64)
        (42, "Công ty và đối tác xuất khẩu có mối quan hệ đặc biệt theo quy định của pháp luật hay không?", "AEO Checklist"),
        (43, "Người đàm phán các hợp đồng ngoại thương có nắm vững mọi hoạt động kinh doanh xuất nhập khẩu của Công ty không?", "AEO Checklist"),
        (44, "Việc đàm phán giá cả có bị hạn chế bởi sự chỉ định/ràng buộc của bên thứ 3 hay không?", "AEO Checklist"),
        (45, "Công ty có lưu trữ Bảng chào giá của người bán không?", "AEO Checklist"),
        (46, "Công ty có toàn quyền định đoạt đối với hàng hóa sau khi nhập khẩu không?", "AEO Checklist"),
        (47, "Ngoài khoản tiền phải thanh toán với người bán theo hóa đơn, hợp đồng, Công ty có phải thanh toán thêm bất kỳ khoản nào khác cho người bán hoặc người thứ 3 do người bán chỉ định để nhập khẩu được các hàng hóa này không?", "AEO Checklist"),
        (48, "Công ty có thanh toán nhiều lần cho mỗi lô hàng nhập khẩu không?", "AEO Checklist"),
        (49, "Công ty có được đối tác nước ngoài chiết khấu, giảm giá đối với hàng hóa nhập khẩu không?", "AEO Checklist"),
        (50, "Việc giảm giá/chiết khấu có được 2 bên ghi nhận bằng văn bản không?", "AEO Checklist"),
        (51, "Việc bán hàng sau khi nhập khẩu của Công ty có phải tuân theo quy định nào khác của đối tác không?", "AEO Checklist"),
        (52, "Việc ký hợp đồng giữa công ty và đối tác có bên thứ 3 tham gia hay không?", "AEO Checklist"),
        (53, "Công ty có thanh toán cho đối tác theo hình thức TTr?", "AEO Checklist"),
        (54, "Công ty có thanh toán cho đối tác theo hình thức L/C?", "AEO Checklist"),
        (55, "Công ty có thanh toán cho đối tác theo hình thức DP?", "AEO Checklist"),
        (56, "Công ty có thanh toán cho đối tác theo hình thức khác không?", "AEO Checklist"),
        (57, "Nhãn hiệu của hàng hóa mà công ty mua có thuộc loại hàng hóa do đối tác độc quyền phân phối hay không?", "AEO Checklist"),
        (58, "Hàng hóa do công ty nhập khẩu có thuộc loại hàng dễ vỡ, dễ hỏng hóc hay không?", "AEO Checklist"),
        (59, "Công ty có trực tiếp phân phối sản phẩm nhập khẩu không?", "AEO Checklist"),
        (60, "Công ty có lưu trữ tài liệu/dữ liệu (bao gồm cả dạng dữ liệu điện tử) trong quá trình đàm phán hay không?", "AEO Checklist"),
        (61, "Công ty có nhập khẩu hàng hóa từ những quốc gia ký hiệp định ưu đãi về thuế với Việt Nam không?", "AEO Checklist"),
        (62, "Công ty có quy trình tự kiểm tra giấy chứng nhận xuất xứ không", "AEO Checklist"),
        (63, "Công ty có nộp lại giấy chứng nhận xuất xứ cho cơ quan hải quan sau khi thông quan hàng hóa không?", "AEO Checklist"),
        (64, "Bộ phận xuất nhập khẩu của Công ty có đảm bảo hiểu rõ về pháp luật hải quan, pháp luật thuế không?", "AEO Checklist"),
    ]
    
    # Write data rows starting from row 3
    for row_idx, (stt, question, ref_source) in enumerate(questions, 3):
        # Empty column A
        ws.cell(row=row_idx, column=1, value="").border = NO_BORDER
        
        # STT
        cell = ws.cell(row=row_idx, column=2, value=stt)
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = CENTER_ALIGNMENT
        
        # Questions (for reference)
        cell = ws.cell(row=row_idx, column=3, value=question)
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        
        # Ref sources
        cell = ws.cell(row=row_idx, column=4, value=ref_source)
        cell.font = CELL_FONT
        cell.border = THIN_BORDER
        cell.alignment = CELL_ALIGNMENT
        
        # Client's answer columns (4 empty columns for different suppliers)
        for col_idx in range(5, 9):  # Columns 5, 6, 7, 8
            cell = ws.cell(row=row_idx, column=col_idx, value="")
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = CELL_ALIGNMENT
        
        # Set row height for questions (auto-wrap)
        ws.row_dimensions[row_idx].height = 30  # Increased height for wrapped text
    
    # Add auto filter
    last_row = 2 + len(questions)
    ws.auto_filter.ref = f"B2:H{last_row}"
    
    # Freeze panes at C3
    ws.freeze_panes = "C3"


def _create_sheet_23(wb: Workbook, value_variance: ValueVarianceReport) -> Dict[str, str]:
    """Create sheet 2.3 - Additions/deductions check
    
    Returns:
        Dictionary mapping ma_npl_sp to flag value ("x" or "")
    """
    from openpyxl.formatting.rule import FormulaRule
    
    ws = wb.create_sheet("2.3")
    apply_sheet_settings(ws)
    
    # Font styles for this sheet
    FLAG_FORMULA_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")  # Bold red for formula display
    FLAG_X_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")  # Bold red for "x"
    
    # Headers for 2.3
    # Dark headers (yellow on black)
    headers_dark = [
        "", "STT", "Mã NPL/SP", "Flow", "Điều kiện giá\nhóa đơn", "Sum of Tổng\nsố lượng",
        "Min of Đơn giá\ntính thuế", "Average of Đơn\ngiá tính thuế2", "Max of Đơn giá\ntính thuế3"
    ]
    # Yellow headers (black on yellow)
    headers_yellow = [
        "", "Test MIN", "Test MED", "Test MAX", "Flag"
    ]
    
    all_headers = headers_dark + headers_yellow
    empty_cols = [1, 10]  # Empty separator columns
    yellow_header_cols = list(range(11, 15))  # Test MIN, Test MED, Test MAX, Flag
    
    column_widths = [2, 8, 20, 10, 18, 18, 20, 20, 20, 2, 12, 12, 12, 12]
    
    # Row 1: Headers
    for col_idx, header in enumerate(all_headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        if col_idx in empty_cols:
            cell.border = NO_BORDER
        elif col_idx in yellow_header_cols:
            cell.font = NEW_COL_HEADER_FONT
            cell.fill = NEW_COL_HEADER_FILL
            cell.alignment = NEW_COL_HEADER_ALIGNMENT
            cell.border = THIN_BORDER
        else:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Row 2: Filter row with formula display in Flag column
    # Formula displayed as text (with leading quote) in Flag column
    # COUNTBLANK checks that all 3 cells have values, then check all > 0%
    FLAG_FORMULA_DISPLAY = "'=IFERROR(IF(AND(COUNTBLANK(K2:M2)=0,K2>0%,L2>0%,M2>0%),\"x\",\"\"),\"\")"
    
    for col_idx in range(1, len(all_headers) + 1):
        cell = ws.cell(row=2, column=col_idx, value="")
        if col_idx == 14:  # Flag column - show formula as text
            cell.value = FLAG_FORMULA_DISPLAY
            cell.font = FLAG_FORMULA_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if col_idx not in empty_cols:
            cell.border = THIN_BORDER
    
    # Set filter row height same as data rows
    ws.row_dimensions[2].height = 12
    
    # ============================================================================
    # MERGE ROWS: Aggregate items by (ma_npl_sp, flow, dieu_kien_gia_hoa_don)
    # Sum quantities, take min of min prices, max of max prices
    # Use sum_don_gia_tinh_thue and count_don_gia_tinh_thue for true average
    # ============================================================================
    aggregated_data = {}
    for item in value_variance.items:
        key = (
            item.ma_npl_sp or "",
            item.flow or "",
            item.dieu_kien_gia_hoa_don or ""
        )
        
        if key not in aggregated_data:
            aggregated_data[key] = {
                'ma_npl_sp': item.ma_npl_sp or "",
                'flow': item.flow or "",
                'dieu_kien_gia_hoa_don': item.dieu_kien_gia_hoa_don or "",
                'tong_so_luong_min': item.tong_so_luong_min or 0,
                # Sum of ALL tong_so_luong values (for display in "Sum of Tổng số lượng" column)
                'sum_tong_so_luong': item.sum_tong_so_luong or 0,
                'min_don_gia_tinh_thue': item.min_don_gia_tinh_thue,
                'max_don_gia_tinh_thue': item.max_don_gia_tinh_thue,
                # Use actual sum and count from source data
                'sum_don_gia': item.sum_don_gia_tinh_thue or 0,
                'count_don_gia': item.count_don_gia_tinh_thue or 0,
            }
        else:
            # Sum tong_so_luong_min (for impact calculation)
            aggregated_data[key]['tong_so_luong_min'] = (
                (aggregated_data[key]['tong_so_luong_min'] or 0) + 
                (item.tong_so_luong_min or 0)
            )
            # Sum ALL tong_so_luong (for display)
            aggregated_data[key]['sum_tong_so_luong'] = (
                (aggregated_data[key]['sum_tong_so_luong'] or 0) + 
                (item.sum_tong_so_luong or 0)
            )
            # Take min of min prices
            if item.min_don_gia_tinh_thue is not None:
                if aggregated_data[key]['min_don_gia_tinh_thue'] is None:
                    aggregated_data[key]['min_don_gia_tinh_thue'] = item.min_don_gia_tinh_thue
                else:
                    aggregated_data[key]['min_don_gia_tinh_thue'] = min(
                        aggregated_data[key]['min_don_gia_tinh_thue'],
                        item.min_don_gia_tinh_thue
                    )
            # Take max of max prices
            if item.max_don_gia_tinh_thue is not None:
                if aggregated_data[key]['max_don_gia_tinh_thue'] is None:
                    aggregated_data[key]['max_don_gia_tinh_thue'] = item.max_don_gia_tinh_thue
                else:
                    aggregated_data[key]['max_don_gia_tinh_thue'] = max(
                        aggregated_data[key]['max_don_gia_tinh_thue'],
                        item.max_don_gia_tinh_thue
                    )
            # Accumulate true sum and count for average calculation
            if item.sum_don_gia_tinh_thue is not None:
                aggregated_data[key]['sum_don_gia'] += item.sum_don_gia_tinh_thue
            if item.count_don_gia_tinh_thue is not None:
                aggregated_data[key]['count_don_gia'] += item.count_don_gia_tinh_thue
    
    # Convert to list and sort
    aggregated_items = list(aggregated_data.values())
    aggregated_items.sort(key=lambda x: (x['ma_npl_sp'], x['flow'], x['dieu_kien_gia_hoa_don']))
    
    # Build STT mapping based on ma_npl_sp only (same ma_npl_sp = same STT)
    npl_to_stt = {}
    stt_counter = 0
    for item in aggregated_items:
        npl_sp = item['ma_npl_sp']
        if npl_sp not in npl_to_stt:
            stt_counter += 1
            npl_to_stt[npl_sp] = stt_counter
    
    # Write data rows starting at row 3
    for row_idx, item in enumerate(aggregated_items, 3):
        stt = npl_to_stt.get(item['ma_npl_sp'], "")
        
        # Calculate average = Sum / Count (not midpoint of min/max)
        avg_price = None
        if item['count_don_gia'] > 0:
            avg_price = item['sum_don_gia'] / item['count_don_gia']
        
        # Excel formulas with dynamic row number for Test MIN, Test MED, Test MAX
        # Note: _xlfn. prefix is required for MINIFS/MAXIFS to work properly when written via openpyxl
        # Wrap with IFERROR to handle #DIV/0! when there's no import data (denominator = 0)
        formula_test_min = f'=IFERROR((_xlfn.MINIFS($G:$G,$C:$C,C{row_idx},$D:$D,"Xuất")-_xlfn.MAXIFS($G:$G,$C:$C,C{row_idx},$D:$D,"Nhập"))/_xlfn.MAXIFS($G:$G,$C:$C,C{row_idx},$D:$D,"Nhập"),"")'
        formula_test_med = f'=IFERROR((_xlfn.MINIFS($H:$H,$C:$C,C{row_idx},$D:$D,"Xuất")-_xlfn.MAXIFS($H:$H,$C:$C,C{row_idx},$D:$D,"Nhập"))/_xlfn.MAXIFS($H:$H,$C:$C,C{row_idx},$D:$D,"Nhập"),"")'
        formula_test_max = f'=IFERROR((_xlfn.MINIFS($I:$I,$C:$C,C{row_idx},$D:$D,"Xuất")-_xlfn.MAXIFS($I:$I,$C:$C,C{row_idx},$D:$D,"Nhập"))/_xlfn.MAXIFS($I:$I,$C:$C,C{row_idx},$D:$D,"Nhập"),"")'
        
        row_data = [
            "",                                    # 1: Empty separator
            stt,                                   # 2: STT
            item['ma_npl_sp'],                     # 3: Mã NPL/SP
            item['flow'],                          # 4: Flow
            item['dieu_kien_gia_hoa_don'],         # 5: Điều kiện giá hóa đơn
            item['sum_tong_so_luong'],             # 6: Sum of Tổng số lượng (total of ALL quantities)
            item['min_don_gia_tinh_thue'],         # 7: Min of Đơn giá tính thuế
            avg_price,                             # 8: Average of Đơn giá tính thuế2
            item['max_don_gia_tinh_thue'],         # 9: Max of Đơn giá tính thuế3
            "",                                    # 10: Empty separator
            None,                                  # 11: Test MIN (formula set separately)
            None,                                  # 12: Test MED (formula set separately)
            None,                                  # 13: Test MAX (formula set separately)
            "",                                    # 14: Flag (empty)
        ]
        
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = CELL_FONT
            
            if col_idx in empty_cols:
                cell.border = NO_BORDER
            else:
                cell.border = THIN_BORDER
            
            if col_idx == 2:  # STT
                cell.alignment = CENTER_ALIGNMENT
            elif col_idx in (6, 7, 8, 9):  # Number columns
                cell.alignment = NUMBER_ALIGNMENT
                cell.number_format = '#,##0'
            elif col_idx in (11, 12, 13):  # Formula columns - percentage format
                cell.alignment = CENTER_ALIGNMENT
                cell.number_format = '0.00%'
            elif col_idx == 14:  # Flag column - center
                cell.alignment = CENTER_ALIGNMENT
            else:
                cell.alignment = CELL_ALIGNMENT
        
        # Set formulas separately for Test columns (using direct cell assignment)
        ws.cell(row=row_idx, column=11).value = formula_test_min
        ws.cell(row=row_idx, column=12).value = formula_test_med
        ws.cell(row=row_idx, column=13).value = formula_test_max
        
        # Flag formula: "x" if all 3 test values exist (not blank) and > 0%
        # K = Test MIN, L = Test MED, M = Test MAX
        # COUNTBLANK checks all 3 cells have values, then check all > 0%
        formula_flag = f'=IFERROR(IF(AND(COUNTBLANK(K{row_idx}:M{row_idx})=0,K{row_idx}>0%,L{row_idx}>0%,M{row_idx}>0%),"x",""),"")'
        flag_cell = ws.cell(row=row_idx, column=14)
        flag_cell.value = formula_flag
    
    # Set column widths
    for col_idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Set header row height
    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT
    
    # Add auto filter on row 2
    last_row = 2 + len(aggregated_items)
    ws.auto_filter.ref = f"B2:N{last_row}"
    
    # Hide filter on empty separator column
    ws.auto_filter.filterColumn.append(FilterColumn(colId=8, hiddenButton=True))
    
    # Freeze at K3 (columns A-J and rows 1-2 frozen)
    ws.freeze_panes = "K3"
    
    # Add conditional formatting for Flag column: bold red "x"
    # When cell value equals "x", apply bold red font
    from openpyxl.formatting.rule import CellIsRule
    ws.conditional_formatting.add(
        f'N3:N{last_row}',
        CellIsRule(operator='equal', formula=['"x"'], font=FLAG_X_FONT)
    )
    
    # ============================================================================
    # Compute flag mapping for input sheet (same logic as formulas)
    # Flag = "x" if for the same ma_npl_sp:
    #   MIN(export prices) > MAX(import prices) for all 3 price metrics
    # ============================================================================
    npl_to_23_flag = {}
    
    # Group by ma_npl_sp
    npl_groups = {}
    for item in aggregated_items:
        npl_sp = item['ma_npl_sp']
        if npl_sp not in npl_groups:
            npl_groups[npl_sp] = {'export': [], 'import': []}
        if item['flow'] == 'Xuất':
            npl_groups[npl_sp]['export'].append(item)
        elif item['flow'] == 'Nhập':
            npl_groups[npl_sp]['import'].append(item)
    
    for npl_sp, groups in npl_groups.items():
        export_items = groups['export']
        import_items = groups['import']
        
        if not export_items or not import_items:
            npl_to_23_flag[npl_sp] = ""
            continue
        
        # Test MIN: compare min_don_gia_tinh_thue (column G)
        export_min_prices = [item['min_don_gia_tinh_thue'] for item in export_items 
                           if item['min_don_gia_tinh_thue'] is not None]
        import_min_prices = [item['min_don_gia_tinh_thue'] for item in import_items 
                           if item['min_don_gia_tinh_thue'] is not None]
        
        # Test MED: compare average prices (column H) = Sum / Count
        export_avg_prices = [item['sum_don_gia'] / item['count_don_gia']
                           for item in export_items 
                           if item['count_don_gia'] > 0]
        import_avg_prices = [item['sum_don_gia'] / item['count_don_gia']
                           for item in import_items 
                           if item['count_don_gia'] > 0]
        
        # Test MAX: compare max_don_gia_tinh_thue (column I)
        export_max_prices = [item['max_don_gia_tinh_thue'] for item in export_items 
                           if item['max_don_gia_tinh_thue'] is not None]
        import_max_prices = [item['max_don_gia_tinh_thue'] for item in import_items 
                           if item['max_don_gia_tinh_thue'] is not None]
        
        # Calculate tests: (MIN export - MAX import) / MAX import
        test_min = test_med = test_max = 0
        
        if export_min_prices and import_min_prices:
            min_export = min(export_min_prices)
            max_import = max(import_min_prices)
            if max_import != 0:
                test_min = (min_export - max_import) / max_import
        
        if export_avg_prices and import_avg_prices:
            min_export_avg = min(export_avg_prices)
            max_import_avg = max(import_avg_prices)
            if max_import_avg != 0:
                test_med = (min_export_avg - max_import_avg) / max_import_avg
        
        if export_max_prices and import_max_prices:
            min_export_max = min(export_max_prices)
            max_import_max = max(import_max_prices)
            if max_import_max != 0:
                test_max = (min_export_max - max_import_max) / max_import_max
        
        # Flag = "x" if all 3 tests > 0
        if test_min > 0 and test_med > 0 and test_max > 0:
            npl_to_23_flag[npl_sp] = "x"
        else:
            npl_to_23_flag[npl_sp] = ""
    
    return npl_to_23_flag


def _create_ntm_sheet(wb: Workbook, ntm_report: NTMReport) -> None:
    """Create Non-Tariff Measures sheet"""
    ws3 = wb.create_sheet("Non-Tariff Measures")
    apply_sheet_settings(ws3)
    
    headers_ntm = ["", "Flow", "HS Code", "Mã NPL/SP", "Tên hàng", "Link"]
    
    for col_idx, header in enumerate(headers_ntm, 1):
        cell = ws3.cell(row=1, column=col_idx, value=header)
        cell.border = NO_BORDER
        if header:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
    
    for row_idx, item in enumerate(ntm_report.items, 2):
        # Data columns (excluding train_link, handled separately)
        row_data = ["", item.qd_1357, item.hs_code, item.ma_npl_sp or "",
                    item.ten_hang or ""]
        
        for col_idx, value in enumerate(row_data, 1):
            cell = ws3.cell(row=row_idx, column=col_idx, value=value)
            cell.font = CELL_FONT
            if col_idx != 1:
                cell.border = THIN_BORDER
            cell.alignment = CELL_ALIGNMENT
        
        # Handle Link column - show "Link" text with embedded hyperlink
        link_cell = ws3.cell(row=row_idx, column=6)
        link_cell.border = THIN_BORDER
        link_cell.alignment = CELL_ALIGNMENT
        
        if item.train_link and str(item.train_link).startswith("http"):
            link_cell.value = "Link"
            link_cell.hyperlink = item.train_link
            link_cell.font = LINK_FONT
        else:
            link_cell.value = "N/A"
            link_cell.font = CELL_FONT
    
    # Adjusted column widths (Link column is shorter now)
    for col_idx, width in enumerate([2, 10, 12, 25, 50, 10], 1):
        ws3.column_dimensions[get_column_letter(col_idx)].width = width
    ws3.freeze_panes = "B2"


def _get_transaction_notes(ma_hieu_ptvc: str) -> str:
    """Get Transaction notes based on Mã hiệu PTVC
    
    Args:
        ma_hieu_ptvc: Transport method code
        
    Returns:
        "OTS imports/exports" if PTVC="9", "Regular imports/exports" if PTVC="1"-"6", else ""
    """
    ptvc = str(ma_hieu_ptvc or '').strip()
    if ptvc == '9':
        return "OTS imports/exports"
    elif ptvc in ['1', '2', '3', '4', '5', '6']:
        return "Regular imports/exports"
    return ""


def _get_chemical_notes(hs_code: str) -> str:
    """Get Chemical notes based on HS Chapter
    
    Args:
        hs_code: HS code (8 digits typically)
        
    Returns:
        "Chemical" if HS Chapter 28-40, "Non-chemical" otherwise
    """
    if not hs_code:
        return "Non-chemical"
    
    hs_clean = str(hs_code).replace('.', '').replace(' ', '').strip()
    if len(hs_clean) >= 2:
        try:
            chapter = int(hs_clean[:2])
            if 28 <= chapter <= 40:
                return "Chemical"
        except ValueError:
            pass
    return "Non-chemical"


def _check_31_filter(item: Dict) -> bool:
    """Check if an item passes the 3.1 sheet filter criteria
    
    Criteria:
    - Flow = "Nhập" (Import only)
    - Số TK starts with "1"
    - Mã hiệu PTVC != "9"
    - Tên đối tác does NOT contain: "Viet Nam", "Việt Nam", "Cong ty" (case insensitive)
    
    Args:
        item: Dictionary with item fields
        
    Returns:
        True if item passes filter, False otherwise
    """
    # Flow must be "Nhập"
    flow = item.get('flow', '')
    if flow != "Nhập":
        return False
    
    # Số TK must start with "1"
    so_tk = str(item.get('so_tk', '') or '')
    if not so_tk.startswith('1'):
        return False
    
    # Mã hiệu PTVC must not be "9"
    ma_hieu_ptvc = str(item.get('ma_hieu_ptvc', '') or '').strip()
    if ma_hieu_ptvc == '9':
        return False
    
    # Tên đối tác must NOT contain Vietnamese company names
    ten_doi_tac = str(item.get('ten_doi_tac', '') or '').lower()
    excluded_patterns = [
        'viet nam', 'việt nam', 'vietnam', 'việtnam',
        'cong ty', 'công ty', 'congty', 'côngty'
    ]
    for pattern in excluded_patterns:
        if pattern in ten_doi_tac:
            return False
    
    return True


def _get_31_exclusion_reason(item: Dict) -> str:
    """Get exclusion reason for items that fail the 3.1 filter.
    
    Returns:
        Exclusion reason string, or empty if item passes filter
    """
    flow = item.get('flow', '')
    if flow != "Nhập":
        return f"excluded - Flow={flow or 'empty'}"
    
    so_tk = str(item.get('so_tk', '') or '')
    if not so_tk.startswith('1'):
        return "excluded - Số TK not starting with 1"
    
    ma_hieu_ptvc = str(item.get('ma_hieu_ptvc', '') or '').strip()
    if ma_hieu_ptvc == '9':
        return "excluded - PTVC=9"
    
    ten_doi_tac = str(item.get('ten_doi_tac', '') or '').lower()
    excluded_patterns = [
        'viet nam', 'việt nam', 'vietnam', 'việtnam',
        'cong ty', 'công ty', 'congty', 'côngty'
    ]
    for pattern in excluded_patterns:
        if pattern in ten_doi_tac:
            return "excluded - VN partner"
    
    return ""


def _create_sheet_31(
    wb: Workbook, 
    ntm_report: NTMReport,
    original_rows: List[ExcelRowData] = None
) -> Tuple[Dict, Dict, int]:
    """Create 3.1 sheet - Non-Tariff Measures check (merged 3.1 and 3.2)
    
    Returns:
        Tuple of (flag_31_mapping, exclusion_31_mapping, max_appendix_count)
    
    Structure matches old 3.1 and 3.2 sheets:
    - Dark section: STT, Mã HS, Flow, Transaction notes, Mã NPL/SP, Tên hàng, Chemical notes,
      Mã loại hình, Số TK, Ngày ĐK, Sum of Tổng số lượng, Đơn vị tính
    - Yellow section (from old 3.1): &, Exclusion, Reason, TRAIN ref, VN Tariff ref,
      COMMODITY POLICY 2024, then CHÍNH SÁCH HH N, Đánh Giá N, Flag (split from policy)
    - Red section (from old 3.2): NTM for chemical, CAS No., CAS sources,
      then CHÍNH SÁCH HH N-C, Đánh Giá N-C, Flag N-C (from NĐ24 appendices)
    
    Args:
        wb: Workbook to add sheet to
        ntm_report: NTM report data
        original_rows: Original Excel row data
        
    Returns:
        Tuple of (flag_31_mapping, exclusion_31_mapping)
    """
    ws = wb.create_sheet("3.1")
    apply_sheet_settings(ws)
    
    # Result mappings for Flag 3.1 and Exclusion in input sheet
    flag_31_mapping = {}
    exclusion_31_mapping = {}
    
    # ============================================================================
    # STEP 1: Build set of NTM items (hs_code_6, ma_npl_sp, ten_hang) with train_link
    # ============================================================================
    ntm_items_set = set()
    ntm_train_links = {}
    for item in ntm_report.items:
        hs_code_6 = item.hs_code or ""
        ntm_key = (hs_code_6, item.ma_npl_sp or "", item.ten_hang or "")
        ntm_items_set.add(ntm_key)
        if item.train_link:
            ntm_train_links[ntm_key] = item.train_link
    
    # ============================================================================
    # STEP 2: Build data from original_rows - MERGE by (Mã HS, Tên hàng, Số TK, Ngày ĐK)
    # ============================================================================
    aggregated_data = {}
    logger.info(f"[3.1] original_rows: {len(original_rows) if original_rows else 'None'}, ntm_items_set: {len(ntm_items_set)} items")
    
    if original_rows:
        for row in original_rows:
            flow = row.flow or get_flow_from_ma_loai_hinh(row.ma_loai_hinh).value if row.ma_loai_hinh else ""
            flow_vn = "Nhập" if flow == "Nhập" or flow == "NHAP" else "Xuất" if flow else ""
            hs_code_full = row.ma_hs or ''
            hs_code_6 = hs_code_full[:6] if hs_code_full else ''
            
            # Build flag_key for exclusion mapping
            flag_key = (flow_vn, hs_code_6, row.ma_npl_sp or "", row.ten_hang or "")
            
            # Check if in NTM report
            ntm_key = (hs_code_6, row.ma_npl_sp or "", row.ten_hang or "")
            if ntm_key not in ntm_items_set:
                if flag_key not in exclusion_31_mapping:
                    exclusion_31_mapping[flag_key] = "excluded - HS not in NTM"
            
            # Parse tong_so_luong
            try:
                tsl_value = float(str(row.tong_so_luong or 0).replace(',', ''))
            except (ValueError, TypeError):
                tsl_value = 0
            
            # Unique key: (Mã HS, Tên hàng, Số TK, Ngày ĐK)
            unique_key = (hs_code_full, row.ten_hang or "", row.so_tk or "", row.ngay_dk or "")
            
            if unique_key not in aggregated_data:
                aggregated_data[unique_key] = {
                    'flow': flow_vn,
                    'hs_code': hs_code_full,
                    'hs_code_6': hs_code_6,
                    'ma_npl_sp': row.ma_npl_sp or "",
                    'ten_hang': row.ten_hang or "",
                    'so_tk': row.so_tk or "",
                    'ngay_dk': row.ngay_dk or "",
                    'ma_loai_hinh': row.ma_loai_hinh or "",
                    'ma_hieu_ptvc': row.ma_hieu_ptvc or "",
                    'ten_doi_tac': row.ten_doi_tac or "",
                    'tong_so_luong': tsl_value,
                    'don_vi_tinh': row.don_vi_tinh or "",
                    'train_link': ntm_train_links.get(ntm_key, ""),
                    'in_ntm': ntm_key in ntm_items_set,
                }
            else:
                # Sum tong_so_luong for merged rows
                aggregated_data[unique_key]['tong_so_luong'] += tsl_value
    
    all_items = list(aggregated_data.values())
    
    # ============================================================================
    # STEP 3: Build flag mappings
    # ============================================================================
    for item in all_items:
        flag_key = (item['flow'], item['hs_code_6'], item['ma_npl_sp'], item['ten_hang'])
        if item['in_ntm'] and _check_31_filter(item):
            flag_31_mapping[flag_key] = "x"
        elif item['in_ntm']:
            reason = _get_31_exclusion_reason(item)
            if reason and flag_key not in exclusion_31_mapping:
                exclusion_31_mapping[flag_key] = reason
    
    # Sort by HS code (and secondary keys for consistency)
    sorted_items = sorted(
        all_items,
        key=lambda x: (x['hs_code'] or '', x['ten_hang'] or '', x.get('so_tk', ''), x.get('ngay_dk', ''))
    )
    
    # Pre-calculate STT for each HS code (same HS code = same STT)
    hs_code_to_stt = {}
    stt_counter = 0
    for item in sorted_items:
        hs_code = item['hs_code'] or ''
        if hs_code and hs_code not in hs_code_to_stt:
            stt_counter += 1
            hs_code_to_stt[hs_code] = stt_counter
    
    logger.info(f"Sheet 3.1: {len(sorted_items)} unique rows (merged by HS+Tên hàng+Số TK+Ngày ĐK), {len(hs_code_to_stt)} unique HS codes")
    
    # ============================================================================
    # STEP 4: Dynamic column counts based on actual data
    # ============================================================================
    # Policy count: 5 (for COMMODITY POLICY columns) - fixed for consistency
    MAX_POLICY_COUNT = 5
    max_policy_count = MAX_POLICY_COUNT
    
    logger.info(f"Sheet 3.1: Using policy count = {max_policy_count}")
    
    # ============================================================================
    # STEP 5: Pre-process CAS extraction and NĐ24 appendix matching for chemical items
    # ============================================================================
    cas_results = {}  # idx -> {'cas': str, 'source': str}
    appendix_results = {}  # idx -> {'appendix_matches': [...], 'nguong_khoi_luong': str}
    ten_hang_to_indices = {}
    products_needing_llm = set()
    
    # Track all chemical indices that need CAS filling
    all_chemical_indices = set()
    
    for idx, item in enumerate(sorted_items):
        # Only extract CAS for chemical items
        if _get_chemical_notes(item['hs_code']) != "Chemical":
            continue
        
        all_chemical_indices.add(idx)
            
        ten_hang = item['ten_hang'] or ""
        ten_hang_clean = ten_hang.strip()
        cas_number = None
        cas_source = None
        
        try:
            cas_number, _ = extract_cas_from_ten_hang(ten_hang)
            if cas_number:
                cas_source = "Tên hàng"
        except Exception as e:
            logger.warning(f"Error extracting CAS from '{ten_hang[:50]}...': {e}")
        
        if cas_number:
            cas_results[idx] = {'cas': cas_number, 'source': cas_source}
        elif ten_hang_clean:
            # Has ten_hang but no CAS from regex -> queue for LLM
            if ten_hang_clean not in ten_hang_to_indices:
                ten_hang_to_indices[ten_hang_clean] = []
            ten_hang_to_indices[ten_hang_clean].append(idx)
            products_needing_llm.add(ten_hang_clean)
        else:
            # No ten_hang -> mark as unknown immediately
            cas_results[idx] = {'cas': 'unknown', 'source': 'AI Cognitive'}
    
    # Batch LLM call for products without CAS
    if products_needing_llm:
        try:
            llm_results = batch_extract_cas_via_llm_sync(list(products_needing_llm))
            for ten_hang_clean, indices in ten_hang_to_indices.items():
                cas_from_llm = llm_results.get(ten_hang_clean)
                for idx in indices:
                    if cas_from_llm:
                        # LLM found CAS
                        cas_results[idx] = {'cas': cas_from_llm, 'source': 'AI Cognitive'}
                    else:
                        # LLM tried but couldn't find CAS -> mark as "unknown"
                        cas_results[idx] = {'cas': 'unknown', 'source': 'AI Cognitive'}
        except Exception as e:
            logger.warning(f"Batch LLM CAS extraction failed: {e}")
            # If LLM call failed, mark all products as unknown
            for ten_hang_clean, indices in ten_hang_to_indices.items():
                for idx in indices:
                    cas_results[idx] = {'cas': 'unknown', 'source': 'AI Cognitive'}
    
    # FINAL CHECK: Ensure ALL chemical items have CAS filled
    for idx in all_chemical_indices:
        if idx not in cas_results:
            cas_results[idx] = {'cas': 'unknown', 'source': 'AI Cognitive'}
    
    logger.info(f"CAS extraction complete: {len(cas_results)} results for {len(all_chemical_indices)} chemical items")
    
    # Pre-compute appendix matches for chemical items (from old 3.2 logic)
    for idx, item in enumerate(sorted_items):
        if _get_chemical_notes(item['hs_code']) != "Chemical":
            continue
        
        cas_info = cas_results.get(idx, {})
        cas_number = cas_info.get('cas')
        hs_code = item['hs_code']
        
        appendix_matches = []
        nguong_khoi_luong = ""
        
        # Check CAS against all appendices
        if cas_number:
            matches = check_cas_in_nd24_appendices(cas_number)
            for match in matches:
                appendix_matches.append({
                    'appendix': match['appendix'],
                    'name': match['name'],
                    'ten_chat': match['data'].get('ten_chat', ''),
                    'yeu_cau': match['data'].get('yeu_cau', ''),
                })
                # Check for Phụ lục IV (nguong_khoi_luong)
                if match['appendix'] == 'IV':
                    nguong_khoi_luong = match.get('nguong_khoi_luong', match['data'].get('nguong_khoi_luong', ''))
        
        # Check HS code against Phụ lục II.1 (banned chemicals)
        banned_match = check_hs_in_nd24_banned(hs_code)
        if banned_match:
            appendix_matches.append({
                'appendix': 'II.1',
                'name': 'Phụ lục II.1 - DANH MỤC HÓA CHẤT, KHOÁNG VẬT CẤM',
                'ten_chat': banned_match.get('ten_chat', ''),
                'yeu_cau': banned_match.get('yeu_cau', ''),
            })
        
        appendix_results[idx] = {
            'appendix_matches': appendix_matches,
            'nguong_khoi_luong': nguong_khoi_luong,
        }
    
    # Calculate actual max_appendix_count from data (minimum 1 if there are any chemical items)
    actual_max_appendix = 0
    has_nguong_khoi_luong = False
    for result in appendix_results.values():
        matches_count = len(result.get('appendix_matches', []))
        if matches_count > actual_max_appendix:
            actual_max_appendix = matches_count
        if result.get('nguong_khoi_luong'):
            has_nguong_khoi_luong = True
    
    # Use actual count, minimum 1 if there are chemical items, 0 otherwise
    max_appendix_count = max(actual_max_appendix, 1) if appendix_results else 0
    
    logger.info(f"Sheet 3.1: Dynamic column counts - policy={max_policy_count}, appendix={max_appendix_count} (actual={actual_max_appendix}), has_nguong={has_nguong_khoi_luong}")
    
    # ============================================================================
    # STEP 6: Build headers - Correct order with separators
    # ============================================================================
    # Section 1: Dark headers (yellow text on black)
    headers = [
        ("", "empty"),           # A: Empty separator
        ("STT", "dark"),
        ("Mã HS", "dark"),
        ("Flow", "dark"),
        ("Transaction\nnotes", "dark"),
        ("Mã NPL/SP", "dark"),
        ("Tên hàng", "dark"),
        ("Chemical\nnotes", "dark"),
        ("Mã loại hình", "dark"),
        ("Số TK", "dark"),
        ("Ngày ĐK", "dark"),
        ("Sum of Tổng\nsố lượng", "dark"),
        ("Đơn vị tính", "dark"),
        # Section 2: Separator + dark style cols (&, Exclusion, Reason)
        ("", "empty"),           # Empty separator
        ("&", "dark"),
        ("Exclusion", "dark"),
        ("Reason", "dark"),
        # Section 3: Yellow style cols (TRAIN ref, VN Tariff ref)
        ("United Nation\n(TRAIN)'s\nNTM ref", "yellow"),
        ("VN Tariff\nSchedule's\nNTM ref", "yellow"),
        # Section 4: Red style (NTM for chemical, CAS) - NO separator before this
        ("NTM for\nchemical", "red"),
        ("CAS No.", "red"),
        ("CAS sources", "red"),
    ]
    
    # Section 5: Measure groups (yellow style) - separator before EACH group
    for i in range(1, max_policy_count + 1):
        headers.append(("", "empty"))  # Separator before each Measure group
        headers.extend([
            (f"Measure {i}", "yellow"),
            (f"Client's\nfulfilment {i}\n(if any)", "yellow"),
            (f"Assessment {i}", "yellow"),
            (f"Flag {i}", "yellow"),
        ])
    
    # Section 6: Chemical measure groups (red style) - separator before EACH group
    for i in range(1, max_appendix_count + 1):
        headers.append(("", "empty"))  # Separator before each Chemical measure group
        headers.extend([
            (f"Chemical\nmeasure {i}", "red"),
            (f"Client's\nfulfilment {i}-C\n(if any)", "red"),
            (f"Assessment {i}-C", "red"),
            (f"Flag {i}-C", "red"),
        ])
    
    # Extract header names and styles
    all_headers = [h[0] for h in headers]
    header_styles = [h[1] for h in headers]
    
    # Track indices by style
    empty_col_indices = [i+1 for i, s in enumerate(header_styles) if s == "empty"]
    dark_cols = [i+1 for i, s in enumerate(header_styles) if s == "dark"]
    yellow_cols = [i+1 for i, s in enumerate(header_styles) if s == "yellow"]
    red_cols = [i+1 for i, s in enumerate(header_styles) if s == "red"]
    
    # Column widths matching header order
    column_widths = []
    for i, (name, style) in enumerate(headers):
        if style == "empty":
            column_widths.append(2)
        elif name == "STT":
            column_widths.append(8)
        elif name == "Mã HS":
            column_widths.append(12)
        elif name == "Flow":
            column_widths.append(10)
        elif "Transaction" in name:
            column_widths.append(18)
        elif name == "Mã NPL/SP":
            column_widths.append(20)
        elif name == "Tên hàng":
            column_widths.append(50)
        elif "Chemical\nnotes" in name:
            column_widths.append(15)
        elif name == "Mã loại hình":
            column_widths.append(15)
        elif name == "Số TK":
            column_widths.append(15)
        elif name == "Ngày ĐK":
            column_widths.append(12)
        elif "Sum of" in name:
            column_widths.append(15)
        elif name == "Đơn vị tính":
            column_widths.append(12)
        elif name == "&":
            column_widths.append(25)
        elif name == "Exclusion":
            column_widths.append(15)
        elif name == "Reason":
            column_widths.append(20)
        elif "TRAIN" in name:
            column_widths.append(15)
        elif "VN Tariff" in name:
            column_widths.append(50)
        elif "NTM for" in name:
            column_widths.append(15)
        elif name == "CAS No.":
            column_widths.append(15)
        elif name == "CAS sources":
            column_widths.append(15)
        elif "Measure" in name or "Chemical\nmeasure" in name:
            column_widths.append(30)
        elif "Ngưỡng" in name:
            column_widths.append(22)
        elif "Flag" in name:
            column_widths.append(12)
        elif "Trains" in name:
            column_widths.append(15)
        else:
            column_widths.append(15)  # Default for Client's fulfilment, Assessment
    
    RED_FILL = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    RED_FONT = Font(name="Arial", bold=True, size=10, color="C4C4CD")  # Gray text on red
    
    # Row 1: Headers with correct styles
    for col_idx, (header, style) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        if style == "empty":
            cell.border = NO_BORDER
        elif style == "dark":
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
        elif style == "red":
            cell.font = RED_FONT
            cell.fill = RED_FILL
            cell.alignment = NEW_COL_HEADER_ALIGNMENT
            cell.border = THIN_BORDER
        else:  # yellow
            cell.font = NEW_COL_HEADER_FONT
            cell.fill = NEW_COL_HEADER_FILL
            cell.alignment = NEW_COL_HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Find key column indices from headers
    ampersand_col = next((i+1 for i, (n, _) in enumerate(headers) if n == "&"), 15)
    train_col_idx = next((i+1 for i, (n, _) in enumerate(headers) if "TRAIN" in n), 18)
    vn_tariff_col_idx = next((i+1 for i, (n, _) in enumerate(headers) if "VN Tariff" in n), 19)
    ntm_chemical_col = next((i+1 for i, (n, _) in enumerate(headers) if "NTM for" in n), 20)
    cas_no_col = next((i+1 for i, (n, _) in enumerate(headers) if n == "CAS No."), 21)
    cas_sources_col = next((i+1 for i, (n, _) in enumerate(headers) if n == "CAS sources"), 22)
    
    # Find Assessment and Flag column indices (both yellow and red versions)
    assessment_flag_cols = [i+1 for i, (n, _) in enumerate(headers) if "Assessment" in n or "Flag" in n]
    
    # Find Exclusion, Reason, and Client's fulfilment column indices for "To fill"
    exclusion_col = next((i+1 for i, (n, _) in enumerate(headers) if n == "Exclusion"), None)
    reason_col = next((i+1 for i, (n, _) in enumerate(headers) if n == "Reason"), None)
    clients_fulfilment_cols = [i+1 for i, (n, _) in enumerate(headers) if "Client's" in n and "fulfilment" in n]
    
    # Combine all columns that need "To fill" in filter row
    to_fill_cols = set(assessment_flag_cols + clients_fulfilment_cols)
    if exclusion_col:
        to_fill_cols.add(exclusion_col)
    if reason_col:
        to_fill_cols.add(reason_col)
    
    # Row 2: Filter row
    FORMULA_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")
    TO_FILL_FONT = Font(name="Arial", size=10, bold=True, color="FF0000")  # Bold, not italic
    
    for col_idx in range(1, len(all_headers) + 1):
        cell = ws.cell(row=2, column=col_idx, value="")
        if col_idx == ampersand_col:
            cell.value = "'=F3&\"/\"&J3"
            cell.font = FORMULA_FONT
        elif col_idx in to_fill_cols:
            cell.value = "To fill"
            cell.font = TO_FILL_FONT
        if col_idx not in empty_col_indices:
            cell.border = THIN_BORDER
    
    ws.row_dimensions[2].height = 12
    
    # ============================================================================
    # STEP 7: Write data rows starting at row 3
    # ============================================================================
    # Write data rows - STT already calculated above (same HS code = same STT)
    for row_idx, item in enumerate(sorted_items, 3):
        idx = row_idx - 3  # 0-based index
        
        # Get values
        hs_code = item['hs_code']
        hs_code_6 = item['hs_code_6'] or hs_code[:6] if hs_code else ""
        transaction_notes = _get_transaction_notes(item['ma_hieu_ptvc'])
        chemical_notes = _get_chemical_notes(hs_code)
        
        # STT: same HS code = same STT (show on every row)
        stt_value = hs_code_to_stt.get(hs_code, "") if hs_code else ""
        
        # Get commodity policy (from old 3.1 logic)
        policy_full = get_commodity_policy(hs_code)
        policies = []
        if policy_full:
            policies = [p.strip() for p in policy_full.split(';') if p.strip()]
        
        # CAS and appendix info for chemical items
        cas_info = cas_results.get(idx, {})
        cas_number = cas_info.get('cas', '')
        cas_source = cas_info.get('source', '')
        app_result = appendix_results.get(idx, {})
        appendix_matches = app_result.get('appendix_matches', [])
        nguong_kl = app_result.get('nguong_khoi_luong', '')
        
        # NTM for chemical - get appendix info from ND24 database (full names with descriptions)
        # Appendix descriptions from NĐ24
        APPENDIX_DESCRIPTIONS = {
            "I": "Phụ lục I - Danh mục hóa chất cơ bản thuộc lĩnh vực công nghiệp hóa chất trọng điểm",
            "II": "Phụ lục II - Danh mục hóa chất sản xuất, kinh doanh có điều kiện",
            "III": "Phụ lục III - Danh mục hóa chất cần kiểm soát đặc biệt (cần giấy phép)",
            "IV": "Phụ lục IV - Danh mục hóa chất phải xây dựng kế hoạch phòng ngừa, ứng phó sự cố",
            "II.1": "Phụ lục II.1 - Danh mục hóa chất, khoáng vật cấm",
        }
        ntm_for_chemical = ""
        if cas_number and chemical_notes == "Chemical":
            appendices = get_chemical_appendix_info(cas_number)
            if appendices:
                # Full appendix names with descriptions, separated by ";"
                appendix_full_names = []
                for app in sorted(appendices):
                    desc = APPENDIX_DESCRIPTIONS.get(app, f"Phụ lục {app}")
                    appendix_full_names.append(desc)
                ntm_for_chemical = f"NĐ24: {'; '.join(appendix_full_names)}"
            
            # Check for special control chemicals (warning marker)
            has_special = any(m['appendix'] in ('III', 'II.1') for m in appendix_matches)
            if has_special:
                cas_number = f"{cas_number} ⚠️"
        
        # Ampersand concatenation
        ampersand_val = f"{item['ma_npl_sp']}/{item['so_tk']}"
        
        # TRAIN link
        train_link = item.get('train_link', '')
        
        # Build row data matching header order exactly (with separators)
        row_data = [
            "",                              # A: Empty separator
            stt_value,                       # B: STT
            item['hs_code'],                 # C: Mã HS
            item['flow'],                    # D: Flow
            transaction_notes,               # E: Transaction notes
            item['ma_npl_sp'],               # F: Mã NPL/SP
            item['ten_hang'],                # G: Tên hàng
            chemical_notes,                  # H: Chemical notes
            item['ma_loai_hinh'],            # I: Mã loại hình
            item['so_tk'],                   # J: Số TK
            item['ngay_dk'],                 # K: Ngày ĐK
            item['tong_so_luong'],           # L: Sum of Tổng số lượng
            item['don_vi_tinh'],             # M: Đơn vị tính
            # Section 2: Separator + dark style columns
            "",                              # N: Empty separator
            ampersand_val,                   # O: &
            "",                              # P: Exclusion
            "",                              # Q: Reason
            # Section 3: Yellow style columns
            "",                              # R: United Nation (TRAIN)'s NTM ref
            policy_full,                     # S: VN Tariff Schedule's NTM ref
            # Section 4: Red style columns (NO separator)
            ntm_for_chemical if chemical_notes == "Chemical" else "",  # T: NTM for chemical
            cas_number if chemical_notes == "Chemical" else "",        # U: CAS No.
            cas_source if chemical_notes == "Chemical" else "",        # V: CAS sources
        ]
        
        # Section 5: Measure groups - separator before EACH group
        for i in range(max_policy_count):
            row_data.append("")  # Empty separator before each Measure group
            if i < len(policies):
                row_data.append(policies[i])  # Measure N
            else:
                row_data.append("")
            row_data.append("[To fill]")  # Client's fulfilment N
            row_data.append("[To fill]")  # Assessment N
            row_data.append("[To fill]")  # Flag N
        
        # Section 6: Chemical measure groups - separator before EACH group
        for i in range(max_appendix_count):
            row_data.append("")  # Empty separator before each Chemical measure group
            if chemical_notes == "Chemical" and i < len(appendix_matches):
                match = appendix_matches[i]
                policy_text = f"{match['name']}\n(Kèm theo Nghị định số 24/2026/NĐ-CP ngày 17 tháng 01 năm 2026 của Chính phủ)"
                row_data.append(policy_text)  # Chemical measure N
            else:
                row_data.append("")  # Empty Chemical measure
            
            # Client's fulfilment-C, Assessment-C, Flag-C
            if chemical_notes == "Chemical":
                row_data.append("[To fill]")  # Client's fulfilment N-C
                row_data.append("[To fill]")  # Assessment N-C
                row_data.append("[To fill]")  # Flag N-C
            else:
                row_data.append("")
                row_data.append("")
                row_data.append("")
        
        # Write cells
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            
            # Handle TRAIN hyperlink
            if col_idx == train_col_idx and train_link and train_link.startswith('http'):
                cell.value = "TRAIN link"
                cell.hyperlink = train_link
                cell.font = Font(name="Arial", size=10, color="0000FF", underline="single")
            elif value == "[To fill]":
                cell.font = ITALIC_FONT
            else:
                cell.font = CELL_FONT
            
            if col_idx in empty_col_indices:
                cell.border = NO_BORDER
            else:
                cell.border = THIN_BORDER
            
            if col_idx == 2:  # STT
                cell.alignment = CENTER_ALIGNMENT
            elif col_idx == 12:  # Sum of Tổng số lượng
                cell.alignment = NUMBER_ALIGNMENT
                if isinstance(value, (int, float)):
                    cell.number_format = '#,##0'
            else:
                cell.alignment = CELL_ALIGNMENT
    
    # ============================================================================
    # STEP 8: Add data validation (dropdown lists)
    # ============================================================================
    from openpyxl.worksheet.datavalidation import DataValidation
    
    # Find Exclusion column index
    exclusion_col_idx = next((i+1 for i, (n, _) in enumerate(headers) if n == "Exclusion"), 16)
    exclusion_col_letter = get_column_letter(exclusion_col_idx)
    exclusion_validation = DataValidation(
        type="list",
        formula1='"Excluded,Not excluded"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Invalid Input",
        error="Please select 'Excluded' or 'Not excluded'"
    )
    if len(sorted_items) > 0:
        exclusion_validation.add(f"{exclusion_col_letter}3:{exclusion_col_letter}{2 + len(sorted_items)}")
        ws.add_data_validation(exclusion_validation)
    
    # Set column widths
    for col_idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Set header row height
    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT
    
    # Add auto filter on row 2
    last_row = 2 + len(sorted_items)
    last_col = len(all_headers)
    ws.auto_filter.ref = f"B2:{get_column_letter(last_col)}{last_row}"
    
    # Hide filter on empty separator columns
    for empty_col in empty_col_indices:
        if empty_col > 1:  # Skip first column A
            col_id = empty_col - 2  # 0-based from B
            try:
                ws.auto_filter.filterColumn.append(FilterColumn(colId=col_id, hiddenButton=True))
            except Exception:
                pass
    
    # Freeze panes - freeze after dark section (column 13 = Đơn vị tính)
    # Dark section: A(empty), B-M (STT through Đơn vị tính) = 13 columns
    freeze_col = 14  # Column N (empty separator before yellow section)
    ws.freeze_panes = f"{get_column_letter(freeze_col)}3"
    
    logger.info(f"Created 3.1 sheet with {len(sorted_items)} rows (same as VNACCs, no merge)")
    logger.info(f"flag_31_mapping: {len(flag_31_mapping)} entries, exclusion_31_mapping: {len(exclusion_31_mapping)} entries")
    
    return flag_31_mapping, exclusion_31_mapping, max_appendix_count


def _create_hs_to_collect_sheet(
    wb: Workbook,
    hs_consistency: HSConsistencyReport,
) -> None:
    """Create 1.2 sheet (formerly HS Inconsistency to collect).
    """
    ws_summary = wb.create_sheet("1.2")
    apply_sheet_settings(ws_summary)
    
    # Headers with empty separator columns
    # All headers (yellow on black)
    headers_part1 = [
        "", "STT", "Mã NPL/SP", "Các mã HS đã kê khai trong giai\nđoạn rà soát",
        "Tên thương phẩm", "Tên khoa học/ Tên kỹ\nthuật", "Mô tả",
        "Công dụng/ chức\nnăng", "Cấu tạo/ thành phần", "Chất liệu", "Thông số kỹ thuật"
    ]
    # GIR section headers (also yellow on black)
    headers_part2 = [
        "", "GIR", "WCO HS\nExplanatory\nNotes 2022", "WCO\nCompendium\nof\nClassification\nOpinions 2022",
        "SEN 2022", "International\nHS Ruling", "Public HS\ndatabase", "Conclusion"
    ]
    
    all_headers = headers_part1 + headers_part2
    
    # Empty separator columns
    empty_cols = [1, 12]  # Column A and column L (separator between parts)
    
    # Row 1: Headers (all yellow on black)
    for col_idx, header in enumerate(all_headers, 1):
        cell = ws_summary.cell(row=1, column=col_idx, value=header)
        if col_idx in empty_cols:
            cell.border = NO_BORDER
        else:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER
    
    # Row 2: Filter row (empty)
    for col_idx in range(1, len(all_headers) + 1):
        cell = ws_summary.cell(row=2, column=col_idx, value="")
        if col_idx not in empty_cols:
            cell.border = THIN_BORDER
    
    # Get Top 10 data
    top_10_data = {}
    if hs_consistency and hs_consistency.items:
        for item in hs_consistency.items:
            if item.impact_refer and item.ma_npl_sp:
                if item.ma_npl_sp not in top_10_data:
                    top_10_data[item.ma_npl_sp] = {'hs_codes': set(), 'impact_refer': item.impact_refer}
                if item.ma_hs:
                    top_10_data[item.ma_npl_sp]['hs_codes'].add(item.ma_hs)
    
    sorted_top_10 = sorted(
        top_10_data.items(),
        key=lambda x: int(x[1]['impact_refer'].replace('IP', '')) if x[1]['impact_refer'] else 999
    )

    # Keep only Top 10 items
    sorted_top_10 = sorted_top_10[:10]

    # Write data rows starting at row 3
    for row_idx, (npl_sp, data) in enumerate(sorted_top_10, 3):
        stt = row_idx - 2
        hs_codes_str = ", ".join(sorted(data['hs_codes']))

        # Column data
        row_data = [
            "",                          # 1: Empty separator
            stt,                         # 2: STT
            npl_sp,                      # 3: Mã NPL/SP
            hs_codes_str,                # 4: Các mã HS
            "[the Company to fill]",     # 5: Tên thương phẩm
            "[the Company to fill]",     # 6: Tên khoa học
            "[the Company to fill]",     # 7: Mô tả
            "[the Company to fill]",     # 8: Công dụng
            "[the Company to fill]",     # 9: Cấu tạo
            "[the Company to fill]",     # 10: Chất liệu
            "[the Company to fill]",     # 11: Thông số kỹ thuật
            "",                          # 12: Empty separator
            "",                          # 13: GIR
            "",                          # 14: WCO HS Explanatory
            "",                          # 15: WCO Compendium
            "",                          # 16: SEN 2022
            "",                          # 17: International HS Ruling
            "",                          # 18: Public HS database
            "",                          # 19: Conclusion
        ]

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_summary.cell(row=row_idx, column=col_idx, value=value)

            # Use italic font for "[the Company to fill]"
            if value == "[the Company to fill]":
                cell.font = ITALIC_FONT
            else:
                cell.font = CELL_FONT

            if col_idx in empty_cols:
                cell.border = NO_BORDER
            else:
                cell.border = THIN_BORDER

            if col_idx == 2:  # STT
                cell.alignment = CENTER_ALIGNMENT
            else:
                cell.alignment = CELL_ALIGNMENT

    # Column widths
    column_widths = [2, 8, 15, 35, 25, 25, 20, 20, 25, 20, 25, 2, 10, 18, 18, 12, 15, 15, 12]
    for col_idx, width in enumerate(column_widths, 1):
        ws_summary.column_dimensions[get_column_letter(col_idx)].width = width

    # Set header row height
    ws_summary.row_dimensions[1].height = HEADER_ROW_HEIGHT

    # Add auto filter on row 2 (filter row) - all columns with headers
    last_row = 2 + len(sorted_top_10)
    ws_summary.auto_filter.ref = f"B2:S{last_row}"  # Columns B-S (skip empty col A)

    # Hide filter dropdown on empty separator column L (colId=10, 0-based from B)
    ws_summary.auto_filter.filterColumn.append(FilterColumn(colId=10, hiddenButton=True))

    # Freeze at M3 (columns A-L and rows 1-2 frozen, including filter row)
    ws_summary.freeze_panes = "L3"


def _reorder_sheets(wb: Workbook, input_sheet_title: str) -> None:
    """Reorder sheets to desired order"""
    desired_order = [
        "Table of Contents",
        "1.0",
        input_sheet_title,
        "1.1",
        "1.2",
        "2.1",
        "2.2a",
        "2.3",
        "3.1",
        "NĐ24.2026",  # CHC reference sheet at the end
    ]
    
    for idx, sheet_name in enumerate(desired_order):
        if sheet_name in wb.sheetnames:
            current_idx = wb.sheetnames.index(sheet_name)
            if current_idx != idx:
                ws = wb[sheet_name]
                wb.move_sheet(ws, offset=idx - current_idx)


def _create_chc_reference_sheet(wb: Workbook) -> bool:
    """Create CHC reference sheet (NĐ24.2026) from source file
    
    Copies the chemical regulation reference sheet from 
    'CHC-Danh mục hóa chất cần GP_Khai báo.xlsx'
    
    Args:
        wb: Target workbook to add sheet to
        
    Returns:
        True if sheet was created successfully, False otherwise
    """
    from openpyxl import load_workbook as load_wb_source
    from openpyxl.utils import get_column_letter
    from copy import copy
    
    # Find the source file
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'CHC-Danh mục hóa chất cần GP_Khai báo.xlsx'),
        os.path.join(os.path.dirname(__file__), '..', 'data', 'CHC-Danh mục hóa chất cần GP_Khai báo.xlsx'),
        'report_service/data/CHC-Danh mục hóa chất cần GP_Khai báo.xlsx',
    ]
    
    source_path = None
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            source_path = abs_path
            break
    
    # Also try finding by listing directory
    if source_path is None:
        for path in possible_paths:
            dir_path = os.path.dirname(os.path.abspath(path))
            if os.path.exists(dir_path):
                for f in os.listdir(dir_path):
                    if 'CHC' in f and f.endswith('.xlsx'):
                        source_path = os.path.join(dir_path, f)
                        break
            if source_path:
                break
    
    if source_path is None:
        logger.warning("Could not find CHC reference file (CHC-Danh mục hóa chất cần GP_Khai báo.xlsx)")
        return False
    
    try:
        logger.info(f"Loading CHC reference sheet from: {source_path}")
        source_wb = load_wb_source(source_path, read_only=False, data_only=True)
        source_ws = source_wb['NĐ24.2026']
        
        # Create new sheet in target workbook
        target_ws = wb.create_sheet("NĐ24.2026")
        apply_sheet_settings(target_ws)
        
        # Copy cell values, styles, and merged cells
        for row_idx, row in enumerate(source_ws.iter_rows(), 1):
            for col_idx, cell in enumerate(row, 1):
                target_cell = target_ws.cell(row=row_idx, column=col_idx)
                
                # Copy value
                target_cell.value = cell.value
                
                # Copy style if cell has one
                if cell.has_style:
                    target_cell.font = copy(cell.font)
                    target_cell.fill = copy(cell.fill)
                    target_cell.border = copy(cell.border)
                    target_cell.alignment = copy(cell.alignment)
                    target_cell.number_format = cell.number_format
                    target_cell.protection = copy(cell.protection)
        
        # Copy column widths
        for col_letter, col_dim in source_ws.column_dimensions.items():
            target_ws.column_dimensions[col_letter].width = col_dim.width
            if col_dim.hidden:
                target_ws.column_dimensions[col_letter].hidden = True
        
        # Copy row heights
        for row_num, row_dim in source_ws.row_dimensions.items():
            target_ws.row_dimensions[row_num].height = row_dim.height
            if row_dim.hidden:
                target_ws.row_dimensions[row_num].hidden = True
        
        # Copy merged cells
        for merged_range in source_ws.merged_cells.ranges:
            target_ws.merge_cells(str(merged_range))
        
        # Set sheet tab color (green for reference)
        target_ws.sheet_properties.tabColor = "00B050"
        
        source_wb.close()
        logger.info(f"Successfully created CHC reference sheet (NĐ24.2026)")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create CHC reference sheet: {e}")
        return False


# Import input sheet creation functions from separate module to avoid circular imports
from .input_sheet import _create_input_sheet_optimized, _create_input_from_dataframe

