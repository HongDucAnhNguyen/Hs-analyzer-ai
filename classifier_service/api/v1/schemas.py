from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
import unicodedata

class ProductQuery(BaseModel):
    engagement_code: Optional[str] = Field(None, description="Engagement code provided by the client")
    product_name: str = Field(..., description="Tên sản phẩm (bắt buộc)")
    science_name: Optional[str] = Field(None, description="Tên khoa học/kỹ thuật của sản phẩm")
    product_description: Optional[str] = Field(None, description="Mô tả chi tiết về sản phẩm")
    function: Optional[str] = Field(None, description="Chức năng chính của sản phẩm")
    structure: Optional[str] = Field(None, description="Cấu trúc, cách lắp ráp của sản phẩm")
    material: Optional[str] = Field(None, description="Vật liệu chính làm ra sản phẩm")
    specifications: Optional[str] = Field(None, description="Thông số kỹ thuật (kích thước, trọng lượng, v.v.)")
    
    
    @field_validator('engagement_code', 'product_name', 'science_name', 'product_description', 'function', 'structure', 'material', 'specifications', mode='before')
    @classmethod
    def validate_utf8_string(cls, v):
        if v is None:
            return v
        if isinstance(v, bytes):
            try:
                v = v.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("Invalid UTF-8 encoding.")
        if isinstance(v, str):
            normalized = unicodedata.normalize('NFC', v).strip()
            return normalized
        return v

    @field_validator('product_name', mode='after')
    @classmethod
    def validate_required_not_blank(cls, v):
        if v is None:
            raise ValueError("Field cannot be blank.")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be blank.")
        return v

    @field_validator('product_description', 'function', mode='after')
    @classmethod
    def validate_required_or_na(cls, v):
        if v is None:
            raise ValueError("Field cannot be blank.")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Field cannot be blank.")
        return v

    @field_validator('product_description', 'function', mode='after')
    @classmethod
    def normalize_na_to_empty(cls, v):
        if isinstance(v, str) and v.strip().lower() == "n/a":
            return ""
        return v

class ClassificationResponse(BaseModel):
    pre_classification: Optional[dict] = Field(None, description="Pre-classification result with candidate sections")
    section_classification: Optional[dict]
    chapter_classification: Optional[dict]
    heading_classification: Optional[dict]
    subheading_classification: Optional[dict]
    cache_hit: Optional[bool] = Field(default=False, description="Indicates if result was served from cache")


class ProductAnalysis(BaseModel):
    product_dna: str = Field(
        ...,
        description="Tóm tắt bản chất sản phẩm (Tên + Chất liệu + Công dụng + Tình trạng)."
    )


class RecommendedSection(BaseModel):
    section_id: Literal[
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "XI",
        "XII",
        "XIII",
        "XIV",
        "XV",
        "XVI",
        "XVII",
        "XVIII",
        "XIX",
        "Other",
    ] = Field(
        ...,
        description="ID của Section được đề xuất."
    )
    section_title_snippet: str = Field(
        ...,
        description="Trích đoạn ngắn tiêu đề Section."
    )
    confidence_score: float = Field(
        ...,
        ge=1,
        le=10,
        description="Mức độ phù hợp từ 1 đến 10."
    )
    gir_application: str = Field(
        ...,
        description="Ghi chú ngắn về cơ sở đề xuất theo GIR."
    )
    rationale: str = Field(
        ...,
        description="Lý do ngắn gọn cho đề xuất Section."
    )


class SectionPreClassification(BaseModel):
    """Schema for the pre-classification step: summarize product DNA and recommend sections"""
    product_analysis: ProductAnalysis = Field(
        ...,
        description="Phân tích tóm tắt bản chất sản phẩm."
    )
    recommended_sections: list[RecommendedSection] = Field(
        ...,
        description="Danh sách các Section đề xuất (tối đa 3)."
    )


class SectionProductAnalysis(BaseModel):
    product_dna: str = Field(
        ...,
        description="Tóm tắt bản chất sản phẩm (Tên + Chất liệu + Công dụng + Tình trạng)."
    )
    key_attribute: str = Field(
        ...,
        description="Yếu tố quyết định: Định danh, Chất liệu, hay Chức năng."
    )


class SelectedSection(BaseModel):
    section_id: Literal[
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "XI",
        "XII",
        "XIII",
        "XIV",
        "XV",
        "XVI",
        "XVII",
        "XVIII",
        "XIX",
        "Other",
    ] = Field(
        ...,
        description="ID của Section được chọn."
    )
    section_title: str = Field(
        ...,
        description="Tiêu đề đầy đủ của Section được chọn."
    )
    rationale: str = Field(
        ...,
        description="Lập luận lựa chọn Section."
    )
    legal_basis: str = Field(
        ...,
        description="Trích dẫn cụ thể Chú giải pháp lý hỗ trợ quyết định."
    )
    gir_application: str = Field(
        ...,
        description="Ghi chú quy tắc GIR làm cơ sở chốt hạ."
    )


class RejectedSection(BaseModel):
    section_id: str = Field(
        ...,
        description="ID của Section bị loại."
    )
    reason: str = Field(
        ...,
        description="Lý do loại Section."
    )


class SectionClassification(BaseModel):
    product_analysis: SectionProductAnalysis = Field(
        ...,
        description="Phân tích tóm tắt bản chất sản phẩm."
    )
    selected_section: SelectedSection = Field(
        ...,
        description="Section được chọn cuối cùng."
    )
    rejected_sections: list[RejectedSection] = Field(
        ...,
        description="Danh sách Section bị loại."
    )
    content_of_explanatory_notes: str = Field(
        ...,
        description="Trích đoạn/tóm tắt các chú giải quyết định."
    )
    source_pages: list[int] = Field(
        ...,
        description="Danh sách các trang trong tài liệu chứa thông tin liên quan được trích dẫn."
    )


class TaskSubmitResponse(BaseModel):
    """Response when submitting an async classification task"""
    task_id: str = Field(..., description="Unique ID for the classification task")
    status: str = Field(..., description="Current status of the task")
    message: str = Field(..., description="Information message")


class TaskStatusResponse(BaseModel):
    """Response for checking task status"""
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status: PENDING, STARTED, PROGRESS, SUCCESS, FAILURE")
    result: Optional[dict] = Field(None, description="Classification result if task is complete")
    progress: Optional[dict] = Field(None, description="Progress information if task is in progress")
    partial_results: Optional[dict] = Field(None, description="Partial results available during processing (e.g., pre_classification, section_classification)")
    error: Optional[str] = Field(None, description="Error message if task failed")




class ChapterProductAnalysis(BaseModel):
    product_dna: str = Field(
        ...,
        description="Tóm tắt bản chất sản phẩm (Tên + Chất liệu + Công dụng + Tình trạng)."
    )
    key_attribute: str = Field(
        ...,
        description="Yếu tố quyết định: Định danh, Chất liệu, hay Chức năng."
    )


class SelectedChapter(BaseModel):
    chapter_id: str = Field(
        ...,
        description="ID của Chapter được chọn (ví dụ: '84')."
    )
    chapter_title: str = Field(
        ...,
        description="Tiêu đề đầy đủ của Chapter được chọn."
    )
    rationale: str = Field(
        ...,
        description="Lập luận lựa chọn Chapter."
    )
    legal_basis: str = Field(
        ...,
        description="Trích dẫn nguyên văn Chú giải pháp lý hỗ trợ quyết định."
    )
    gir_application: str = Field(
        ...,
        description="Ghi chú quy tắc GIR làm cơ sở chốt hạ."
    )


class RejectedChapter(BaseModel):
    chapter_id: str = Field(
        ...,
        description="ID của Chapter bị loại."
    )
    reason: str = Field(
        ...,
        description="Lý do loại Chapter."
    )


class ChapterClassification(BaseModel):
    product_analysis: ChapterProductAnalysis = Field(
        ...,
        description="Phân tích tóm tắt bản chất sản phẩm."
    )
    selected_chapter: SelectedChapter = Field(
        ...,
        description="Chapter được chọn cuối cùng."
    )
    rejected_chapters: list[RejectedChapter] = Field(
        ...,
        description="Danh sách Chapter bị loại."
    )
    content_of_explanatory_notes: str = Field(
        ...,
        description="Trích đoạn/tóm tắt các chú giải quyết định."
    )
    source_pages: list[int] = Field(
        ...,
        description="Danh sách các trang trong tài liệu chứa thông tin liên quan được trích dẫn."
    )


class HeadingProductAnalysis(BaseModel):
    product_dna: str = Field(
        ...,
        description="Tóm tắt bản chất sản phẩm (Tên + Chất liệu + Công dụng + Tình trạng/Bao bì)."
    )
    key_attribute: str = Field(
        ...,
        description="Yếu tố quyết định: Định danh, Chất liệu, hay Chức năng."
    )


class SelectedHeading(BaseModel):
    heading_id: str = Field(
        ...,
        description="ID của Heading được chọn (ví dụ: '84.07')."
    )
    heading_title: str = Field(
        ...,
        description="Tiêu đề đầy đủ của Heading được chọn."
    )
    rationale: str = Field(
        ...,
        description="Lập luận lựa chọn Heading."
    )
    legal_basis: str = Field(
        ...,
        description="Trích dẫn cụ thể nguyên văn câu Chú giải pháp lý hoặc nội dung Nhóm hỗ trợ quyết định."
    )
    gir_application: str = Field(
        ...,
        description="Ghi chú quy tắc GIR làm cơ sở chốt hạ."
    )


class RejectedHeading(BaseModel):
    heading_id: str = Field(
        ...,
        description="ID của Heading bị loại."
    )
    reason: str = Field(
        ...,
        description="Lý do loại Heading."
    )


class HeadingClassification(BaseModel):
    product_analysis: HeadingProductAnalysis = Field(
        ...,
        description="Phân tích tóm tắt bản chất sản phẩm."
    )
    selected_heading: SelectedHeading = Field(
        ...,
        description="Heading được chọn cuối cùng."
    )
    rejected_headings: list[RejectedHeading] = Field(
        ...,
        description="Danh sách Heading bị loại."
    )
    content_of_explanatory_notes: str = Field(
        ...,
        description="Trích đoạn/tóm tắt các chú giải quyết định."
    )
    source_pages: list[int] = Field(
        ...,
        description="Danh sách các trang trong tài liệu chứa thông tin liên quan được trích dẫn."
    )


class SubheadingProductAnalysis(BaseModel):
    product_dna: str = Field(
        ...,
        description="Tóm tắt bản chất sản phẩm (Tên + Chất liệu + Công dụng + Tình trạng/Bao bì)."
    )
    key_attribute: str = Field(
        ...,
        description="Yếu tố quyết định để phân loại."
    )


class Gir6HierarchyAnalysis(BaseModel):
    selected_one_dash: str = Field(
        ...,
        description="Trích dẫn văn bản của nhánh 1 gạch '-' được chọn."
    )
    reasoning_one_dash: str = Field(
        ...,
        description="Lý do chọn nhánh 1 gạch này so với các nhánh 1 gạch khác."
    )


class SelectedSubheading(BaseModel):
    subheading_id: str = Field(
        ...,
        description="ID của Subheading được chọn (ví dụ: '8407.10')."
    )
    subheading_title: str = Field(
        ...,
        description="Văn bản chi tiết của phân nhóm 6 số."
    )
    rationale: str = Field(
        ...,
        description="Lập luận lựa chọn Subheading."
    )
    legal_basis: str = Field(
        ...,
        description="Trích dẫn cụ thể Chú giải Phân nhóm hoặc nội dung văn bản Phân nhóm."
    )
    gir_application: str = Field(
        ...,
        description="Ghi chú quy tắc GIR làm cơ sở chốt hạ."
    )


class RejectedSubheading(BaseModel):
    subheading_id: str = Field(
        ...,
        description="ID của Subheading bị loại."
    )
    reason: str = Field(
        ...,
        description="Lý do loại Subheading."
    )


class SubheadingClassification(BaseModel):
    product_analysis: SubheadingProductAnalysis = Field(
        ...,
        description="Phân tích tóm tắt bản chất sản phẩm."
    )
    gir6_hierarchy_analysis: Gir6HierarchyAnalysis = Field(
        ...,
        description="Phân tích lựa chọn nhánh 1 gạch theo GIR 6."
    )
    selected_subheading: SelectedSubheading = Field(
        ...,
        description="Subheading được chọn cuối cùng."
    )
    rejected_subheadings: list[RejectedSubheading] = Field(
        ...,
        description="Danh sách Subheading bị loại."
    )
    content_of_explanatory_notes: str = Field(
        ...,
        description="Trích đoạn nguyên văn các chú giải quyết định."
    )
    source_pages: list[int] = Field(
        ...,
        description="Danh sách các trang trong tài liệu chứa thông tin liên quan được trích dẫn."
    )
