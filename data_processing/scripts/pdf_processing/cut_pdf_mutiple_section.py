from PyPDF2 import PdfReader, PdfWriter

def cut_pdf_by_list(input_path, cut_list):
    """
    Cắt PDF theo danh sách các đoạn trang.
    Mỗi phần tử trong cut_list là dict dạng:
    {
        "start": số_trang_bắt_đầu (int),
        "end": số_trang_kết_thúc (int),
        "filename": tên_file_pdf_đầu_ra (str)
    }
    """
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    print(f"📘 Tổng số trang trong file: {total_pages}\n")

    for item in cut_list:
        start_page = item["start"]
        end_page = item["end"]
        output_path = item["output_file"]

        start_index = start_page - 1
        end_index = end_page

        if start_index < 0 or end_index > total_pages or start_index >= end_index:
            print(f"⚠️ Bỏ qua {output_path}: Phạm vi {start_page}–{end_page} không hợp lệ.")
            continue

        writer = PdfWriter()
        for i in range(start_index, end_index):
            writer.add_page(reader.pages[i])

        with open(output_path, "wb") as f:
            writer.write(f)

        print(f"✅ Đã tạo file: {output_path} (từ trang {start_page} → {end_page})")


if __name__ == "__main__":
    print("=== ✂️ CẮT FILE PDF THEO DANH SÁCH ===")
    input_file = "./full_explanatory_notes.pdf"

    # Danh sách các đoạn muốn cắt
    cut_list = [
        {"start": 775, "end": 851, "output_file": "VII.pdf"},
        {"start": 1333, "end": 1511, "output_file": "XV.pdf"},
        {"start": 1511, "end": 1911, "output_file": "XVI.pdf"},
        {"start": 1911, "end": 1975, "output_file": "XVII.pdf"},
        {"start": 1975, "end": 2126, "output_file": "XVIII.pdf"},
        {"start": 2135, "end": 2191, "output_file": "XX.pdf"},
    ]

    try:
        cut_pdf_by_list(input_file, cut_list)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
