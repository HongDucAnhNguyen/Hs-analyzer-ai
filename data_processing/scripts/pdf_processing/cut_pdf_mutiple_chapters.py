import os
from PyPDF2 import PdfReader, PdfWriter

def cut_pdf_by_list(input_path, cut_list):
    """
    Cắt PDF theo danh sách các đoạn trang.
    Mỗi phần tử trong cut_list là dict dạng:
    {
        "start": int,                # Trang bắt đầu
        "end": int,                  # Trang kết thúc
        "prefix_output_file": str    # Prefix cho tên file đầu ra
    }
    """
    # Lấy tên file input (không bao gồm phần mở rộng)
    input_filename = os.path.basename(input_path)
    input_name, _ = os.path.splitext(input_filename)

    # Tạo folder output theo tên file input
    output_folder = os.path.join(os.path.dirname(input_path), "chapters")
    os.makedirs(output_folder, exist_ok=True)

    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    print(f"📘 Tổng số trang trong file '{input_filename}': {total_pages}\n")

    for item in cut_list:
        start_page = item["start"]
        end_page = item["end"]
        prefix = item.get("prefix_output_file", "")

        # Tên file output theo format mong muốn
        output_filename = f"{prefix}{input_name}.pdf"
        output_path = os.path.join(output_folder, output_filename)

        start_index = start_page - 1
        end_index = end_page

        if start_index < 0 or end_index > total_pages or start_index >= end_index:
            print(f"⚠️ Bỏ qua {output_filename}: Phạm vi {start_page}–{end_page} không hợp lệ.")
            continue

        writer = PdfWriter()
        for i in range(start_index, end_index):
            writer.add_page(reader.pages[i])

        with open(output_path, "wb") as f:
            writer.write(f)

        print(f"✅ Đã tạo file: {output_path} (từ trang {start_page} → {end_page})")

    print(f"\n📂 Hoàn tất! Tất cả file output được lưu tại: '{output_folder}'")

def process_pdf_folder(input_folder, cut_list):
    """
    Duyệt toàn bộ file PDF trong folder và cắt từng file theo cut_list.
    """
    if not os.path.isdir(input_folder):
        raise ValueError(f"❌ Đường dẫn '{input_folder}' không phải là thư mục hợp lệ!")

    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"⚠️  Không tìm thấy file PDF nào trong thư mục: {input_folder}")
        return

    print(f"🔍 Tìm thấy {len(pdf_files)} file PDF trong '{input_folder}'")

    for filename in pdf_files:
        print(f"filename '{filename}'")
        cut = cut_list.get(filename)
        if cut is None:
            continue
        print(f"current list '{cut}'")
        file_path = os.path.join(input_folder, filename)
        try:
            cut_pdf_by_list(file_path, cut_list[filename])
        except Exception as e:
            print(f"❌ Lỗi khi xử lý '{filename}': {e}")

    print("\n🎉 Tất cả file trong thư mục đã được xử lý xong!")

if __name__ == "__main__":
    print("=== ✂️ CẮT FILE PDF THEO DANH SÁCH ===")
    input_folder = "./sections"

    # Danh sách các đoạn muốn cắt
    cut_list = {
        "Section_VII.pdf": [
            {"start": 2, "end": 47, "prefix_output_file": "Chapter_39_"},
            {"start": 47, "end": 77, "prefix_output_file": "Chapter_40_"},
        ],
        "Section_XV.pdf": [
            {"start": 7, "end": 50, "prefix_output_file": "Chapter_72_"},
            {"start": 50, "end": 87, "prefix_output_file": "Chapter_73_"},
            {"start": 87, "end": 102, "prefix_output_file": "Chapter_74_"},
            {"start": 102, "end": 109, "prefix_output_file": "Chapter_75_"},
            {"start": 109, "end": 119, "prefix_output_file": "Chapter_76_"},  # File data đang bị thiếu chương 77
            {"start": 119, "end": 123, "prefix_output_file": "Chapter_78_"},
            {"start": 123, "end": 128, "prefix_output_file": "Chapter_79_"},
            {"start": 128, "end": 132, "prefix_output_file": "Chapter_80_"},
            {"start": 132, "end": 146, "prefix_output_file": "Chapter_81_"},
            {"start": 146, "end": 165, "prefix_output_file": "Chapter_82_"},
            {"start": 165, "end": 179, "prefix_output_file": "Chapter_83_"},
        ],
        "Section_XVI.pdf": [
            {"start": 11, "end": 280, "prefix_output_file": "Chapter_84_"},
            {"start": 280, "end": 401, "prefix_output_file": "Chapter_85_"},
        ],
        "Section_XVII.pdf": [
            {"start": 7, "end": 20, "prefix_output_file": "Chapter_86_"},
            {"start": 20, "end": 50, "prefix_output_file": "Chapter_87_"},
            {"start": 50, "end": 58, "prefix_output_file": "Chapter_88_"},
            {"start": 58, "end": 65, "prefix_output_file": "Chapter_89_"},
        ],
        "Section_XVIII.pdf": [
            {"start": 2, "end": 118, "prefix_output_file": "Chapter_90_"},
            {"start": 118, "end": 139, "prefix_output_file": "Chapter_91_"},
            {"start": 139, "end": 152, "prefix_output_file": "Chapter_92_"},
        ],
        "Section_XX.pdf": [
            {"start": 1, "end": 16, "prefix_output_file": "Chapter_94_"},
            {"start": 17, "end": 32, "prefix_output_file": "Chapter_95_"},
            {"start": 32, "end": 57, "prefix_output_file": "Chapter_96_"},
        ]
    }

    try:
        process_pdf_folder(input_folder, cut_list)
    except Exception as e:
        print(f"❌ Lỗi tổng quát: {e}")
