"""Constants and column mappings for Excel processing

Contains:
- Excel column name to model field mappings
- Numeric field definitions
- Style constants for Excel output
"""

from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


# ============================================================================
# COLUMN MAPPING
# ============================================================================

EXCEL_COLUMN_MAP = {
    "STT": "stt", "stt": "stt", "S T T": "stt",
    "Số TK": "so_tk", "So TK": "so_tk", "Số tờ khai": "so_tk",
    "Ngày ĐK": "ngay_dk", "Ngay DK": "ngay_dk", "Ngày đăng ký": "ngay_dk",
    "Mã loại hình": "ma_loai_hinh", "Ma loai hinh": "ma_loai_hinh", "Loại hình": "ma_loai_hinh",
    "Mã địa điểm đích": "ma_dia_diem_dich",
    "Tên địa điểm đích cho vận chuyển bảo thuế": "ten_dia_diem_dich",
    "Tên địa điểm đích": "ten_dia_diem_dich",
    "Địa điểm dỡ hàng": "dia_diem_do_hang",
    "Mã hiệu PTVC": "ma_hieu_ptvc",
    "Ngày khởi hành vận chuyển": "ngay_khoi_hanh",
    "Ký hiệu và số hiệu bao bì": "ky_hieu_so_hieu_bao_bi",
    "Tỷ giá thanh toán": "ty_gia_thanh_toan", "Ty gia thanh toan": "ty_gia_thanh_toan",
    "Đơn vị tiền tệ": "don_vi_tien_te", "Don vi tien te": "don_vi_tien_te",
    "Số lượng kiện": "so_luong_kien",
    "Mã ĐVT kiện": "ma_dvt_kien",
    "Trọng lượng": "trong_luong",
    "Mã ĐVT trọng lượng": "ma_dvt_trong_luong",
    "Số quản lý nội bộ": "so_quan_ly_noi_bo",
    "Điều kiện giá hóa đơn": "dieu_kien_gia_hoa_don",
    "Dieu kien gia hoa don": "dieu_kien_gia_hoa_don",
    "ĐKGHĐ": "dieu_kien_gia_hoa_don",
    "Ghi chú": "ghi_chu",
    "STT hàng": "stt_hang",
    "Mã NPL/SP": "ma_npl_sp", "Ma NPL/SP": "ma_npl_sp",
    "Mã NPL": "ma_npl_sp", "Mã SP": "ma_npl_sp",
    "Mã HS": "ma_hs", "Ma HS": "ma_hs", "HS Code": "ma_hs",
    "Tên hàng": "ten_hang", "Ten hang": "ten_hang",
    "Xuất xứ": "xuat_xu", "Xuat xu": "xuat_xu",
    "Đơn giá": "don_gia", "Don gia": "don_gia",
    "Đơn giá tính thuế": "don_gia_tinh_thue", "Don gia tinh thue": "don_gia_tinh_thue",
    "Tổng số lượng": "tong_so_luong", "Tong so luong": "tong_so_luong",
    "Đơn vị tính": "don_vi_tinh", "Don vi tinh": "don_vi_tinh",
    "Tổng số lượng 2": "tong_so_luong_2",
    "Đơn vị tính 2": "don_vi_tinh_2",
    "Trị giá NT": "tri_gia_nt", "Tri gia NT": "tri_gia_nt",
    "Tổng trị giá": "tong_tri_gia", "Tong tri gia": "tong_tri_gia",
    "Mã biểu thuế XNK": "ma_bieu_thue_xnk",
    "Thuế suất XNK": "thue_suat_xnk",
    "Tiền thuế XNK": "tien_thue_xnk",
    "Số tiền miễn thuế XNK": "so_tien_mien_thue_xnk",
    "Thuế suất TV": "thue_suat_tv",
    "Tiền thuế TV": "tien_thue_tv",
    "Thuế suất PB": "thue_suat_pb",
    "Tiền thuế PB": "tien_thue_pb",
    "Thuế suất TTĐB": "thue_suat_ttdb",
    "Tiền thuế TTĐB": "tien_thue_ttdb",
    "Thuế suất BVMT": "thue_suat_bvmt",
    "Tiền thuế MT": "tien_thue_mt",
    "Thuế suất VA": "thue_suat_va",
    "Tiền thuế VAT": "tien_thue_vat",
    "Tổng tiền thuế": "tong_tien_thue",
    "Mã doanh nghiệp": "ma_doanh_nghiep", "Ma doanh nghiep": "ma_doanh_nghiep",
    "Tên doanh nghiệp": "ten_doanh_nghiep", "Ten doanh nghiep": "ten_doanh_nghiep",
    "Tên đối tác": "ten_doi_tac", "Ten doi tac": "ten_doi_tac",
    "Số hóa đơn": "so_hoa_don", "So hoa don": "so_hoa_don",
    "Ngày hóa đơn": "ngay_hoa_don", "Ngay hoa don": "ngay_hoa_don",
    "Số hợp đồng": "so_hop_dong", "So hop dong": "so_hop_dong",
    "Ngày hợp đồng": "ngay_hop_dong", "Ngay hop dong": "ngay_hop_dong",
    "Trọng lượng hàng": "trong_luong_hang", "Trong luong hang": "trong_luong_hang",
    "EY'S NOTE": "ey_note", "EYS NOTE": "ey_note", "EY NOTE": "ey_note",
}

# Numeric fields that need special parsing
NUMERIC_FIELDS = {
    'ty_gia_thanh_toan', 'so_luong_kien', 'trong_luong',
    'don_gia', 'don_gia_tinh_thue', 'tong_so_luong', 'tong_so_luong_2',
    'tri_gia_nt', 'tong_tri_gia', 'thue_suat_xnk', 'tien_thue_xnk',
    'so_tien_mien_thue_xnk', 'thue_suat_tv', 'tien_thue_tv',
    'thue_suat_pb', 'tien_thue_pb', 'thue_suat_ttdb', 'tien_thue_ttdb',
    'thue_suat_bvmt', 'tien_thue_mt', 'thue_suat_va', 'tien_thue_vat',
    'tong_tien_thue', 'trong_luong_hang'
}


# ============================================================================
# EXCEL STYLES
# ============================================================================

# Header styles (dark theme - yellow on black)
HEADER_FONT = Font(name="Arial", bold=True, color="FFE600", size=10)
HEADER_FILL = PatternFill(start_color="2E2E38", end_color="2E2E38", fill_type="solid")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Cell styles
CELL_FONT = Font(name="Arial", size=10)
# Text columns (Mã NPL, Tên Hàng, etc.) - always left aligned
CELL_ALIGNMENT = Alignment(horizontal="left", vertical="center", wrap_text=True)
# Numeric columns (Tổng trị giá, Đơn giá, etc.) - always right aligned
NUMBER_ALIGNMENT = Alignment(horizontal="right", vertical="center", wrap_text=True)
# Center alignment for STT, flags, short codes
CENTER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Border styles
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)
NO_BORDER = Border()

# Link style
LINK_FONT = Font(name="Arial", size=10, color="0563C1", underline="single")

