"""Process E-tariff dataset input files and build Excel outputs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
import sys
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import FilterColumn

from report_service.utils.excel_processor.constants import (
	CELL_ALIGNMENT,
	CELL_FONT,
	CENTER_ALIGNMENT,
	HEADER_ALIGNMENT,
	HEADER_FILL,
	HEADER_FONT,
	NO_BORDER,
	THIN_BORDER,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
	sys.path.insert(0, REPO_ROOT)

from classifier_service.api.v1.schemas import ProductQuery
from classifier_service.services.classification_service import get_classification
from pydantic import ValidationError
from crawl_service.core.models import ProductCrawlQuery
from crawl_service.core.orchestrator import CrawlOrchestrator
from crawl_service.core.hs_database_orchestrator import HSCodeDatabaseOrchestrator
from hs_analyzer_service.api.v1.schemas import HSCodeCandidate, ProductInfo
from hs_analyzer_service.services.analyzer_service import analyze_hs_codes
from rag_service.core.service.hs_code_search import hscode_search
from report_service.utils.filename_validation import validate_dataset_filename
from shared.llm_error_utils import is_quota_error, quota_error_detail

logger = logging.getLogger(__name__)

DATASET_MAX_CONCURRENT = int(os.getenv("DATASET_MAX_CONCURRENT", "5"))


# Lazy-loaded lookup table for exact HS code -> metadata fallback.
_CODE_PAGE_INDEX: Optional[Dict[str, Dict[str, object]]] = None



HEADER_ALIASES = {
	# English dataset headers
	"commodityname": "product_name",
	"commoditydescription": "description",
	"function": "function",
	"scientifictechnicalname": "scientific_name",
	"structure": "structure",
	"material": "material",
	"specifications": "specifications",
	"otherinformation": "other_information",
	# Vietnamese CHC 1.2 headers
	"tenthuongpham": "product_name",
	"mota": "description",
	"congdungchucnang": "function",
	"tenkhoahoctenkythuat": "scientific_name",
	"cautaothanhphan": "structure",
	"chatlieu": "material",
	"thongsokythuat": "specifications",
	"thongtinkhac": "other_information",
	# Optional pass-through columns
	"nplproductcode": "npl_product_code",
	"manplsp": "npl_product_code",
	"declaredhscodesduringreviewperiod": "hs_codes_review",
	"cacmahsdakekhaitronggiaidoanrasoat": "hs_codes_review",
}

REQUIRED_FIELDS = {
	"product_name",
	"description",
	"function",
}

OPTIONAL_FIELDS = {
	"scientific_name",
	"structure",
	"material",
	"specifications",
	"other_information",
	"npl_product_code",
	"hs_codes_review",
}

COLUMN_ORDER = [
	"product_name",
	"scientific_name",
	"description",
	"function",
	"structure",
	"material",
	"specifications",
	"other_information"
]

OUTPUT_COLUMNS = [
	("gri", "GIR"),
	("wco_explanatory_notes", "WCO HS Explanatory Notes 2022"),
	("wco_compendium", "WCO Compendium of Classification Opinions 2022"),
	("sen_2022", "SEN 2022"),
	("international_hs_ruling", "International HS Ruling"),
	("public_hs_database", "Public HS database"),
	("conclusion", "Conclusion")
]

HEADERS_PART1_EN = [
	"",
	"No.",
	"NPL/Product Code",
	"Declared HS Codes During Review Period",
	"Commodity Name",
	"Scientific/Technical Name",
	"Commodity Description",
	"Function",
	"Structure",
	"Material",
	"Specifications",
]

HEADERS_PART1_VI = [
	"",
	"STT",
	"Mã NPL/SP",
	"Các mã HS đã kê khai trong giai đoạn rà soát",
	"Tên thương phẩm",
	"Tên khoa học/ Tên kỹ thuật",
	"Mô tả",
	"Công dụng/ chức năng",
	"Cấu tạo/ thành phần",
	"Chất liệu",
	"Thông số kỹ thuật",
]

HEADERS_PART2_EN = [
	"",
	"GIR",
	"WCO HS\nExplanatory\nNotes 2022",
	"WCO\nCompendium\nof\nClassification\nOpinions 2022",
	"SEN 2022",
	"International\nHS Ruling",
	"Public HS\ndatabase",
	"Conclusion",
]

HEADERS_PART2_VI = [
	"",
	"GIR",
	"WCO HS\nExplanatory\nNotes 2022",
	"WCO\nCompendium\nof\nClassification\nOpinions 2022",
	"SEN 2022",
	"International\nHS Ruling",
	"Public HS\ndatabase",
	"Conclusion",
]

EMPTY_COLS = {1, 12}

COLUMN_WIDTHS = [
	2,
	8,
	15,
	35,
	25,
	25,
	20,
	20,
	25,
	20,
	25,
	2,
	10,
	18,
	18,
	12,
	15,
	15,
	12,
]

HEADER_ROW_HEIGHT = 80
DATA_ROW_HEIGHT = 220
ITALIC_FONT = Font(name="Arial", italic=True, size=10)
BLOCK_SEPARATOR = "----------------------------------------"
INVALID_XML_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
EXCEL_CELL_MAX_LENGTH = 32767
TOP_CELL_ALIGNMENT = Alignment(horizontal="left", vertical="top", wrap_text=True)


@dataclass
class DatasetInputRow:
	source_index: int
	data: Dict[str, Any]


@dataclass
class DatasetRowResult:
	row_index: int
	source_index: int
	input_data: Dict[str, Any]
	wco: Dict[str, Any]
	compendium: List[Dict[str, Any]]
	asean: List[Dict[str, Any]]
	hs_ruling: Dict[str, Any]
	hs_database: Dict[str, Any]
	ai_conclusion: Dict[str, Any]
	ai_benchmark: List[Dict[str, Any]]
	errors: Dict[str, str]


def _normalize_header(value: Any) -> str:
	if value is None:
		return ""
	text = str(value).strip().lower()
	text = text.replace("đ", "d").replace("Đ", "d")
	text = unicodedata.normalize("NFKD", text)
	text = "".join(char for char in text if not unicodedata.combining(char))
	return "".join(char for char in text if char.isalnum())


def _safe_value(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, float) and pd.isna(value):
		return ""
	return str(value).strip()


def _is_na_text(value: str) -> bool:
	return value.strip().lower() == "n/a"


def _normalize_na(value: str) -> str:
	text = value.strip()
	if not text:
		return ""
	return "" if _is_na_text(text) else text


def _normalize_hs_code(code: Optional[str]) -> str:
	if not code:
		return ""
	return "".join(ch for ch in str(code) if ch.isdigit())


def _coerce_code_list(raw_codes: object) -> List[str]:
	if not raw_codes:
		return []
	if isinstance(raw_codes, str):
		return [raw_codes]
	if isinstance(raw_codes, (list, tuple, set)):
		return [str(code) for code in raw_codes if code is not None]
	return [str(raw_codes)]


def _get_code_page_index() -> Dict[str, Dict[str, object]]:
	global _CODE_PAGE_INDEX
	if _CODE_PAGE_INDEX is not None:
		return _CODE_PAGE_INDEX

	index: Dict[str, Dict[str, object]] = {}
	data_path = os.path.join(
		os.path.dirname(__file__),
		"..",
		"..",
		"data",
		"structured_subheadings_v2_all.json",
	)

	try:
		with open(data_path, "r", encoding="utf-8") as handle:
			payload = json.load(handle) or {}
	except Exception as exc:
		logger.warning("Failed to load subheading index: %s", exc)
		_CODE_PAGE_INDEX = {}
		return _CODE_PAGE_INDEX

	subheadings = payload.get("subheadings", []) if isinstance(payload, dict) else []
	for entry in subheadings:
		if not isinstance(entry, dict):
			continue
		pages = entry.get("pages") or []
		if isinstance(pages, (int, str)):
			pages = [pages]
		codes = _coerce_code_list(entry.get("code"))
		chapter = entry.get("chapter") or entry.get("chapter_en") or entry.get("chapter_vi")
		heading = entry.get("heading") or entry.get("heading_en") or entry.get("heading_vi")
		for code in codes:
			normalized = _normalize_hs_code(code)
			if not normalized:
				continue
			index[normalized] = {
				"source_pages": pages if isinstance(pages, list) else [],
				"chapter": chapter,
				"heading": heading,
				"file_name": "structured_subheadings_v2_all.json",
				"file_path": data_path,
			}

	_CODE_PAGE_INDEX = index
	return _CODE_PAGE_INDEX


def _lookup_metadata_by_code(subheading_id: Optional[str]) -> Optional[Dict[str, object]]:
	normalized = _normalize_hs_code(subheading_id)
	if not normalized:
		return None
	index = _get_code_page_index()
	return index.get(normalized)


def _extract_source_pages(metadata: Any) -> List[str]:
	if not isinstance(metadata, dict):
		return []
	pages = metadata.get("pages") or metadata.get("source_pages") or metadata.get("page") or []
	if isinstance(pages, (int, str)):
		return [str(pages)]
	if isinstance(pages, list):
		return [str(page) for page in pages if page is not None]
	return []


def _resolve_source_pages(metadata: Any, hs_code: Optional[str]) -> List[str]:
	pages = _extract_source_pages(metadata)
	if pages:
		return pages
	lookup = _lookup_metadata_by_code(hs_code)
	return [str(page) for page in (lookup or {}).get("source_pages", [])]

def _strip_company_placeholder(value: str) -> str:
	if not value:
		return ""
	if value.strip().lower() == "[the company to fill]":
		return ""
	return value


def _normalize_numeric_text(value: str) -> str:
	text = value.strip()
	if not text:
		return text
	if "," in text or " " in text:
		return text
	if re.fullmatch(r"\d+\.0+", text):
		return text.split(".", 1)[0]
	return text


def _read_excel(content: bytes, filename: str, header: Optional[int]) -> pd.DataFrame:
	extension = os.path.splitext(filename or "")[1].lower()
	engine = "pyxlsb" if extension == ".xlsb" else None
	return pd.read_excel(BytesIO(content), header=header, engine=engine)


def parse_dataset_rows(
	content: bytes,
	filename: str
) -> List[DatasetInputRow]:
	validate_dataset_filename(filename)
	dataframe = _read_excel(content, filename, header=0)
	columns = [_normalize_header(col) for col in dataframe.columns]
	normalized_to_original = {}
	for original_col in dataframe.columns:
		normalized = _normalize_header(original_col)
		if normalized and normalized not in normalized_to_original:
			normalized_to_original[normalized] = original_col

	logger.info(
		"Dataset headers normalized=%s",
		sorted(normalized_to_original.keys()),
	)

	canonical_to_original = {}
	for normalized, original_col in normalized_to_original.items():
		canonical = HEADER_ALIASES.get(normalized)
		if canonical and canonical not in canonical_to_original:
			canonical_to_original[canonical] = original_col

	if "npl_product_code" not in canonical_to_original:
		for normalized, original_col in normalized_to_original.items():
			if any(token in normalized for token in ("nplproductcode", "manplsp", "nplsp")):
				canonical_to_original["npl_product_code"] = original_col
				break

	if "hs_codes_review" not in canonical_to_original:
		for normalized, original_col in normalized_to_original.items():
			if any(
				token in normalized
				for token in (
					"declaredhscodesduringreview",
					"declaredhscodesduringreviewperiod",
					"hscodesduringreviewperiod",
					"hscodesduringreview",
					"cacmahsdakekhaitronggiaidoanrasoat",
					"mahsdakekhaitronggiaidoanrasoat",
				)
			) or (
				"mahs" in normalized
				and ("rasoat" in normalized or "review" in normalized)
			):
				canonical_to_original["hs_codes_review"] = original_col
				break

	missing_fields = [
		field for field in REQUIRED_FIELDS if field not in canonical_to_original
	]
	if missing_fields:
		present_headers = ", ".join(
			[str(col).strip() for col in dataframe.columns if str(col).strip()]
		)
		raise ValueError(
			"Invalid column headers. Required fields: Commodity Name (Tên thương phẩm), "
			"Commodity Description (Mô tả), Function (Công dụng/ chức năng). "
			"Optional fields: Scientific/Technical Name, Structure, Material, "
			"Specifications, Other information. Detected headers: "
			+ present_headers
		)

	rows: List[DatasetInputRow] = []
	row_errors: List[str] = []
	for index, row in dataframe.iterrows():
		mapped = {}
		na_fields: set = set()  # track fields explicitly set to N/A by the user
		for key in REQUIRED_FIELDS.union(OPTIONAL_FIELDS):
			original_col = canonical_to_original.get(key)
			if original_col is not None:
				raw = _safe_value(row.get(original_col))
				if _is_na_text(raw):
					na_fields.add(key)
				# For required fields, preserve "N/A" so LLM receives it
				# For optional fields, normalize N/A to empty string
				if key in REQUIRED_FIELDS:
					value = raw if _is_na_text(raw) else _normalize_na(raw)
				else:
					value = _normalize_na(raw)
				if key in {"npl_product_code", "hs_codes_review"}:
					value = _normalize_numeric_text(value)
				mapped[key] = value
		for key in COLUMN_ORDER:
			mapped.setdefault(key, "")

		has_any_value = any(
			(mapped.get(key) or "").strip()
			for key in REQUIRED_FIELDS.union(OPTIONAL_FIELDS)
		)
		if not has_any_value:
			continue

		missing_required = []
		for key in REQUIRED_FIELDS:
			if not (mapped.get(key) or "").strip():
				missing_required.append(key)
		# If product_name is present but other required fields are blank,
		# treat blank required fields as "N/A" rather than rejecting the row.
		# The LLM will handle missing information gracefully.
		if missing_required and (mapped.get("product_name") or "").strip():
			for key in missing_required:
				mapped[key] = "N/A"
			missing_required = []
		if missing_required:
			excel_row = index + 2  # header row is 1
			row_errors.append(
				f"Row {excel_row}: missing required fields: {', '.join(missing_required)}"
			)
			continue

		if any(mapped.get(key) for key in COLUMN_ORDER):
			rows.append(DatasetInputRow(source_index=index, data=mapped))

	if row_errors:
		preview = "; ".join(row_errors[:10])
		raise ValueError(
			"Invalid dataset rows (required fields must be non-empty). "
			f"Examples: {preview}"
		)

	return rows


def _build_candidate_list(
	compendium: Sequence[Dict[str, Any]],
	asean: Sequence[Dict[str, Any]],
	hs_database: Dict[str, Any]
) -> List[HSCodeCandidate]:
	counts: Dict[str, int] = {}

	for entry in compendium or []:
		for code in entry.get("subheading_ids") or []:
			counts[code] = counts.get(code, 0) + 1

	for entry in asean or []:
		for code in entry.get("subheading_ids") or []:
			counts[code] = counts.get(code, 0) + 1

	results = _extract_hs_database_results(hs_database)
	for result in results:
		for source in result.get("sources", []) or []:
			for hs_code in source.get("hs_codes", []) or []:
				code = hs_code.get("hs_code")
				count = hs_code.get("count", 0)
				if code:
					counts[code] = counts.get(code, 0) + int(count)

	candidates = [
		HSCodeCandidate(hs_code=code, number_of_occurrences=count)
		for code, count in counts.items()
	]

	candidates.sort(key=lambda item: item.number_of_occurrences, reverse=True)
	return candidates[:10]


def _extract_hs_database_results(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
	if not isinstance(payload, dict):
		return []

	results = payload.get("results")
	if isinstance(results, list):
		return results

	nested = payload.get("result")
	if isinstance(nested, dict) and isinstance(nested.get("results"), list):
		return nested.get("results") or []

	return []


def _normalize_wco_result(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
	if not isinstance(payload, dict):
		return {}

	classification_keys = {
		"section_classification",
		"chapter_classification",
		"heading_classification",
		"subheading_classification",
	}

	if any(key in payload for key in classification_keys):
		return payload

	nested = payload.get("result")
	if isinstance(nested, dict) and any(key in nested for key in classification_keys):
		return nested

	return payload

# Debug Logger to summarize WCO classification result
# ========================================================================
def _summarize_wco_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
	if not isinstance(payload, dict):
		return {"type": type(payload).__name__}

	classification_keys = (
		"section_classification",
		"chapter_classification",
		"heading_classification",
		"subheading_classification",
	)

	present_blocks = [key for key in classification_keys if payload.get(key)]
	missing_blocks = [key for key in classification_keys if not payload.get(key)]

	def _block_keys(block: Any) -> List[str]:
		return list(block.keys()) if isinstance(block, dict) else []

	block_keys = {
		key: _block_keys(payload.get(key))
		for key in classification_keys
	}

	return {
		"keys": list(payload.keys()),
		"present_blocks": present_blocks,
		"missing_blocks": missing_blocks,
		"block_keys": block_keys,
		"has_error": bool(payload.get("error")),
		"has_pre_classification": bool(payload.get("pre_classification")),
	}


def _apply_wco_fallback_from_preclassification(
	wco_payload: Optional[Dict[str, Any]],
	product_name: str,
) -> Dict[str, Any]:
	if not isinstance(wco_payload, dict):
		return {}

	if any(
		wco_payload.get(key)
		for key in (
			"section_classification",
			"chapter_classification",
			"heading_classification",
			"subheading_classification",
		)
	):
		return wco_payload

	pre = wco_payload.get("pre_classification") or {}
	if not isinstance(pre, dict):
		return wco_payload

	recommended = pre.get("recommended_sections") or []
	if not isinstance(recommended, list):
		recommended = []

	candidates = [
		item.get("section_id")
		for item in recommended
		if isinstance(item, dict) and item.get("section_id")
	]
	if not candidates:
		candidates = pre.get("candidate_section_ids") or []
	if not isinstance(candidates, list) or not candidates:
		return wco_payload

	section_id = str(candidates[0]).strip() if candidates[0] is not None else ""
	primary_recommendation = recommended[0] if recommended else {}
	primary_rationale = ""
	if isinstance(primary_recommendation, dict):
		primary_rationale = str(primary_recommendation.get("rationale") or "").strip()
	reasoning = primary_rationale or str(pre.get("reasoning") or "").strip()
	product_analysis = pre.get("product_analysis") or {}
	product_dna = ""
	if isinstance(product_analysis, dict):
		product_dna = str(product_analysis.get("product_dna") or "").strip()
	if not section_id and not reasoning:
		return wco_payload

	product_dna_text = product_dna
	fallback_notes = (
		reasoning
		or product_dna_text
		or f"Fallback pre-classification selected section {section_id}."
	)
	fallback_reason = (
		reasoning
		or f"Detailed section classification failed; using pre-classification fallback for product '{product_name}'."
	)

	wco_payload["section_classification"] = {
		"section_id": section_id or "Other",
		"section_title": f"Section {section_id}" if section_id else "Section Other",
		"reason": fallback_reason,
		"content_of_explanatory_notes": fallback_notes,
		"gri_usage": ["1"],
		"source_pages": [],
	}
	wco_payload["fallback_preclassification"] = True

	logger.warning(
		"Applied WCO fallback from pre_classification for product '%s' (section=%s).",
		product_name,
		section_id or "Other",
	)
	return wco_payload
#========================================================================

def _build_product_info(row: Dict[str, Any]) -> ProductInfo:
	return ProductInfo(
		product_name=row.get("product_name", ""),
		science_name=row.get("scientific_name") or None,
		product_description=row.get("description", ""),
		function=row.get("function", ""),
		structure=row.get("structure") or None,
		material=row.get("material") or None,
		specifications=row.get("specifications") or None,
		other_information=row.get("other_information") or None
	)


async def _process_row(
	row: DatasetInputRow,
	row_index: int,
	orchestrator: CrawlOrchestrator,
	hs_database_orchestrator: HSCodeDatabaseOrchestrator
) -> DatasetRowResult:
	errors: Dict[str, str] = {}
	row_data = row.data
	query_data = {
		"product_name": _strip_company_placeholder(row_data.get("product_name") or ""),
		"scientific_name": _strip_company_placeholder(row_data.get("scientific_name") or ""),
		"description": _strip_company_placeholder(row_data.get("description") or ""),
		"function": _strip_company_placeholder(row_data.get("function") or ""),
		"structure": _strip_company_placeholder(row_data.get("structure") or ""),
		"material": _strip_company_placeholder(row_data.get("material") or ""),
		"specifications": _strip_company_placeholder(row_data.get("specifications") or ""),
		"other_information": _strip_company_placeholder(row_data.get("other_information") or ""),
	}

	classifier_payload = {
		"product_name": query_data["product_name"],
		"science_name": query_data["scientific_name"] or None,
		"product_description": query_data["description"] or None,
		"function": query_data["function"] or None,
		"structure": query_data["structure"] or None,
		"material": query_data["material"] or None,
		"specifications": query_data["specifications"] or None,
	}

	try:
		classifier_payload = ProductQuery(**classifier_payload).model_dump()
	except ValidationError as exc:
		errors["wco"] = f"Invalid classifier input: {exc}"
		logger.warning(
			"Dataset row %s classifier input invalid: %s",
			row_index,
			exc,
		)
		classifier_payload = classifier_payload

	classifier_payload["scientific_name"] = query_data["scientific_name"] or None
	classifier_payload["description"] = query_data["description"] or None

	wco_result: Dict[str, Any] = {}
	compendium_result: List[Dict[str, Any]] = []
	asean_result: List[Dict[str, Any]] = []
	hs_ruling_result: Dict[str, Any] = {}
	hs_database_result: Dict[str, Any] = {}
	ai_conclusion_result: Dict[str, Any] = {}
	ai_benchmark_result: List[Dict[str, Any]] = []

	try:
		wco_result = _normalize_wco_result(
			await asyncio.to_thread(get_classification, classifier_payload)
		)
		logger.info(
			"Dataset row %s WCO raw payload: %s",
			row_index,
			json.dumps(wco_result, ensure_ascii=False),
		)
	except Exception as exc:  
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["wco"] = str(exc)
		logger.warning("Dataset row %s WCO classification failed: %s", row_index, exc)

	if not any(
		(wco_result or {}).get(key)
		for key in (
			"section_classification",
			"chapter_classification",
			"heading_classification",
			"subheading_classification",
		)
	):
		logger.warning(
			"Dataset row %s WCO classification returned empty blocks for product '%s'.",
			row_index,
			query_data.get("product_name", ""),
		)

	wco_result = _apply_wco_fallback_from_preclassification(
		wco_result,
		query_data.get("product_name", ""),
	)

	if not any(
		(wco_result or {}).get(key)
		for key in (
			"section_classification",
			"chapter_classification",
			"heading_classification",
			"subheading_classification",
		)
	):
		logger.warning(
			"Dataset row %s WCO payload missing classification blocks. Summary: %s",
			row_index,
			json.dumps(_summarize_wco_payload(wco_result), ensure_ascii=False),
		)

	try:
		compendium_result = await hscode_search(
			product_name=query_data["product_name"],
			science_name=query_data["scientific_name"],
			product_description=query_data["description"],
			function=query_data["function"],
			material=query_data["material"],
			structure=query_data["structure"],
			specifications=query_data["specifications"],
			other_information=query_data["other_information"],
			image_paths=[],
			collection_name="compendium"
		)
	except Exception as exc:  
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["compendium"] = str(exc)

	try:
		asean_result = await hscode_search(
			product_name=query_data["product_name"],
			science_name=query_data["scientific_name"],
			product_description=query_data["description"],
			function=query_data["function"],
			material=query_data["material"],
			structure=query_data["structure"],
			specifications=query_data["specifications"],
			other_information=query_data["other_information"],
			image_paths=[],
			collection_name="asean"
		)
	except Exception as exc:  
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["asean"] = str(exc)

	try:
		crawl_query = ProductCrawlQuery(
			product_name=query_data["product_name"],
			science_name=query_data["scientific_name"],
			product_description=query_data["description"],
			function=query_data["function"],
			structure=query_data["structure"],
			material=query_data["material"],
			specifications=query_data["specifications"],
			other_information=query_data["other_information"],
		)
		hs_ruling_response = await orchestrator.crawl_with_product_info_grouped(
			crawl_query
		)
		hs_ruling_result = hs_ruling_response.dict()
	except Exception as exc:  
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["hs_ruling"] = str(exc)

	try:
		crawl_query = ProductCrawlQuery(
			product_name=query_data["product_name"],
			science_name=query_data["scientific_name"],
			product_description=query_data["description"],
			function=query_data["function"],
			structure=query_data["structure"],
			material=query_data["material"],
			specifications=query_data["specifications"],
			other_information=query_data["other_information"],
		)
		hs_database_response = await hs_database_orchestrator.search_hs_codes(
			crawl_query
		)
		hs_database_result = hs_database_response.dict()
	except Exception as exc:  # pylint: disable=broad-except
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["hs_database"] = str(exc)
		logger.warning("Dataset row %s HS database lookup failed: %s", row_index, exc)

	if not _extract_hs_database_results(hs_database_result):
		logger.warning(
			"Dataset row %s HS database returned no results for product '%s'.",
			row_index,
			query_data.get("product_name", ""),
		)

	try:
		candidates = _build_candidate_list(
			compendium_result,
			asean_result,
			hs_database_result
		)
		if candidates:
			product = _build_product_info(row_data)
			ai_response = await analyze_hs_codes(product, candidates)
			ai_conclusion_result = ai_response.dict()
			ai_benchmark_result = [
				result.model_dump()
				for result in ai_response.results
			]
		else:
			errors["ai_conclusion"] = "No HS code candidates extracted."
	except Exception as exc:  
		if is_quota_error(exc):
			raise RuntimeError(quota_error_detail()) from exc
		errors["ai_conclusion"] = str(exc)

	if errors:
		logger.warning(
			"Dataset row %s completed with errors for product '%s': %s",
			row_index,
			query_data.get("product_name", ""),
			json.dumps(errors, ensure_ascii=False),
		)

	return DatasetRowResult(
		row_index=row_index,
		source_index=row.source_index,
		input_data=row_data,
		wco=wco_result or {},
		compendium=compendium_result or [],
		asean=asean_result or [],
		hs_ruling=hs_ruling_result or {},
		hs_database=hs_database_result or {},
		ai_conclusion=ai_conclusion_result or {},
		ai_benchmark=ai_benchmark_result or [],
		errors=errors
	)


async def process_dataset_rows(
	rows: List[DatasetInputRow],
	progress_callback: Optional[Any] = None
) -> List[DatasetRowResult]:
	orchestrator = CrawlOrchestrator()
	hs_database_orchestrator = HSCodeDatabaseOrchestrator()
	total = len(rows)
	if total == 0:
		return []

	logger.info(
		"Dataset processing: %s rows (max_concurrent=%s)",
		total,
		DATASET_MAX_CONCURRENT,
	)

	semaphore = asyncio.Semaphore(DATASET_MAX_CONCURRENT)

	async def _run(row: DatasetInputRow, index: int) -> tuple[int, DatasetRowResult]:
		async with semaphore:
			result = await _process_row(
				row,
				index,
				orchestrator,
				hs_database_orchestrator,
			)
			return index, result

	tasks = [
		asyncio.ensure_future(_run(row, index))
		for index, row in enumerate(rows, start=1)
	]

	results_by_index: Dict[int, DatasetRowResult] = {}
	completed = 0
	for coro in asyncio.as_completed(tasks):
		try:
			index, result = await coro
		except Exception as exc:
			if is_quota_error(exc):
				for task in tasks:
					task.cancel()
				raise RuntimeError(quota_error_detail()) from exc
			raise
		results_by_index[index] = result
		completed += 1
		if progress_callback:
			progress_callback(completed, total)

	return [results_by_index[i] for i in range(1, total + 1)]


def _format_gri_usage(result: Dict[str, Any]) -> str:
	section = result.get("section_classification") or {}
	selected_section = section.get("selected_section") or {}
	chapter = result.get("chapter_classification") or {}
	selected_chapter = chapter.get("selected_chapter") or {}
	heading = result.get("heading_classification") or {}
	selected_heading = heading.get("selected_heading") or {}
	subheading = result.get("subheading_classification") or {}
	selected_subheading = subheading.get("selected_subheading") or {}
	combined = [
		*([selected_section.get("gir_application")] if selected_section.get("gir_application") else []),
		*([selected_chapter.get("gir_application")] if selected_chapter.get("gir_application") else []),
		*([selected_heading.get("gir_application")] if selected_heading.get("gir_application") else []),
		*([selected_subheading.get("gir_application")] if selected_subheading.get("gir_application") else [])
	]
	unique = list({str(value).replace(" ", ""): str(value) for value in combined}.values())
	return ", ".join(sorted(filter(None, unique)))


def _to_text(value: Any) -> str:
	if value is None:
		return ""
	return str(value).strip()


def _join_blocks(blocks: List[str]) -> str:
	return f"\n{BLOCK_SEPARATOR}\n".join([block for block in blocks if block])


def _sanitize_excel_text(value: str) -> str:
	if not value:
		return ""
	cleaned = INVALID_XML_CHARS_PATTERN.sub("", value)
	if len(cleaned) > EXCEL_CELL_MAX_LENGTH:
		return cleaned[: EXCEL_CELL_MAX_LENGTH - 15] + "\n[TRUNCATED]"
	return cleaned


def _fallback_if_empty(value: str, fallback: str) -> str:
	return value if value else fallback


def _infer_output_template(
	original_content: Optional[bytes],
) -> Tuple[List[str], List[str], set]:
	"""Infer output headers and italic styling from the input template."""
	if not original_content:
		return HEADERS_PART1_EN, HEADERS_PART2_EN, set()

	try:
		workbook = load_workbook(BytesIO(original_content), data_only=True)
		worksheet = workbook["1.2"] if "1.2" in workbook.sheetnames else workbook.active
		header_row = 1

		normalized_to_col: Dict[str, int] = {}
		for col_idx in range(1, worksheet.max_column + 1):
			cell_value = worksheet.cell(row=header_row, column=col_idx).value
			normalized = _normalize_header(cell_value)
			if normalized and normalized not in normalized_to_col:
				normalized_to_col[normalized] = col_idx

		has_vn_headers = any(
			key in normalized_to_col
			for key in (
				"tenthuongpham",
				"mota",
				"congdungchucnang",
				"cautaothanhphan",
				"chatlieu",
				"thongsokythuat",
				"tenkhoahoctenkythuat",
			)
		)

		canonical_to_col: Dict[str, int] = {}
		for normalized, col_idx in normalized_to_col.items():
			canonical = HEADER_ALIASES.get(normalized)
			if canonical and canonical not in canonical_to_col:
				canonical_to_col[canonical] = col_idx

		data_row = 3 if worksheet.max_row >= 3 else 2
		italic_fields = set()
		for field, col_idx in canonical_to_col.items():
			cell = worksheet.cell(row=data_row, column=col_idx)
			if cell.font and cell.font.italic:
				italic_fields.add(field)

		headers_part1 = HEADERS_PART1_VI if has_vn_headers else HEADERS_PART1_EN
		headers_part2 = HEADERS_PART2_VI if has_vn_headers else HEADERS_PART2_EN
		return headers_part1, headers_part2, italic_fields
	except Exception:
		return HEADERS_PART1_EN, HEADERS_PART2_EN, set()


def _format_wco_notes(result: Dict[str, Any]) -> str:
	pre_classification = result.get("pre_classification") or {}
	section_block = result.get("section_classification") or {}
	selected_section = section_block.get("selected_section") or {}
	chapter_block = result.get("chapter_classification") or {}
	selected_chapter = chapter_block.get("selected_chapter") or {}
	heading_block = result.get("heading_classification") or {}
	selected_heading = heading_block.get("selected_heading") or {}
	subheading_block = result.get("subheading_classification") or {}
	selected_subheading = subheading_block.get("selected_subheading") or {}

	def _format_rejected(items: Any, id_key: str) -> str:
		if not isinstance(items, list):
			return ""
		formatted: List[str] = []
		for item in items:
			if not isinstance(item, dict):
				continue
			identifier = _to_text(item.get(id_key))
			reason = _to_text(item.get("reason"))
			if not identifier and not reason:
				continue
			formatted.append(f"{identifier or 'N/A'} - {reason}".strip())
		return "; ".join([entry for entry in formatted if entry])

	hs_code = _to_text(selected_subheading.get("subheading_id")) or _to_text(
		selected_heading.get("heading_id") or heading_block.get("heading_id")
	)
	hs_title = _to_text(selected_subheading.get("subheading_title")) or _to_text(
		selected_heading.get("heading_title") or heading_block.get("heading_title")
	)

	classification_section = ""
	if hs_code or hs_title:
		label = "HS Sub-heading" if _to_text(selected_subheading.get("subheading_id")) else "HS Heading"
		classification_section = "\n".join(
			[
				"Classification Result",
				f"{label}: {hs_code} {hs_title}".strip(),
			]
		)

	section_product_analysis = section_block.get("product_analysis") or {}
	product_dna = _to_text(
		section_product_analysis.get("product_dna")
		if isinstance(section_product_analysis, dict)
		else ""
	)
	key_attribute = _to_text(
		section_product_analysis.get("key_attribute")
		if isinstance(section_product_analysis, dict)
		else ""
	)
	product_lines = []
	if product_dna:
		product_lines.append(f"Product DNA: {product_dna}")
	if key_attribute:
		product_lines.append(f"Key Attribute: {key_attribute}")
	product_section = ""
	if product_lines:
		product_section = "\n".join(["Overview On Product Analysis", *product_lines])

	gri_text = _to_text(_format_gri_usage(result))
	gri_section = ""
	if gri_text:
		gri_section = "\n".join(["General Interpretative Rules (GIR)", f"GRIS Usage: {gri_text}"])

	blocks = [
		{"key": "section_classification", "title": "4.1. Section", "file": "Section"},
		{"key": "chapter_classification", "title": "4.2. Chapter", "file": "Chapter"},
		{"key": "heading_classification", "title": "4.3. Heading", "file": "Heading"},
		{"key": "subheading_classification", "title": "4.4. Sub-Heading", "file": "Sub-Heading"},
	]

	formatted: List[str] = []
	for item in blocks:
		block = result.get(item["key"]) or {}
		if item["key"] == "section_classification":
			identifier = selected_section.get("section_id") or ""
			heading_title = selected_section.get("section_title") or ""
			reason = _to_text(selected_section.get("rationale"))
			notes = _to_text(section_block.get("content_of_explanatory_notes"))
			rejected = _format_rejected(section_block.get("rejected_sections"), "section_id")
			pages = ", ".join(
				_resolve_source_pages(section_block, selected_section.get("section_id"))
			)
		elif item["key"] == "chapter_classification":
			identifier = selected_chapter.get("chapter_id") or ""
			heading_title = selected_chapter.get("chapter_title") or ""
			reason = _to_text(selected_chapter.get("rationale"))
			notes = _to_text(chapter_block.get("content_of_explanatory_notes"))
			rejected = _format_rejected(chapter_block.get("rejected_chapters"), "chapter_id")
			pages = ", ".join(
				_resolve_source_pages(chapter_block, selected_chapter.get("chapter_id"))
			)
		elif item["key"] == "heading_classification":
			identifier = selected_heading.get("heading_id") or ""
			heading_title = selected_heading.get("heading_title") or ""
			reason = _to_text(selected_heading.get("rationale"))
			notes = _to_text(heading_block.get("content_of_explanatory_notes"))
			rejected = _format_rejected(heading_block.get("rejected_headings"), "heading_id")
			pages = ", ".join(
				_resolve_source_pages(heading_block, selected_heading.get("heading_id"))
			)
		elif item["key"] == "subheading_classification":
			identifier = selected_subheading.get("subheading_id") or ""
			heading_title = selected_subheading.get("subheading_title") or ""
			reason = _to_text(selected_subheading.get("rationale"))
			notes = _to_text(subheading_block.get("content_of_explanatory_notes"))
			rejected = _format_rejected(
				subheading_block.get("rejected_subheadings"),
				"subheading_id",
			)
			pages = ", ".join(
				_resolve_source_pages(subheading_block, selected_subheading.get("subheading_id"))
			)
		else:
			identifier = (
				block.get("subheading_id")
				or block.get("heading_id")
				or block.get("chapter_id")
				or block.get("section_id")
				or ""
			)
			heading_title = (
				block.get("subheading_title")
				or block.get("heading_title")
				or block.get("chapter_title")
				or block.get("section_title")
				or ""
			)
			reason = _to_text(block.get("reason"))
			notes = _to_text(block.get("content_of_explanatory_notes"))
			rejected = ""
			pages = ", ".join(_resolve_source_pages(block, identifier))

		if (
			not identifier
			and not heading_title
			and not reason
			and not notes
			and not pages
			and not rejected
		):
			continue

		formatted.append(
			"\n".join(
				[
					item["title"],
					f"{item['file']}: {identifier}" if identifier else "",
					f"{item['file']} Title: {heading_title}" if heading_title else "",
					f"Rationale: {reason}" if reason else "",
					f"Content Of Explanatory Notes: {notes}" if notes else "",
					f"Rejected {item['file']}s: {rejected}" if rejected else "",
					f"Relevant HS Explanatory Notes' files: {item['file']}.pdf",
					f"Explanatory Notes Page: {pages}" if pages else "",
				]
			)
		)

	sections = [block for block in formatted if block.strip()]
	if not sections and pre_classification:
		recommended = pre_classification.get("recommended_sections") or []
		candidate_sections = pre_classification.get("candidate_section_ids") or []
		product_analysis = pre_classification.get("product_analysis") or {}
		product_dna = product_analysis.get("product_dna") if isinstance(product_analysis, dict) else []
		reasoning = _to_text(pre_classification.get("reasoning"))

		recommended_labels: List[str] = []
		if isinstance(recommended, list):
			for item in recommended:
				if not isinstance(item, dict):
					continue
				section_id = item.get("section_id")
				snippet = item.get("section_title_snippet")
				score = item.get("confidence_score")
				if section_id:
					label = str(section_id)
					if snippet:
						label = f"{label} - {snippet}"
					if isinstance(score, (int, float)):
						label = f"{label} ({score:.1f})"
					recommended_labels.append(label)

		pre_section = ["Pre-classification Only"]
		if product_dna:
			pre_section.append("Product DNA: " + _to_text(product_dna))
		if recommended_labels:
			pre_section.append(f"Recommended Sections: {', '.join(recommended_labels)}")
		elif candidate_sections:
			pre_section.append(f"Candidate Sections: {', '.join(candidate_sections)}")
		if reasoning:
			pre_section.append(f"Reasoning: {reasoning}")
		sections = ["\n".join(pre_section)]
	if gri_section:
		sections.insert(0, gri_section)
	if product_section:
		sections.insert(0, product_section)
	if classification_section:
		sections.insert(0, classification_section)
	return "\n\n".join(sections)


def _format_citation_items(
	items: Sequence[Dict[str, Any]],
	source_type: str,
) -> str:
	lines: List[str] = []
	for index, item in enumerate(items or [], start=1):
		pages = ", ".join(
			_resolve_source_pages(item.get("metadata", {}), (item.get("subheading_ids") or [""])[0])
		)
		if source_type == "compendium":
			file_name = "WCO Compendium of Classification Opinions.pdf"
			file_label = "WCO Compendium of Classification Opinions Files"
			page_label = "WCO Compendium of Classification Opinions Pages"
		else:
			file_name = "SEN AHTN 2022 (EN & VN) - Appendix of OL3866 (colour).pdf"
			file_label = "SEN AHTN 2022 (EN & VN) - Appendix of OL3866 (colour) Files"
			page_label = "SEN AHTN 2022 (EN & VN) - Appendix of OL3866 (colour) Pages"

		parts = [
			f"Result {index}",
			("HS: " + ", ".join(item.get("subheading_ids") or [])) if item.get("subheading_ids") else "",
			f"Reason: {item.get('reason')}" if item.get("reason") else "",
			f"Notes: {item.get('content_of_citation')}" if item.get("content_of_citation") else "",
			f"{file_label}: {file_name}",
			f"{page_label}: {pages}" if pages else "",
		]
		line = "\n".join([part for part in parts if part]).strip()
		if line:
			lines.append(line)
	return "\n\n".join(lines)


def _format_hs_ruling(result: Dict[str, Any]) -> str:
	results = result.get("results") or []
	sources = result.get("sources_queried") or []
	if not results or not sources:
		return ""

	keyword_blocks: List[str] = []
	for idx, item in enumerate(results, start=1):
		technical_name = _to_text(item.get("technical_name"))
		source_blocks: List[str] = []
		for source in sources:
			source_name = _to_text(source.get("source_name"))
			source_url = _to_text(source.get("source_url"))
			links = [
				_to_text(link.get("link"))
				for link in (item.get("links") or [])
				if _to_text(link.get("source")) == source_name and _to_text(link.get("link"))
			]
			source_blocks.append(
				"\n".join(
					[
						f"Source: {source_name}" if source_name else "",
						f"Source URL: {source_url}" if source_url else "",
						"Links:",
						"\n".join([f"- {url}" for url in links]) if links else "- N/A",
					]
				)
			)

		keyword_blocks.append(
			"\n".join(
				[
					f"Keyword Suggestion {idx}: \"{technical_name}\"",
					_join_blocks(source_blocks),
				]
			)
		)

	return f"\n\n{BLOCK_SEPARATOR}\n\n".join([block for block in keyword_blocks if block])


def _format_hs_database(results: Sequence[Dict[str, Any]]) -> str:
	technical_results = results or []
	if not technical_results:
		return ""

	keyword_blocks: List[str] = []
	for idx, item in enumerate(technical_results, start=1):
		technical_name = _to_text(item.get("technical_name"))
		source_blocks: List[str] = []
		for source in item.get("sources") or []:
			source_name = _to_text(source.get("source"))
			source_url = _to_text(source.get("source_url"))
			result_url = _to_text(source.get("result_url"))
			hs_codes = source.get("hs_codes") or []

			urls_from_hs_codes = [_to_text(hs.get("url")) for hs in hs_codes if _to_text(hs.get("url"))]
			stats = "\n".join(
				[
					f"- {hs_code} ({count}/{total}) ~ {percentage}%"
					for hs_code, count, total, percentage in [
						(
							_to_text(hs.get("hs_code")),
							_to_text(hs.get("count")),
							_to_text(source.get("total_count")),
							_to_text(hs.get("percentage")),
						)
						for hs in hs_codes
					]
					if hs_code
				]
			)

			if "trade-tariff" in source_url.lower() or not result_url:
				link_block = "\n".join(
					[
						"Links:",
						"\n".join([f"- {url}" for url in urls_from_hs_codes]) if urls_from_hs_codes else "- N/A",
					]
				)
			else:
				link_block = f"Result URL: {result_url}"

			source_blocks.append(
				"\n".join(
					[
						f"Source: {source_name}" if source_name else "",
						f"Source URL: {source_url}" if source_url else "",
						link_block,
						f"Statistics:\n{stats}" if stats else "",
					]
				)
			)

		keyword_blocks.append(
			"\n".join(
				[
					f"Keyword Suggestion {idx}: \"{technical_name}\"",
					_join_blocks(source_blocks) if source_blocks else "- N/A",
				]
			)
		)

	return f"\n\n{BLOCK_SEPARATOR}\n\n".join([block for block in keyword_blocks if block])


def _format_conclusion(result: Dict[str, Any], benchmark: Sequence[Dict[str, Any]]) -> str:
	benchmark_rows = []
	for idx, item in enumerate(benchmark or result.get("results") or [], start=1):
		section_chapter = " / ".join(
			[value for value in [_to_text(item.get("section_info")), _to_text(item.get("chapter_info"))] if value]
		)
		benchmark_rows.append(
			"\n".join(
				[
					f"Result {idx}",
					f"HS Sub-heading: {_to_text(item.get('hs_code'))}" if _to_text(item.get("hs_code")) else "",
					f"Score: {_to_text(item.get('compatibility_score'))}" if item.get("compatibility_score") is not None else "",
					f"GIR Applied: {_to_text(item.get('gir_applied'))}" if _to_text(item.get("gir_applied")) else "",
					f"Legal Reasoning: {_to_text(item.get('legal_reasoning'))}" if _to_text(item.get("legal_reasoning")) else "",
					f"Section / Chapter: {section_chapter}" if section_chapter else "",
				]
			)
		)

	lines = [
		"1. Recommended HS Sub-heading",
		f"Recommended HS Code: {_to_text(result.get('recommended_hs_code'))}" if _to_text(result.get("recommended_hs_code")) else "",
		"2. Executive Summary",
		_to_text(result.get("executive_summary")),
		f"Total HS Codes Analyzed: {_to_text(result.get('total_hs_codes_analyzed'))}" if result.get("total_hs_codes_analyzed") is not None else "",
		"3. Benchmark",
		"\n\n".join([row for row in benchmark_rows if row]) if benchmark_rows else "No comparison results available.",
	]
	return "\n".join([line for line in lines if line])




def build_output_excel(
	results: List[DatasetRowResult],
	original_content: Optional[bytes] = None,
) -> bytes:
	headers_part1, headers_part2, italic_fields = _infer_output_template(original_content)
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "1.2"
	worksheet.sheet_view.showGridLines = False
	worksheet.sheet_view.zoomScale = 80
	worksheet.sheet_properties.tabColor = "000000"
	worksheet.column_dimensions["A"].width = 2

	all_headers = headers_part1 + headers_part2
	for col_idx, header in enumerate(all_headers, 1):
		cell = worksheet.cell(row=1, column=col_idx, value=header)
		if col_idx in EMPTY_COLS:
			cell.border = NO_BORDER
		else:
			cell.font = HEADER_FONT
			cell.fill = HEADER_FILL
			cell.alignment = HEADER_ALIGNMENT
			cell.border = THIN_BORDER

	for col_idx in range(1, len(all_headers) + 1):
		cell = worksheet.cell(row=2, column=col_idx, value="")
		if col_idx not in EMPTY_COLS:
			cell.border = THIN_BORDER

	for row_idx, result in enumerate(results, 3):
		input_data = result.input_data or {}
		wco_payload = result.wco or {}
		gri_text = _sanitize_excel_text(_format_gri_usage(wco_payload))
		wco_text = _sanitize_excel_text(_format_wco_notes(wco_payload))
		if wco_payload.get("fallback_preclassification"):
			gri_text = ""
			wco_text = ""
		if not gri_text and not wco_text:
			logger.warning(
				"Dataset output row %s rendered empty GRI/WCO for product '%s'. WCO keys=%s",
				row_idx - 2,
				input_data.get("product_name", ""),
				list(wco_payload.keys()) if isinstance(wco_payload, dict) else type(wco_payload).__name__,
			)

		gri_text = _fallback_if_empty(gri_text, "No GIR usage available for this item.")
		wco_text = _fallback_if_empty(
			wco_text,
			"No WCO explanatory notes available for this item.",
		)
		compendium_text = _fallback_if_empty(
			_sanitize_excel_text(_format_citation_items(result.compendium or [], "compendium")),
			"No WCO compendium notes available for this item.",
		)
		asean_text = _fallback_if_empty(
			_sanitize_excel_text(_format_citation_items(result.asean or [], "asean")),
			"No SEN notes available for this item.",
		)
		hs_ruling_text = _fallback_if_empty(
			_sanitize_excel_text(_format_hs_ruling(result.hs_ruling or {})),
			"No international HS ruling data available for this item.",
		)
		hs_database_text = _fallback_if_empty(
			_sanitize_excel_text(
				_format_hs_database(_extract_hs_database_results(result.hs_database or {}))
			),
			"No public HS database data available for this item.",
		)
		conclusion_text = _fallback_if_empty(
			_sanitize_excel_text(_format_conclusion(result.ai_conclusion or {}, result.ai_benchmark or [])),
			"No AI conclusion available for this item.",
		)
		row_data = [
			"",  # 1: Empty separator
			row_idx - 2,  # 2: STT
			input_data.get("npl_product_code", ""),  # 3: NPL/Product Code
			input_data.get("hs_codes_review", ""),  # 4: Declared HS Codes
			input_data.get("product_name", ""),  # 5: Tên thương phẩm
			input_data.get("scientific_name", ""),  # 6: Tên khoa học
			input_data.get("description", ""),  # 7: Mô tả
			input_data.get("function", ""),  # 8: Công dụng
			input_data.get("structure", ""),  # 9: Cấu tạo
			input_data.get("material", ""),  # 10: Chất liệu
			input_data.get("specifications", ""),  # 11: Thông số kỹ thuật
			"",  # 12: Empty separator
			gri_text,  # 13: GRI
			wco_text,  # 14: WCO Explanatory Notes
			compendium_text,  # 15 : WCO Compendium
			asean_text,  # 16 : SEN AHTN Notes
			hs_ruling_text,  # 17 : International HS Ruling
			hs_database_text,  # 18 : Public HS Database
			conclusion_text,  # 19 : AI Conclusion
		]

		for col_idx, value in enumerate(row_data, 1):
			cell = worksheet.cell(row=row_idx, column=col_idx, value=value)
			if value == "[the Company to fill]":
				cell.font = ITALIC_FONT
			elif col_idx == 5 and "product_name" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 6 and "scientific_name" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 7 and "description" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 8 and "function" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 9 and "structure" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 10 and "material" in italic_fields:
				cell.font = ITALIC_FONT
			elif col_idx == 11 and "specifications" in italic_fields:
				cell.font = ITALIC_FONT
			else:
				cell.font = CELL_FONT
			if col_idx in EMPTY_COLS:
				cell.border = NO_BORDER
			else:
				cell.border = THIN_BORDER
			if col_idx == 2:
				cell.alignment = CENTER_ALIGNMENT
			elif col_idx >= 13:
				cell.alignment = TOP_CELL_ALIGNMENT
			else:
				cell.alignment = CELL_ALIGNMENT

		worksheet.row_dimensions[row_idx].height = DATA_ROW_HEIGHT

	for col_idx, width in enumerate(COLUMN_WIDTHS, 1):
		worksheet.column_dimensions[get_column_letter(col_idx)].width = width

	worksheet.row_dimensions[1].height = HEADER_ROW_HEIGHT
	last_row = 2 + len(results)
	worksheet.auto_filter.ref = f"B2:S{last_row}"
	worksheet.auto_filter.filterColumn.append(FilterColumn(colId=10, hiddenButton=True))
	worksheet.freeze_panes = "L3"

	buffer = BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()
