from PyPDF2 import PdfReader, PdfWriter

def cut_pdf(input_path, output_path, start_page, end_page):
    """
    Cắt PDF từ trang start_page đến end_page (tính từ 1, inclusive).
    Lưu ra file PDF mới tại output_path.
    """
    reader = PdfReader(input_path)
    writer = PdfWriter()

    start_index = start_page - 1
    end_index = end_page

    total_pages = len(reader.pages)
    if start_index < 0 or end_index > total_pages or start_index >= end_index:
        raise ValueError(f"Phạm vi trang không hợp lệ. PDF có {total_pages} trang.")

    for i in range(start_index, end_index):
        writer.add_page(reader.pages[i])

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"✅ Đã tạo file: {output_path} (từ trang {start_page} → {end_page})")


if __name__ == "__main__":
    print("=== ✂️ CẮT FILE PDF ===")
    input_file = "./full_explanatory_notes.pdf"
    start_page = 1508
    end_page = 1911
    output_file = "XVI.pdf" 
    
    try:
        cut_pdf(input_file, output_file, start_page, end_page)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
