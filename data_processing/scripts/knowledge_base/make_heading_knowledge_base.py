import os
import json
import fitz  # PyMuPDF
import sys
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import google.generativeai as genai
from pathlib import Path
from data_processing.prompts.prompt_extract_knownledge_base import headings

SYSTEM_INSTRUCTION = headings

def configure_gemini_api():
    """Cấu hình API Gemini bằng API key từ biến môi trường."""
    api_key = "AIzaSyDP782-7pBE5APp7xA_uogAoOXf0aC6j1s"
    if not api_key:
        raise ValueError("Biến môi trường GOOGLE_API_KEY chưa được thiết lập.")
    genai.configure(api_key=api_key)

def extract_text_from_pdf(pdf_path: Path, input_name: str) -> str:
    """
    Trích xuất văn bản từ tệp PDF, đánh dấu nội dung của từng trang.

    Args:
        pdf_path: Đường dẫn đến tệp PDF.

    Returns:
        Một chuỗi chứa toàn bộ văn bản từ PDF, với dấu phân cách trang.
    """

    full_text = ""
    with fitz.open(pdf_path) as doc:
        print(f"Đang đọc {len(doc)} trang từ tệp PDF: {input_name}...")
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            full_text += f"==Start of OCR for page {page_num}==\n"
            full_text += text
            full_text += f"\n==End of OCR for page {page_num}==\n\n"
    return full_text

def call_gemini_for_extraction(pdf_text: str) -> dict:
    """
    Gọi API Gemini để trích xuất dữ liệu có cấu trúc từ văn bản PDF.

    Args:
        pdf_text: Văn bản đã được trích xuất từ PDF.

    Returns:
        Một dictionary chứa dữ liệu đã được trích xuất.
    """
    print("Đang gửi yêu cầu đến Gemini API...")
    
    # Sử dụng model có khả năng xử lý context lớn và tuân theo chỉ dẫn tốt
    # 'gemini-2.5-pro' là lựa chọn nhanh và hiệu quả
    model = genai.GenerativeModel(
        'gemini-2.5-pro',
        system_instruction=SYSTEM_INSTRUCTION
    )

    # Cấu hình để yêu cầu output là JSON
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json"
    )

    # Tạo prompt hoàn chỉnh
    prompt = f"Vui lòng phân tích nội dung PDF sau đây và trích xuất dữ liệu theo cấu trúc đã hướng dẫn:\n\n{pdf_text}"

    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        # API trả về một chuỗi JSON, cần phải parse nó
        # Loại bỏ các ký tự ```json và ``` ở đầu và cuối nếu có
        cleaned_json_string = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        return json.loads(cleaned_json_string)

    except Exception as e:
        print(f"Đã xảy ra lỗi khi gọi Gemini API: {e}")
        # In ra nội dung phản hồi để debug nếu có lỗi
        if 'response' in locals() and hasattr(response, 'text'):
            print("Phản hồi thô từ API:", response.text)
        return None
    
def extract_heading_id_from_filename(filename: Path) -> str | None:
    """
    Sử dụng regex để tìm và trích xuất heading ID (ví dụ: '39.01') từ tên file.
    """
    # Pattern này tìm một chuỗi có dạng XX.XX
    match = re.search(r'(\d{2}\.\d{2})', filename)
    if match:
        return match.group(1)
    return None

def filter_json_by_heading_id(data, target_id: str):
    """
    Lọc dữ liệu JSON. Xử lý trường hợp data là một object hoặc một list các object.
    Chỉ trả về object duy nhất có heading_id trùng khớp.
    """
    if isinstance(data, list):
        # Nếu API trả về một danh sách, tìm đối tượng chính xác
        for item in data:
            if isinstance(item, dict) and item.get("heading_id") == target_id:
                return item # Trả về đối tượng đầu tiên tìm thấy
    elif isinstance(data, dict):
        # Nếu API trả về một đối tượng duy nhất, kiểm tra nó
        if data.get("heading_id") == target_id:
            return data
    # Trả về None nếu không tìm thấy hoặc cấu trúc không đúng
    return None

def save_to_json_file(data: dict, output_path: Path):
    """
    Lưu dữ liệu dictionary vào một tệp JSON.

    Args:
        data: Dữ liệu cần lưu.
        output_path: Đường dẫn đến tệp JSON đầu ra.
    """
    print(f"Đang lưu kết quả vào tệp: {output_path}...")
    # Tạo thư mục cha nếu chưa có
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Hoàn thành!")


def main():
    """Hàm chính điều phối toàn bộ quy trình."""
    try:
        # 1. Cấu hình API
        configure_gemini_api()

        # 2. Xác định đường dẫn file
        input_folder = "./data_ver2/headings"

        # Duyệt qua các sub-folder
        subfolders = os.listdir(input_folder)
        for subfolder in sorted(subfolders):
            subfolder_path = os.path.join(input_folder, subfolder)

            if os.path.isfile(subfolder_path):
                continue

            pdf_files = [f for f in os.listdir(subfolder_path) if f.lower().endswith(".pdf")]
            for filename in sorted(pdf_files):
                file_path = os.path.join(subfolder_path, filename)
                input_name, _ = os.path.splitext(filename)

                # 3. (MỚI) Trích xuất heading ID mục tiêu từ tên file
                target_heading_id = extract_heading_id_from_filename(filename)
                if not target_heading_id:
                    print(f"Lỗi: Không thể trích xuất heading ID từ tên file: '{input_name}'")
                    return
                print(f"Đã xác định Heading mục tiêu từ tên file: {target_heading_id}")

                # 4. Trích xuất văn bản từ PDF
                pdf_content = extract_text_from_pdf(file_path, input_name)

                # 5. Gọi Gemini để phân tích và trích xuất
                structured_data = call_gemini_for_extraction(pdf_content)

                # 6. Lưu kết quả
                if structured_data:
                    # 7. Lọc kết quả JSON
                    print(f"Đang lọc kết quả cho heading ID: {target_heading_id}...")
                    filtered_data = filter_json_by_heading_id(structured_data, target_heading_id)
                    output_json_path = os.path.join(f"{subfolder_path}/headings_knowledge_base", f"{input_name}_Knowledge_Base.json")
                    save_to_json_file(filtered_data, output_json_path)
                else:
                    print("Không nhận được dữ liệu hợp lệ từ API. Tệp JSON không được tạo.")

    except (ValueError, FileNotFoundError) as e:
        print(f"Lỗi: {e}")
    except Exception as e:
        print(f"Đã xảy ra lỗi không mong muốn: {e}")

if __name__ == "__main__":
    main()