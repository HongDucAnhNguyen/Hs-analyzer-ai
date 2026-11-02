"""Pydantic models for Report Service

Models for Excel data analysis and report generation:
- Input model: Excel row data from TKR report
- Output models: HS Consistency, Value Variance, and NTM reports
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class FlowType(str, Enum):
    """Flow type - Import (Nhập) or Export (Xuất)"""
    NHAP = "Nhập"
    XUAT = "Xuất"
    UNKNOWN = "Unknown"


# Mapping of Mã loại hình to Flow type
# Based on Vietnam Customs regulations
MA_LOAI_HINH_TO_FLOW = {
    # ==========================================
    # NHẬP KHẨU (Import) codes
    # ==========================================
    # Loại A - Nhập khẩu kinh doanh
    "A11": FlowType.NHAP,  # Nhập kinh doanh tiêu dùng
    "A12": FlowType.NHAP,  # Nhập kinh doanh sản xuất
    "A21": FlowType.NHAP,  # Chuyển tiêu thụ nội địa từ nguồn tạm nhập
    "A31": FlowType.NHAP,  # Nhập khẩu hàng hóa đã xuất khẩu
    "A41": FlowType.NHAP,  # Nhập kinh doanh của doanh nghiệp thực hiện quyền nhập khẩu
    "A42": FlowType.NHAP,  # Thay đổi mục đích sử dụng hoặc chuyển tiêu thụ nội địa từ các loại hình khác
    "A43": FlowType.NHAP,  # Nhập khẩu hàng hóa thuộc Chương trình ưu đãi thuế
    "A44": FlowType.NHAP,  # Tạm nhập hàng hóa bán tại cửa hàng miễn thuế
    
    # Loại E - DNCX và gia công
    "E11": FlowType.NHAP,  # Nhập nguyên liệu của DNCX từ nước ngoài
    "E13": FlowType.NHAP,  # Nhập hàng hóa khác vào DNCX
    "E15": FlowType.NHAP,  # Nhập nguyên liệu, vật tư của DNCX từ nội địa
    "E21": FlowType.NHAP,  # Nhập nguyên liệu, vật tư để gia công cho thương nhân nước ngoài
    "E23": FlowType.NHAP,  # Nhập nguyên liệu, vật tư gia công từ hợp đồng khác chuyển sang
    "E31": FlowType.NHAP,  # Nhập nguyên liệu sản xuất xuất khẩu
    "E33": FlowType.NHAP,  # Nhập nguyên liệu, vật tư vào kho bảo thuế
    "E41": FlowType.NHAP,  # Nhập sản phẩm thuê gia công ở nước ngoài
    
    # Loại G - Tạm nhập
    "G11": FlowType.NHAP,  # Tạm nhập hàng kinh doanh tạm nhập tái xuất
    "G12": FlowType.NHAP,  # Tạm nhập máy móc, thiết bị phục vụ dự án có thời hạn
    "G13": FlowType.NHAP,  # Tạm nhập miễn thuế
    "G14": FlowType.NHAP,  # Tạm nhập khác
    "G51": FlowType.NHAP,  # Tái nhập hàng hóa đã tạm xuất
    
    # Loại C - Kho ngoại quan và khu phi thuế quan (Nhập)
    "C11": FlowType.NHAP,  # Hàng nước ngoài gửi kho ngoại quan
    "C21": FlowType.NHAP,  # Hàng đưa vào khu phi thuế quan
    
    # Loại H - Khác
    "H11": FlowType.NHAP,  # Hàng nhập khẩu khác
    
    # ==========================================
    # XUẤT KHẨU (Export) codes
    # ==========================================
    # Loại B - Xuất khẩu kinh doanh
    "B11": FlowType.XUAT,  # Xuất kinh doanh
    "B12": FlowType.XUAT,  # Xuất kinh doanh sản phẩm gia công, SXXK, DNCX
    "B13": FlowType.XUAT,  # Xuất sản phẩm gia công cho thương nhân nước ngoài
    
    # Loại C - Xuất (kho ngoại quan, SXXK)
    "C12": FlowType.XUAT,  # Hàng từ kho ngoại quan xuất đi nước ngoài
    "C22": FlowType.XUAT,  # Hàng từ khu phi thuế quan xuất đi nước ngoài
    
    # Loại E - Xuất DNCX
    "E42": FlowType.XUAT,
    "E52": FlowType.XUAT,  # Xuất sản phẩm của DNCX ra nước ngoài
    "E54": FlowType.XUAT,  # Xuất sản phẩm của DNCX vào nội địa
    "E62": FlowType.XUAT,  # Xuất hàng hóa khác của DNCX
    "E82": FlowType.XUAT,  # Xuất sản phẩm của DNCX vào nước ngoài
    
    # Loại G - Tái xuất, tạm xuất
    "G21": FlowType.XUAT,  # Tái xuất hàng kinh doanh tạm nhập tái xuất
    "G22": FlowType.XUAT,  # Tái xuất máy móc, thiết bị phục vụ dự án có thời hạn
    "G23": FlowType.XUAT,  # Tái xuất hàng tạm nhập miễn thuế
    "G24": FlowType.XUAT,  # Tái xuất khác
    "G61": FlowType.XUAT,  # Tái xuất hàng gửi kho ngoại quan
    
    # Loại H - Khác
    "H21": FlowType.XUAT,  # Hàng xuất khẩu khác
}


def get_flow_from_ma_loai_hinh(ma_loai_hinh: Optional[str]) -> FlowType:
    """Get Flow type from Mã loại hình
    
    Args:
        ma_loai_hinh: Type code (e.g., A11, A12, B13, C22)
        
    Returns:
        FlowType.NHAP for import, FlowType.XUAT for export, FlowType.UNKNOWN if not recognized
    """
    return MA_LOAI_HINH_TO_FLOW.get(ma_loai_hinh, FlowType.UNKNOWN)


class ExcelRowData(BaseModel):
    """Model for a single row from the input Excel file (TKR Report)
    
    Contains all relevant columns from the customs declaration report.
    """
    stt: Optional[str] = Field(None, description="STT - Số thứ tự")
    so_tk: Optional[str] = Field(None, description="Số TK - Số tờ khai")
    ngay_dk: Optional[str] = Field(None, description="Ngày ĐK - Ngày đăng ký")
    ma_loai_hinh: Optional[str] = Field(None, description="Mã loại hình")
    ma_dia_diem_dich: Optional[str] = Field(None, description="Mã địa điểm đích")
    ten_dia_diem_dich: Optional[str] = Field(None, description="Tên địa điểm đích cho vận chuyển bảo thuế")
    dia_diem_do_hang: Optional[str] = Field(None, description="Địa điểm dỡ hàng")
    ma_hieu_ptvc: Optional[str] = Field(None, description="Mã hiệu PTVC")
    ngay_khoi_hanh: Optional[str] = Field(None, description="Ngày khởi hành vận chuyển")
    ky_hieu_so_hieu_bao_bi: Optional[str] = Field(None, description="Ký hiệu và số hiệu bao bì")
    ty_gia_thanh_toan: Optional[float] = Field(None, description="Tỷ giá thanh toán")
    don_vi_tien_te: Optional[str] = Field(None, description="Đơn vị tiền tệ")
    so_luong_kien: Optional[float] = Field(None, description="Số lượng kiện")
    ma_dvt_kien: Optional[str] = Field(None, description="Mã ĐVT kiện")
    trong_luong: Optional[float] = Field(None, description="Trọng lượng")
    ma_dvt_trong_luong: Optional[str] = Field(None, description="Mã ĐVT trọng lượng")
    so_quan_ly_noi_bo: Optional[str] = Field(None, description="Số quản lý nội bộ")
    dieu_kien_gia_hoa_don: Optional[str] = Field(None, description="Điều kiện giá hóa đơn")
    ghi_chu: Optional[str] = Field(None, description="Ghi chú")
    stt_hang: Optional[str] = Field(None, description="STT hàng")
    ma_npl_sp: Optional[str] = Field(None, description="Mã NPL/SP")
    ma_hs: Optional[str] = Field(None, description="Mã HS")
    ten_hang: Optional[str] = Field(None, description="Tên hàng")
    xuat_xu: Optional[str] = Field(None, description="Xuất xứ")
    don_gia: Optional[float] = Field(None, description="Đơn giá")
    don_gia_tinh_thue: Optional[float] = Field(None, description="Đơn giá tính thuế")
    tong_so_luong: Optional[float] = Field(None, description="Tổng số lượng")
    don_vi_tinh: Optional[str] = Field(None, description="Đơn vị tính")
    tong_so_luong_2: Optional[float] = Field(None, description="Tổng số lượng 2")
    don_vi_tinh_2: Optional[str] = Field(None, description="Đơn vị tính 2")
    tri_gia_nt: Optional[float] = Field(None, description="Trị giá NT")
    tong_tri_gia: Optional[float] = Field(None, description="Tổng trị giá")
    ma_bieu_thue_xnk: Optional[str] = Field(None, description="Mã biểu thuế XNK")
    thue_suat_xnk: Optional[float] = Field(None, description="Thuế suất XNK")
    tien_thue_xnk: Optional[float] = Field(None, description="Tiền thuế XNK")
    so_tien_mien_thue_xnk: Optional[float] = Field(None, description="Số tiền miễn thuế XNK")
    thue_suat_tv: Optional[float] = Field(None, description="Thuế suất TV")
    tien_thue_tv: Optional[float] = Field(None, description="Tiền thuế TV")
    thue_suat_pb: Optional[float] = Field(None, description="Thuế suất PB")
    tien_thue_pb: Optional[float] = Field(None, description="Tiền thuế PB")
    thue_suat_ttdb: Optional[float] = Field(None, description="Thuế suất TTĐB")
    tien_thue_ttdb: Optional[float] = Field(None, description="Tiền thuế TTĐB")
    thue_suat_bvmt: Optional[float] = Field(None, description="Thuế suất BVMT")
    tien_thue_mt: Optional[float] = Field(None, description="Tiền thuế MT")
    thue_suat_va: Optional[float] = Field(None, description="Thuế suất VA")
    tien_thue_vat: Optional[float] = Field(None, description="Tiền thuế VAT")
    tong_tien_thue: Optional[float] = Field(None, description="Tổng tiền thuế")
    ma_doanh_nghiep: Optional[str] = Field(None, description="Mã doanh nghiệp")
    ten_doanh_nghiep: Optional[str] = Field(None, description="Tên doanh nghiệp")
    ten_doi_tac: Optional[str] = Field(None, description="Tên đối tác")
    so_hoa_don: Optional[str] = Field(None, description="Số hóa đơn")
    ngay_hoa_don: Optional[str] = Field(None, description="Ngày hóa đơn")
    so_hop_dong: Optional[str] = Field(None, description="Số hợp đồng")
    ngay_hop_dong: Optional[str] = Field(None, description="Ngày hợp đồng")
    trong_luong_hang: Optional[float] = Field(None, description="Trọng lượng hàng")
    ey_note: Optional[str] = Field(None, description="EY'S NOTE")
    
    # Preprocess fields (from item code matching)
    source: Optional[str] = Field(None, description="Source - matching source (from preprocess)")
    item: Optional[str] = Field(None, description="Item / Final Item Code (from preprocess)")
    
    # Computed field
    flow: Optional[str] = Field(None, description="Flow - Nhập/Xuất (computed from Mã loại hình)")
    
    def compute_flow(self) -> str:
        """Compute Flow from Mã loại hình"""
        return get_flow_from_ma_loai_hinh(self.ma_loai_hinh).value


# ============================================================================
# HS Consistency Report Models
# ============================================================================

class HSConsistencyItem(BaseModel):
    """Single item in HS Consistency report
    
    Only includes NPL/SP with 2+ different HS codes (inconsistent).
    Grouped by Flow -> Mã loại hình -> Mã NPL/SP -> Mã HS
    """
    flow: str = Field(..., description="Flow - Nhập/Xuất")
    ma_loai_hinh: Optional[str] = Field(None, description="Mã loại hình")
    ma_npl_sp: Optional[str] = Field(None, description="Mã NPL/SP")
    ma_hs: Optional[str] = Field(None, description="Mã HS")
    ten_hang: Optional[str] = Field(None, description="Tên hàng")
    total: float = Field(0.0, description="Total (Sum of Tổng trị giá)")
    tax: Optional[str] = Field(None, description="Tax rate from tariff_rates.json (kept as string to preserve format)")
    impact_amount: Optional[float] = Field(None, description="Impact = Total × (Max tax - current tax)")
    to_pic: Optional[str] = Field(None, description="x if in Top 10 by impact")
    impact_refer: Optional[str] = Field(None, description="IP1-IP10 for Top 10 products by total impact")
    
    class Config:
        json_schema_extra = {
            "example": {
                "flow": "Nhập",
                "ma_loai_hinh": "A12",
                "ma_npl_sp": "CKSRYX104K50-T",
                "ma_hs": "85322400",
                "ten_hang": "Tụ gốm 2 lớp",
                "total": 541377233.0,
                "tax": 0.0,
                "impact_amount": 27068861.66,
                "to_pic": "x",
                "impact_refer": "IP1"
            }
        }


class HSConsistencyReport(BaseModel):
    """HS Consistency Report
    
    Contains aggregated data for HS consistency analysis.
    """
    items: List[HSConsistencyItem] = Field(..., description="List of grouped items")
    total_items: int = Field(..., description="Total number of items")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total_items": 0
            }
        }


# ============================================================================
# Value Variance Report Models
# ============================================================================

class ValueVarianceItem(BaseModel):
    """Single item in Value Variance report
    
    Represents aggregated data grouped by Flow -> Điều kiện giá hóa đơn -> Mã NPL/SP -> Tên đối tác
    """
    flow: str = Field(..., description="Flow - Nhập/Xuất")
    dieu_kien_gia_hoa_don: Optional[str] = Field(None, description="Điều kiện giá hóa đơn")
    ma_npl_sp: Optional[str] = Field(None, description="Mã NPL/SP")
    ten_doi_tac: Optional[str] = Field(None, description="Tên đối tác")
    hs_code_max_duty: Optional[str] = Field(None, description="HS Code (maximum duty rate)")
    import_duty_rate_max: Optional[float] = Field(None, description="Import Duty rate (max)")
    tong_so_luong_min: Optional[float] = Field(None, description="Tổng số lượng (ứng Đơn giá tính thuế min) - for Impact calculation")
    sum_tong_so_luong: Optional[float] = Field(None, description="Sum of Tổng số lượng (total of all quantities)")
    min_don_gia_tinh_thue: Optional[float] = Field(None, description="Min of Đơn giá tính thuế")
    max_don_gia_tinh_thue: Optional[float] = Field(None, description="Max of Đơn giá tính thuế")
    sum_don_gia_tinh_thue: Optional[float] = Field(None, description="Sum of Đơn giá tính thuế (for average calculation)")
    count_don_gia_tinh_thue: Optional[int] = Field(None, description="Count of Đơn giá tính thuế records (for average calculation)")
    impact_amount: Optional[float] = Field(None, description="Impact = (Max - Min) × Duty rate × Quantity")
    to_pic: Optional[str] = Field(None, description="x if in Top 10 by impact")
    impact_refer: Optional[str] = Field(None, description="IP1-IP10 for Top 10 products by total impact")
    
    class Config:
        json_schema_extra = {
            "example": {
                "flow": "Nhập",
                "dieu_kien_gia_hoa_don": "DAP",
                "ma_npl_sp": "T903-000055",
                "ten_doi_tac": "CONG TY ABC",
                "hs_code_max_duty": "85322400",
                "import_duty_rate_max": 5.0,
                "tong_so_luong_min": 1000.0,
                "min_don_gia_tinh_thue": 5163244.0,
                "max_don_gia_tinh_thue": 6100248.0,
                "impact_amount": 46850200.0,
                "to_pic": "x",
                "impact_refer": "IP1"
            }
        }


class ValueVarianceReport(BaseModel):
    """Value Variance Report
    
    Contains aggregated data for value variance analysis.
    """
    items: List[ValueVarianceItem] = Field(..., description="List of grouped items")
    total_items: int = Field(..., description="Total number of items")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total_items": 0
            }
        }


# ============================================================================
# Non-Tariff Measures Report Models
# ============================================================================

class NTMItem(BaseModel):
    """Single item in Non-Tariff Measures report
    
    Represents data grouped by QĐ 1357 (Import/Export) -> HS Code
    """
    qd_1357: str = Field(..., description="QĐ 1357 - Import/Export")
    hs_code: str = Field(..., description="Mã HS (6 digits)")
    ma_npl_sp: Optional[str] = Field(None, description="Mã NPL/SP")
    ten_hang: Optional[str] = Field(None, description="Tên hàng")
    train_link: str = Field(default="", description="TRAINS Online link for NTM data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "qd_1357": "Import",
                "hs_code": "722691",
                "ma_npl_sp": "T903-000055",
                "ten_hang": "Tấm thép hợp kim",
                "train_link": "https://trainsonline.unctad.org/detailedSearch?..."
            }
        }


class NTMReport(BaseModel):
    """Non-Tariff Measures Report
    
    Contains NTM data grouped by QĐ 1357 -> HS Code.
    """
    items: List[NTMItem] = Field(..., description="List of NTM items")
    total_items: int = Field(..., description="Total number of items")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total_items": 0
            }
        }


# ============================================================================
# API Request/Response Models
# ============================================================================

class AnalyzeExcelResponse(BaseModel):
    """Response model for analyze-excel endpoint
    
    Returns result_id for downloading generated reports.
    """
    result_id: str = Field(..., description="Unique ID for this result set")
    hs_consistency_summary: HSConsistencyReport = Field(..., description="HS Consistency report summary")
    value_variance_summary: ValueVarianceReport = Field(..., description="Value Variance report summary")
    total_rows_processed: int = Field(..., description="Total rows processed from input Excel")
    
    class Config:
        json_schema_extra = {
            "example": {
                "result_id": "550e8400-e29b-41d4-a716-446655440000",
                "hs_consistency_summary": {"items": [], "total_items": 0},
                "value_variance_summary": {"items": [], "total_items": 0},
                "total_rows_processed": 100
            }
        }


class ExportReportRequest(BaseModel):
    """Request model for export report endpoint"""
    result_id: str = Field(..., description="Result ID from analyze response")
    report_type: str = Field(
        "both",
        description="Report type: 'hs_consistency', 'value_variance', or 'both'"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "result_id": "550e8400-e29b-41d4-a716-446655440000",
                "report_type": "both"
            }
        }



