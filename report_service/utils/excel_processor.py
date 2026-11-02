"""Excel processing utilities for Report Service - BACKWARD COMPATIBILITY WRAPPER

This file maintains backward compatibility with existing imports.
All functionality has been refactored into the excel_processor/ package.

For new code, prefer importing directly from the package:
    from report_service.utils.excel_processor import (
        parse_excel_file,
        generate_hs_consistency_report,
        generate_combined_excel,
    )

Module Structure (in excel_processor/):
- constants.py: Column mappings and Excel styles
- file_cache.py: Memory-efficient Excel file caching  
- helpers.py: Utility functions (parsing, validation)
- tariff.py: Tariff rate loading and lookup
- parser.py: Excel file parsing
- reports.py: Report generation (HS, VV, NTM)
- output.py: Excel output generation
- input_sheet.py: Input data sheet creation
"""

# Re-export everything from the new package structure
from report_service.utils.excel_processor import (
    # Cache
    ExcelFileCache,
    # Constants
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
    # Helpers
    parse_numeric_value,
    is_valid_npl_sp,
    format_hs_code,
    generate_filename,
    # Tariff
    load_tariff_rates,
    parse_tax_value,
    get_duty_rate,
    get_tax_str,
    # Parser
    find_header_row,
    parse_excel_file,
    parse_excel_from_cache,
    # Reports
    generate_hs_consistency_reports,
    generate_hs_consistency_report,
    generate_value_variance_report,
    generate_ntm_report,
    # Output
    apply_sheet_settings,
    generate_combined_excel,
)

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
]
