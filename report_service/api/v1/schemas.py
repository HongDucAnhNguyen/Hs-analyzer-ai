"""
API v1 Schemas for Report Service - Task Management
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ReportSheet(str, Enum):
    """Available report sheets"""
    INPUT_DATA = "input_data"
    HS_INCONSISTENCY = "hs_inconsistency"
    HS_TO_COLLECT = "hs_to_collect"
    VALUE_VARIANCE = "value_variance"
    NON_TARIFF_MEASURES = "ntm"
    
    @classmethod
    def all_sheets(cls) -> List["ReportSheet"]:
        """Return all available sheets"""
        return list(cls)


# Default sheets to generate (all sheets)
DEFAULT_SHEETS = ReportSheet.all_sheets()


class TaskSubmitResponse(BaseModel):
    """Response when submitting an async report task"""
    task_id: str = Field(..., description="Unique ID for the report task")
    status: str = Field(..., description="Current status of the task")
    message: str = Field(..., description="Information message")


class TaskStatusResponse(BaseModel):
    """Response for checking task status"""
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status: PENDING, STARTED, PROGRESS, SUCCESS, FAILURE")
    result: Optional[Dict[str, Any]] = Field(None, description="Report result if task is complete")
    progress: Optional[Dict[str, Any]] = Field(None, description="Progress information if task is in progress")
    partial_results: Optional[Dict[str, Any]] = Field(None, description="Partial results available during processing")
    error: Optional[str] = Field(None, description="Error message if task failed")


class PrefillMode(str, Enum):
    """Pre-fill mode for missing Mã NPL/SP (Item Code)"""
    NONE = "none"                # No pre-filling (default)
    RULE_BASED = "rule_based"    # Rule-based matching only (fast, no cost)
    LLM = "llm"                  # Rule-based + LLM for remaining (slower, uses API credits)


class ProcessAsyncRequest(BaseModel):
    """Request to process a file from MinIO asynchronously"""
    object_name: str = Field(..., description="Object name in MinIO storage")
    input_sections: Optional[List["InputSection"]] = Field(
        default=None,
        description="List of input sections to fill in input_data sheet. Options: tariff_classification, customs_valuation, non_tariff_measures, exim_statistics. Default: all sections."
    )
    prefill_mode: PrefillMode = Field(
        default=PrefillMode.NONE,
        description="Pre-fill mode for missing Mã NPL/SP: 'none' (default), 'rule_based' (fast, pattern matching), 'llm' (rule_based + LLM generation)."
    )


class ProcessAsyncResponse(BaseModel):
    """Response after submitting async processing task"""
    task_id: str = Field(..., description="Task ID for polling status")
    status: str = Field(..., description="Current task status")
    message: str = Field(..., description="Information message")


class DatasetProcessAsyncRequest(BaseModel):
    """Request to process an E-tariff dataset file from MinIO asynchronously"""
    object_name: str = Field(..., description="Object name in MinIO storage")


class DatasetProcessAsyncResponse(BaseModel):
    """Response after submitting dataset async processing task"""
    task_id: str = Field(..., description="Task ID for polling status")
    status: str = Field(..., description="Current task status")
    message: str = Field(..., description="Information message")


class ManualInputExportRequest(BaseModel):
    """Request payload for manual input export"""
    product_name: Optional[str] = Field(default="", description="Commodity name")
    science_name: Optional[str] = Field(default="", description="Scientific/technical name")
    product_description: Optional[str] = Field(default="", description="Commodity description")
    function: Optional[str] = Field(default="", description="Function")
    structure: Optional[str] = Field(default="", description="Structure")
    material: Optional[str] = Field(default="", description="Material")
    specifications: Optional[str] = Field(default="", description="Specifications")
    gri: Optional[str] = Field(default="", description="GIR values")
    wco_explanatory_notes: Optional[str] = Field(
        default="",
        description="WCO HS Explanatory Notes 2022"
    )
    wco_compendium: Optional[str] = Field(
        default="",
        description="WCO Compendium of Classification Opinions 2022"
    )
    sen_2022: Optional[str] = Field(default="", description="SEN 2022")
    international_hs_ruling: Optional[str] = Field(
        default="",
        description="International HS Ruling"
    )
    public_hs_database: Optional[str] = Field(
        default="",
        description="Public HS database"
    )
    conclusion: Optional[str] = Field(default="", description="Conclusion")


class HsToCollectFillMapResponse(BaseModel):
    """Response payload for HS-to-collect fill map."""
    fills: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping from ma_npl_sp to column values for Sheet 1.2"
    )


# ============================================================================
# Input Sheet Options API
# ============================================================================

class InputSection(str, Enum):
    """Available input sections for report generation"""
    TARIFF_CLASSIFICATION = "tariff_classification"  # Section 1 (1.1 + 1.2)
    CUSTOMS_VALUATION = "customs_valuation"  # Section 2 (2.1 + 2.2 + 2.3)
    NON_TARIFF_MEASURES = "non_tariff_measures"  # Section 3 (3.1 + 3.2)
    EXIM_STATISTICS = "exim_statistics"  # Section 1.0 (EXIM Statistics)
    
    @classmethod
    def all_sections(cls) -> List["InputSection"]:
        """Return all available sections"""
        return list(cls)


# Default input sections (all sections)
DEFAULT_INPUT_SECTIONS = InputSection.all_sections()


# Mapping from InputSection to enabled_sections set
INPUT_SECTION_TO_ENABLED = {
    InputSection.TARIFF_CLASSIFICATION: "1",
    InputSection.CUSTOMS_VALUATION: "2",
    InputSection.NON_TARIFF_MEASURES: "3",
    InputSection.EXIM_STATISTICS: "exim",
}


def get_enabled_sections(input_sections: Optional[List[InputSection]]) -> set:
    """Convert list of InputSection to enabled_sections set
    
    Args:
        input_sections: List of InputSection enums, None means all sections
        
    Returns:
        Set of enabled section numbers ("1", "2", "3", "exim")
    """
    if input_sections is None:
        return {"1", "2", "3", "exim"}  # All enabled
    return {INPUT_SECTION_TO_ENABLED[s] for s in input_sections}


class InputSheetOptionsResponse(BaseModel):
    """Response for available input section options"""
    input_sections: List[str] = Field(..., description="List of available input section values to use in API requests")


# Input section options - these are the actual values to pass in API requests
INPUT_SHEET_OPTIONS = [
    "tariff_classification",  # Section 1 (1.1 + 1.2)
    "customs_valuation",  # Section 2 (2.1 + 2.2 + 2.3)
    "non_tariff_measures",  # Section 3 (3.1 + 3.2)
    "exim_statistics",  # Section 1.0 (EXIM Statistics)
]

