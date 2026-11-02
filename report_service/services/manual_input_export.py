"""Service for manual input Excel export."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Dict, List

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import FilterColumn

from report_service.utils.excel_processor.constants import (
	CELL_ALIGNMENT,
	CELL_FONT,
	CENTER_ALIGNMENT,
	HEADER_ALIGNMENT,
	HEADER_FILL,
	HEADER_FONT,
	LINK_FONT,
	NO_BORDER,
	THIN_BORDER,
)

URL_PATTERN = re.compile(r"https?://[^\s\]\)\"'>]+")
INVALID_XML_CHARS_PATTERN = re.compile(
	r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]"
)
EXCEL_CELL_MAX_LENGTH = 32767

HEADER_KEYS: List[str] = [
	"gri",
	"wco_explanatory_notes",
	"wco_compendium",
	"sen_2022",
	"international_hs_ruling",
	"public_hs_database",
	"conclusion",
]

HEADERS_PART1 = [
	"",
	"STT",
	"Tên thương phẩm",
	"Tên khoa học/ Tên kỹ\nthuật",
	"Mô tả",
	"Công dụng/ chức\nnăng",
	"Cấu tạo/ thành phần",
	"Chất liệu",
	"Thông số kỹ thuật",
]

HEADERS_PART2 = [
	"",
	"GIR",
	"WCO HS\nExplanatory\nNotes 2022",
	"WCO\nCompendium\nof\nClassification\nOpinions 2022",
	"SEN 2022",
	"International\nHS Ruling",
	"Public HS\ndatabase",
	"Conclusion",
]

EMPTY_COLS = {1, 10}

COLUMN_WIDTHS = [
	2,
	8,
	25,
	25,
	20,
	20,
	25,
	20,
	25,
	2,
	12,
	42,
	42,
	36,
	48,
	48,
	38,
]

HEADER_ROW_HEIGHT = 80
ITALIC_FONT = Font(name="Arial", italic=True, size=10)


def _extract_first_url(value: str) -> str | None:
	match = URL_PATTERN.search(value or "")
	return match.group(0) if match else None


def _sanitize_excel_text(value: str) -> str:
	if not value:
		return ""
	cleaned = INVALID_XML_CHARS_PATTERN.sub("", value)
	if len(cleaned) > EXCEL_CELL_MAX_LENGTH:
		return cleaned[: EXCEL_CELL_MAX_LENGTH - 15] + "\n[TRUNCATED]"
	return cleaned


def build_manual_input_export(values: Dict[str, str]) -> bytes:
	"""Build the manual input export workbook and return its bytes."""
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "1.2"
	worksheet.sheet_view.showGridLines = False
	worksheet.sheet_view.zoomScale = 80
	worksheet.sheet_properties.tabColor = "000000"
	worksheet.column_dimensions["A"].width = 2

	all_headers = HEADERS_PART1 + HEADERS_PART2

	# Row 1: Headers
	for col_idx, header in enumerate(all_headers, 1):
		cell = worksheet.cell(row=1, column=col_idx, value=header)
		if col_idx in EMPTY_COLS:
			cell.border = NO_BORDER
		else:
			cell.font = HEADER_FONT
			cell.fill = HEADER_FILL
			cell.alignment = HEADER_ALIGNMENT
			cell.border = THIN_BORDER

	# Row 2: Filter row
	for col_idx in range(1, len(all_headers) + 1):
		cell = worksheet.cell(row=2, column=col_idx, value="")
		if col_idx not in EMPTY_COLS:
			cell.border = THIN_BORDER

	# Row 3: Data
	input_values = {
		"product_name": _sanitize_excel_text(
			str(values.get("product_name", "") or "")
		),
		"science_name": _sanitize_excel_text(
			str(values.get("science_name", "") or "")
		),
		"product_description": _sanitize_excel_text(
			str(values.get("product_description", "") or "")
		),
		"function": _sanitize_excel_text(
			str(values.get("function", "") or "")
		),
		"structure": _sanitize_excel_text(
			str(values.get("structure", "") or "")
		),
		"material": _sanitize_excel_text(
			str(values.get("material", "") or "")
		),
		"specifications": _sanitize_excel_text(
			str(values.get("specifications", "") or "")
		),
	}

	row_data = [
		"",  # 1: Empty separator
		1,  # 2: STT
		input_values["product_name"],  # 3: Tên thương phẩm
		input_values["science_name"],  # 4: Tên khoa học
		input_values["product_description"],  # 5: Mô tả
		input_values["function"],  # 6: Công dụng
		input_values["structure"],  # 7: Cấu tạo
		input_values["material"],  # 8: Chất liệu
		input_values["specifications"],  # 9: Thông số kỹ thuật
		"",  # 10: Empty separator
		_sanitize_excel_text(str(values.get(HEADER_KEYS[0], "") or "")),  # 11: GIR
		_sanitize_excel_text(str(values.get(HEADER_KEYS[1], "") or "")),  # 12 : WCO Explanatory Notes
		_sanitize_excel_text(str(values.get(HEADER_KEYS[2], "") or "")),  # 13 : WCO Compendium
		_sanitize_excel_text(str(values.get(HEADER_KEYS[3], "") or "")),  # 14 : SEN 2022
		_sanitize_excel_text(str(values.get(HEADER_KEYS[4], "") or "")),  # 15 : International HS Ruling
		_sanitize_excel_text(str(values.get(HEADER_KEYS[5], "") or "")),  # 16 : Public HS database
		_sanitize_excel_text(str(values.get(HEADER_KEYS[6], "") or "")),  # 17 : Conclusion
	]

	for col_idx, value in enumerate(row_data, 1):
		cell = worksheet.cell(row=3, column=col_idx, value=value)
		if value == "[the Company to fill]":
			cell.font = ITALIC_FONT
		else:
			cell.font = CELL_FONT

		if col_idx >= 11 and isinstance(value, str) and value:
			sanitized_value = _sanitize_excel_text(value)
			first_url = _extract_first_url(sanitized_value)
			if first_url and sanitized_value.strip() == first_url:
				cell.value = sanitized_value
				cell.hyperlink = first_url
				cell.font = LINK_FONT
			else:
				cell.value = sanitized_value

		if col_idx in EMPTY_COLS:
			cell.border = NO_BORDER
		else:
			cell.border = THIN_BORDER
		if col_idx == 2:
			cell.alignment = CENTER_ALIGNMENT
		else:
			cell.alignment = CELL_ALIGNMENT

	for col_idx, width in enumerate(COLUMN_WIDTHS, 1):
		worksheet.column_dimensions[get_column_letter(col_idx)].width = width

	worksheet.row_dimensions[1].height = HEADER_ROW_HEIGHT
	worksheet.row_dimensions[3].height = 340
	worksheet.auto_filter.ref = "B2:Q3"
	worksheet.auto_filter.filterColumn.append(FilterColumn(colId=8, hiddenButton=True))
	worksheet.freeze_panes = "J3"

	buffer = BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()
