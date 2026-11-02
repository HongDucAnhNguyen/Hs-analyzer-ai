import fitz  # PyMuPDF
import re
import os

def extract_headings_from_pdf(doc, filename, verbose=False):
    """
    Trích xuất thông tin heading từ một file PDF của chương Chú giải chi tiết HS (Phiên bản sửa lỗi).

    Hàm này đã được cập nhật để:
    1. Xử lý chính xác các trường hợp heading có tiêu đề nằm ở dòng tiếp theo.
    2. Ghi nhận cả những heading không có tiêu đề trên cùng một dòng.
    3. Vẫn đảm bảo tính duy nhất và chính xác của heading_code.

    Args:
        pdf_path: Đường dẫn đến file PDF cần xử lý.

    Returns:
        Một danh sách các dictionary, mỗi dictionary chứa thông tin về một heading.
    """
    
    # Bước 1: Khởi tạo các biến và định nghĩa Regular Expression (Regex)
    found_headings = []
    
    # Mẫu Regex được cập nhật:
    # - Sử dụng (.*) thay vì (.+) để cho phép title có thể rỗng.
    #   Điều này rất quan trọng cho các heading mà tiêu đề nằm ở dòng tiếp theo.
    heading_regex = re.compile(
        r"(?m)^(?!(?:\d{2}\.\d{2}\.\d{2}|\d{4}\.\d{2}))"  # loại bỏ subheading như 12.34.56 hoặc 1234.56
        r"^[\[\(\s]*"              # Bắt đầu dòng, khớp các ký tự mở tùy chọn
        r"(\d{2})\s?\.?\s?(\d{2})" # Chụp 2 nhóm 2 chữ số (lõi của heading_code)
        r"[\s\.\-–\]]"             # Khớp các ký tự phân tách hoặc đóng tùy chọn
        r"\s*"                     # Khớp khoảng trắng sau mã
        r"(.*)"                    # Chụp phần còn lại của dòng (có thể rỗng)
    )

    print(f"Đang xử lý {len(doc)} trang từ file '{filename}'...")

    # --- Xác định prefix chương từ filename ---
    # Ví dụ: Chapter_80_Section_XV → prefix = "80"
    chapter_match = re.search(r"Chapter_(\d{2})", filename)
    chapter_prefix = chapter_match.group(1) if chapter_match else None

    for page_num, page in enumerate(doc, start=1):
        blocks = sorted(page.get_text("blocks"), key=lambda b: b[1])

        for block in blocks:
            text = block[4].strip()
            if not text:
                continue

            # Bước 3: Áp dụng Regex để tìm tiêu đề Heading
            first_line = text.split('\n')[0]
            match = heading_regex.match(first_line)

            if match:
                # Bước 4: Chuẩn hóa và Trích xuất dữ liệu nếu khớp
                group1, group2, title_part = match.groups()
                heading_code = f"{group1}.{group2}"

                if group1 != chapter_prefix:
                    # Bỏ qua nếu heading không thuộc chapter hiện tại
                    if verbose:
                        print(f"[SKIP] {heading_code} (chapter {group1}) not in file chapter_{chapter_prefix}")
                    continue

                heading_title = title_part.strip()
                y_position = block[1]

                found_headings.append({
                    "heading_code": heading_code,
                    "start_page": page_num,
                    "heading_title": heading_title,
                    "pos": y_position,
                })
    
    print(f"Đã tìm thấy tổng cộng {len(found_headings)} heading tiềm năng. Đang lọc để lấy kết quả duy nhất...")

    # Bước 5: Hậu xử lý để đảm bảo mỗi heading_code là duy nhất
    # Logic này đảm bảo rằng khi một heading_code (ví dụ 84.65) được tìm thấy ở nhiều nơi,
    # chỉ có lần xuất hiện đầu tiên (với start_page đúng) được giữ lại.
    unique_headings = {}
    for heading in found_headings:
        code = heading["heading_code"]
        if code not in unique_headings:
            pos_matches = [h for h in unique_headings.values() if h["pos"] == heading["pos"]]
            start_pages = [item["start_page"] for item in pos_matches]

            if heading["start_page"] in start_pages:
                continue

            unique_headings[code] = heading

    headings = list(unique_headings.values())

    return headings


def compute_end_pages(headings, total_pages, verbose=False, page_start_threshold=64):
    """
    Tính end_page cho từng heading dựa vào vị trí next heading.
    page_start_threshold: nếu pos <= threshold => coi là 'đầu trang'
    """
    if not headings:
        return []

    # đảm bảo headings đã sắp xếp theo thứ tự xuất hiện (start_page, pos)
    headings = sorted(headings, key=lambda x: (x["start_page"], x["pos"]))
    for i in range(len(headings)):
        cur = headings[i]
        cur_start = cur["start_page"]

        if i < len(headings) - 1:
            nxt = headings[i + 1]
            next_start = nxt["start_page"]
            next_pos = nxt["pos"]

            if next_start == cur_start:
                # next heading nằm trong cùng 1 trang
                end_page = next_start
                case = "same_page"
            else:
                # next heading ở trang khác
                # nếu next_pos nhỏ (rất ở đầu trang) => coi là đầu trang
                if next_pos <= page_start_threshold:
                    end_page = max(cur_start, next_start - 1)
                    case = "next_at_page_start"
                else:
                    # next heading ở giữa trang next => include next page
                    end_page = next_start
                    case = "next_in_middle_of_page"
        else:
            # heading cuối cùng -> tới hết file
            end_page = total_pages
            case = "last_heading"

        # bảo đảm hợp lệ
        if end_page < cur_start:
            # fallback: đảm bảo ít nhất 1 trang
            if verbose:
                print(f"[WARN] end_page {end_page} < start_page {cur_start} cho {cur['heading_code']}, sửa về start_page")
            end_page = cur_start
            case = "fixed_to_start"

        # cap to total_pages
        end_page = min(end_page, total_pages)

        headings[i]["end_page"] = end_page
        headings[i]["case"] = case

        if verbose:
            print(f"[LOG] {cur['heading_code']}: start={cur_start} pos={cur['pos']} -> end={end_page} ({case})")

    final_lists = []
    for heading in headings:
        final_lists.append({
            "heading_code": heading["heading_code"],
            "heading_title": heading["heading_title"],
            "start_page": heading["start_page"],
            "end_page": heading["end_page"],
        })

    return final_lists


def cut_pdf_by_headings(input_path, verbose=False):
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        print(f"Lỗi: Không thể mở file PDF tại '{input_path}'. Chi tiết: {e}")
        return []

    base_name = os.path.splitext(os.path.basename(input_path))[0]

    output_folder = os.path.join("data_ver2/headings", f"headings_output_{base_name}")
    os.makedirs(output_folder, exist_ok=True)

    headings = extract_headings_from_pdf(doc, base_name, verbose=verbose)
    if not headings:
        print("⚠️ Không tìm thấy heading nào trong file.")
        return

    headings = compute_end_pages(headings, len(doc), verbose=verbose)

    # Cắt theo từng heading
    for h in headings:
        start = h["start_page"]
        end = h["end_page"]
        heading_code = h["heading_code"]

        # Safety check
        if end < start:
            print(f"⚠️ Bỏ qua {heading_code}: end_page ({end}) < start_page ({start})")
            continue

        new_doc = fitz.open()

        for p in range(start - 1, end):
            new_doc.insert_pdf(doc, from_page=p, to_page=p)

        output_filename = f"Heading_{heading_code}_{base_name}.pdf"
        output_path = os.path.join(output_folder, output_filename)
        new_doc.save(output_path)
        new_doc.close()

        if verbose:
            print(f"✅ {output_filename} (trang {start} → {end})")

    doc.close()

    print(f"\n📂 Hoàn tất! Các file lưu trong: {output_folder}")

def process_pdf_folder(input_folder):
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

    # Duyệt từng file PDF
    for pdf_name in sorted(pdf_files):
        pdf_path = os.path.join(input_folder, pdf_name)
        print(f"\n🚀 Đang xử lý file: {pdf_name}")

        try:
            # Gọi hàm xử lý từng file
            cut_pdf_by_headings(pdf_path, verbose=True)
        except Exception as e:
            print(f"❌ Lỗi khi xử lý '{pdf_name}': {e}")

    print("\n✅ Hoàn tất xử lý toàn bộ file PDF trong thư mục!")


if __name__ == "__main__":
    print("=== ✂️ CẮT FILE PDF THEO DANH SÁCH ===")
    try:
        input_folder = "./data_ver2/chapters"
        process_pdf_folder(input_folder)
    except Exception as e:
        print(f"❌ Lỗi tổng quát: {e}")
