from pydantic import BaseModel, Field
from typing import List, Optional, Any

class HSCodeMetadata(BaseModel):
    source_pages: List[int] = Field(
        ...,
        description="Danh sách các trang trong tài liệu chứa thông tin liên quan được trích dẫn."
    )
    chapter: Optional[str] = Field(None, description="HS chapter to which the code belongs.")
    heading: Optional[str] = Field(None, description="4-digit HS heading (e.g., '87.08').")
    file_name: Optional[str] = Field(None, description="Name of the source file.")
    file_path: Optional[str] = Field(None, description="Full path to the source file.")
    title: Optional[str] = Field(None, description="Title or heading in the document.")


class HSCodeResult(BaseModel):
    subheading_ids: List[str] = Field(
        ...,
        description="ID của Sub-Heading được phân loại (danh sách các mã HS code, ví dụ: ['0301.99.31', '0301.99.32'])."
    )
    reason: str = Field(
        ...,
        description="Giải thích ngắn gọn tại sao query lại thuộc về Sub-Heading này."
    )
    content_of_citation: str = Field(
        ...,
        description="Trích dẫn hoặc tóm tắt nội dung trong file liên quan trực tiếp đến sản phẩm."
    )
    metadata: HSCodeMetadata = Field(
        ...,
        description="Metadata chứa thông tin nguồn của HS code bao gồm source_pages và các thông tin khác."
    )


class HsCodeOutput(BaseModel):
    results: List[HSCodeResult] = Field(
        ...,
        description="Danh sách các kết quả phân loại HS code, sắp xếp theo độ phù hợp từ cao đến thấp."
    )
