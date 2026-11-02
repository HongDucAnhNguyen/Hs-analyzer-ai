"""Excel Processing Module for Report Service

This module provides utilities for:
- Parsing TKR Excel files (xlsx/xlsb)
- Generating HS Consistency, Value Variance, and NTM reports
- Creating combined Excel output with multiple sheets

Module Structure:
- constants.py: Column mappings and Excel styles
- file_cache.py: Memory-efficient Excel file caching
- helpers.py: Utility functions (parsing, validation)
- tariff.py: Tariff rate loading and lookup
- parser.py: Excel file parsing
- reports.py: Report generation (HS, VV, NTM)
- output.py: Excel output generation
- input_sheet.py: Input data sheet creation

Usage:
    from report_service.utils.excel_processor import (
        parse_excel_file,
        generate_hs_consistency_report,
        generate_value_variance_report,
        generate_ntm_report,
        generate_combined_excel,
    )
"""

# Re-export all public APIs for backward compatibility

# Cache
from .file_cache import ExcelFileCache

# Constants
from .constants import (
    EXCEL_COLUMN_MAP,
    NUMERIC_FIELDS,
    HEADER_FONT,
    HEADER_FILL,
    HEADER_ALIGNMENT,
    CELL_FONT,
    CELL_ALIGNMENT,
    NUMBER_ALIGNMENT,
    CENTER_ALIGNMENT,
    THIN_BORDER,
    NO_BORDER,
    LINK_FONT,
)

# Helpers
from .helpers import (
    parse_numeric_value,
    is_valid_npl_sp,
    format_hs_code,
    generate_filename,
)

# Tariff
from .tariff import (
    load_tariff_rates,
    parse_tax_value,
    get_duty_rate,
    get_tax_str,
)

# Parser
from .parser import (
    find_header_row,
    parse_excel_file,
    parse_excel_from_cache,
)

# Reports
from .reports import (
    generate_hs_consistency_reports,
    generate_hs_consistency_report,
    generate_value_variance_report,
    generate_ntm_report,
)

# Output
from .output import (
    apply_sheet_settings,
    generate_combined_excel,
)

# TRAINS utilities (for flow conversion)
from .trains import (
    convert_flow_to_vietnamese,
    convert_flow_to_lookup_key,
)

# CAS extraction utilities (for chemical products)
from .cas_extractor import (
    extract_cas_from_ten_hang,
    extract_all_cas_from_ten_hang,
    check_cas_in_appendix_iii,
    check_hs_chapter_28_29,
    analyze_chemical_compliance,
    get_cas_via_llm_sync,
    batch_extract_cas_via_llm_sync,
    get_chemical_name_from_cas,
    get_chemical_appendix_info,
)

# Define public API
__all__ = [
    # Cache
    "ExcelFileCache",
    # Constants
    "EXCEL_COLUMN_MAP",
    "NUMERIC_FIELDS",
    "HEADER_FONT",
    "HEADER_FILL",
    "HEADER_ALIGNMENT",
    "CELL_FONT",
    "CELL_ALIGNMENT",
    "NUMBER_ALIGNMENT",
    "CENTER_ALIGNMENT",
    "THIN_BORDER",
    "NO_BORDER",
    "LINK_FONT",
    # Helpers
    "parse_numeric_value",
    "is_valid_npl_sp",
    "format_hs_code",
    "generate_filename",
    # Tariff
    "load_tariff_rates",
    "parse_tax_value",
    "get_duty_rate",
    "get_tax_str",
    # Parser
    "find_header_row",
    "parse_excel_file",
    "parse_excel_from_cache",
    # Reports
    "generate_hs_consistency_reports",
    "generate_hs_consistency_report",
    "generate_value_variance_report",
    "generate_ntm_report",
    # Output
    "apply_sheet_settings",
    "generate_combined_excel",
    # TRAINS utilities
    "convert_flow_to_vietnamese",
    "convert_flow_to_lookup_key",
    # CAS extraction
    "extract_cas_from_ten_hang",
    "extract_all_cas_from_ten_hang",
    "check_cas_in_appendix_iii",
    "check_hs_chapter_28_29",
    "analyze_chemical_compliance",
    "get_cas_via_llm_sync",
    "batch_extract_cas_via_llm_sync",
    "get_chemical_name_from_cas",
    "get_chemical_appendix_info",
]
