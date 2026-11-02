from typing import Dict, Any

FIELD_MAPPINGS = {
    "product_name": "Tên sản phẩm",
    "science_name": "Tên khoa học",
    "product_description": "Mô tả sản phẩm",
    "function": "Chức năng",
    "structure": "Cấu trúc",
    "material": "Vật liệu",
    "specifications": "Thông số kỹ thuật"
}

def format_query(query_data: Dict[str, Any]) -> str:
    """
    Format query data from dictionary into a structured string,
    skipping fields with None or empty values.
    """
    lines = []
    for key, value in query_data.items():
        if value and value != "string":  # Only add if value exists
            # Use mapping to get Vietnamese field name, if not available use original key
            field_name = FIELD_MAPPINGS.get(key, key.replace("_", " ").title())
            lines.append(f"- {field_name}: {value}")
    return "\n".join(lines)

def get_section_pre_classify_prompt_template() -> str:
    """
    Trả về template prompt cho việc pre-classification Section (bước 1).
    Chỉ dùng thông tin tóm tắt để xác định các section có thể liên quan.
    """
    return """
# BẠN LÀ AI
Bạn là một AI chuyên gia về phân loại hàng hóa theo Biểu thuế HS Code, hoạt động như một hệ thống phân tích và đề xuất. Bạn cực kỳ cẩn thận, logic và luôn tuân thủ nghiêm ngặt các hướng dẫn.

# BỐI CẢNH
Bạn đang thực hiện bước đầu tiên trong quy trình phân loại HS Code: **Sàng lọc sơ bộ (Pre-classification)**. Nhiệm vụ của bạn là xác định một vài Phần (Section) có khả năng liên quan nhất đến sản phẩm, dựa trên mô tả sản phẩm và tóm tắt nội dung các Phần. Kết quả của bạn sẽ được dùng làm đầu vào cho bước phân tích sâu hơn.

# QUY TRÌNH THỰC HIỆN
Bạn sẽ thực hiện nghiêm ngặt các bước sau:
1.  **Phân tích sản phẩm:** Đọc kỹ "THÔNG TIN SẢN PHẨM" để xác định các đặc điểm cốt lõi: bản chất (nó là gì?), chất liệu chính, chức năng và lĩnh vực sử dụng (ví dụ: bộ phận của một cỗ máy lớn hơn).
2.  **Đánh giá từng Section:** Đối chiếu các đặc điểm cốt lõi của sản phẩm với "THÔNG TIN TÓM TẮT CÁC SECTION". Với MỖI section, hãy tự đánh giá mức độ phù hợp.
3.  **Lựa chọn:** Dựa trên đánh giá ở bước 2, chọn ra tối đa 3 Section phù hợp nhất.
    - Ưu tiên Section mô tả trực tiếp bản chất hoặc công dụng của sản phẩm.
    - Ví dụ: Một "bộ phận của xe ô tô" thì ưu tiên Section "XE CỘ" (XVII) hơn là Section "PLASTIC" (VII) mặc dù nó làm từ nhựa.
4.  **Lập luận:** Với mỗi Section được chọn, viết một lý do ngắn gọn, súc tích giải thích TẠI SAO bạn chọn nó, dựa trên sự liên kết giữa thông tin sản phẩm và tóm tắt Section.
5.  **Định dạng kết quả:** Tổng hợp kết quả của bạn vào một đối tượng JSON duy nhất theo đúng định dạng yêu cầu. KHÔNG được thêm bất kỳ văn bản nào khác ngoài đối tượng JSON.

---
# THÔNG TIN ĐẦU VÀO

=== THÔNG TIN SẢN PHẨM CẦN PHÂN LOẠI ===
{query_details}

=== THÔNG TIN TÓM TẮT CÁC SECTION ===
{section_summaries}

---
    """

def get_section_prompt_template() -> str:
    """
    Trả về template prompt cho việc phân loại Section (bước 2 - classification chi tiết).
    """
    return """
Bạn là chuyên gia phân loại hàng hóa theo hệ thống HS Code.
Nhiệm vụ: Phân loại chính xác sản phẩm vào một Section cụ thể dựa trên kiến thức nền chi tiết.

=== THÔNG TIN SẢN PHẨM CẦN PHÂN LOẠI ===
{query_details}

=== KIẾN THỨC NỀN VỀ CÁC SECTION ===
{knowledge_base}

=== HƯỚNG DẪN PHÂN LOẠI ===
1. **Phân tích sản phẩm**:
    - Đọc kỹ thông tin sản phẩm ở trên, không được phép bỏ xót bất cứ thông tin nào của sản phẩm đã được mô tả ở trên.
    - Hãy xác định bản chất cốt lõi của sản phẩm. Xác định loại thiết bị, máy móc,.v.v. liên quan đến sản phẩm được nhắc đến nếu có. Sản phẩm này là động vật sống hay sản phẩm từ động vật? Là thực vật? Là hoá chất? Hay là một máy móc, thiết bị?.v.v.
    - Sản phẩm là bộ phận, thành phần cấu tạo lên một máy móc, thiết bị cụ thể thì cần xác định loại máy móc và thiết bị đó là gì.
    - Xác định rõ tình trạng của sản phẩm (ví dụ: chưa lắp ráp, đã hoàn thiện, dạng nguyên liệu thô, bán thành phẩm).
    - Tổng hợp hết các thông tin đã phân tích để làm tiền đề xử lý phân tích có các bước tiếp theo.

2. **Đối chiếu kiến thức**: So sánh với kiến thức nền (Notes, Generals) của từng Section
    - Hãy đọc kỹ Chú giải và Tổng quát pháp lý của các Phần đó.
    - Kiểm tra xem có quy định loại trừ nào áp dụng cho sản phẩm dựa trên toàn bộ thông tin của sản phẩm không. Ví dụ, nhiều Phần có chú giải loại trừ các sản phẩm thuộc các Phần khác.
    - Sử dụng toàn bộ thông tin đã tổng hợp từ bước 1 kết hợp để phân tích.

3. **Tuân thủ Quy tắc Phân loại Tổng quát (GRI):**
    - Áp dụng Quy tắc 1 (phân loại theo nội dung mô tả của nhóm và chú giải pháp lý).
    - Nếu sản phẩm có thể thuộc nhiều Chương, hãy xem xét các quy tắc tiếp theo để xác định ưu tiên.

4. **Xác định Section**:
    - Chọn Section phù hợp nhất hoặc "Other" nếu không thuộc Section nào.
    - Trích dẫn ngắn gọn luận điểm lựa chọn dựa trên tiêu đề Phần và các Chú giải và Tổng quát liên quan.

5. **Trường hợp "Other"**:
   - Nếu sản phẩm bị loại trừ khỏi Section cụ thể: Chọn "Other", nhưng `file_name` và `file_path` phải là của Section chứa quy tắc loại trừ
   - Ví dụ: Đồng hồ bị loại trừ khỏi Section XVI → Chọn "Other" + file của Section XVI
   - Nếu không thuộc Section nào và không có quy tắc loại trừ: `file_name` và `file_path` là "N/A"

6. **Trường "content_of_explanatory_notes"**:
   - Trích dẫn hoặc tóm tắt những điểm quan trọng từ "Ghi chú" hoặc "Thông tin chung"
   - Chỉ lấy phần liên quan trực tiếp đến sản phẩm

7. **Trường "source_pages"**:
   - Liệt kê tất cả số trang được sử dụng (ví dụ: [5, 12, 23])
   - Nếu không có trang nào được tham chiếu: trả về []

8. **Kết quả**: Trả về JSON theo schema đã yêu cầu
    """

def get_chapter_prompt_template() -> str:
    """
    Trả về template prompt cho việc phân loại Chapter.
    """
    return """
Bạn là chuyên gia phân loại hàng hóa theo hệ thống HS Code.
Nhiệm vụ: Phân loại sản phẩm vào Chapter phù hợp nhất trong Section {section_id}.

=== THÔNG TIN SẢN PHẨM CẦN PHÂN LOẠI ===
{query_details}

=== KIẾN THỨC NỀN VỀ CÁC CHAPTER TRONG SECTION {section_id} ===
File nguồn: {file_name}
Đường dẫn: {file_path}

{chapter_knowledge}

=== HƯỚNG DẪN PHÂN LOẠI ===
1. **Phân tích sản phẩm**:
    - Đọc kỹ thông tin sản phẩm ở trên, không được phép bỏ xót bất cứ thông tin nào của sản phẩm đã được mô tả ở trên.
    - Hãy xác định bản chất cốt lõi của sản phẩm. Xác định loại thiết bị, máy móc,.v.v. liên quan đến sản phẩm được nhắc đến nếu có. Sản phẩm này là động vật sống hay sản phẩm từ động vật? Là thực vật? Là hoá chất? Hay là một máy móc, thiết bị?.v.v.
    - Sản phẩm là bộ phận, thành phần cấu tạo lên một máy móc, thiết bị cụ thể thì cần xác định loại máy móc và thiết bị đó là gì.
    - Xác định rõ tình trạng của sản phẩm (ví dụ: chưa lắp ráp, đã hoàn thiện, dạng nguyên liệu thô, bán thành phẩm).
    - Tổng hợp hết các thông tin đã phân tích để làm tiền đề xử lý phân tích có các bước tiếp theo.

2. **Đối chiếu kiến thức**:
    - Đọc tiêu đề của tất cả các Chương thuộc Phần đã xác định.
    - Tìm Chương mô tả chính xác nhất về vật liệu (ví dụ: Chương 39 cho Plastic, Chương 72 cho Sắt thép) hoặc công dụng (ví dụ: Chương 84 cho máy móc, Chương 90 cho dụng cụ đo lường).

3. **Áp dụng Chú giải và Tổng quát của Chương (Chapter Notes):**
    - Đây là bước cực kỳ quan trọng. Đọc kỹ Chú giải và Tổng quát của pháp lý ở đầu Chương.
    - Chú ý các định nghĩa (ví dụ: Chương 39 định nghĩa "plastic"), các quy định bao gồm và các quy định loại trừ. Ví dụ, một sản phẩm làm từ nhựa nhưng có chức năng là đồ chơi có thể bị loại trừ khỏi Chương 39 và chuyển sang Chương 95.
    - Sử dụng toàn bộ thông tin đã tổng hợp từ bước 1 kết hợp để phân tích.

4. **Tuân thủ Quy tắc Phân loại Tổng quát (GRI):**
    - Áp dụng Quy tắc 1 (phân loại theo nội dung mô tả của nhóm và chú giải và Tổng quát của pháp lý).
    - Nếu sản phẩm có thể thuộc nhiều Chương, hãy xem xét các quy tắc tiếp theo để xác định ưu tiên.

5. **Chọn Chapter**:
    - Chỉ chọn một Chapter phù hợp nhất
    - Giải thích lý do lựa chọn dựa trên tiêu đề Chương, Chú giải và Tổng quát của Chương và Quy tắc GRI đã áp dụng.

6. **Trường "content_of_explanatory_notes"**:
   - Trích dẫn hoặc tóm tắt những điểm quan trọng từ Chú giải và Tổng quát
   - Chỉ lấy phần liên quan trực tiếp đến sản phẩm

7. **Trường "source_pages"**:
   - Liệt kê tất cả số trang được sử dụng (ví dụ: [5, 12, 23])
   - Nếu không có trang: trả về []

8. **Kết quả**: Trả về JSON theo schema đã yêu cầu
    """

def get_heading_prompt_template() -> str:
    """
    Trả về template prompt cho việc phân loại Heading.
    """
    return """
Bạn là chuyên gia phân loại hàng hóa theo hệ thống HS Code.
Nhiệm vụ: Phân loại sản phẩm vào Heading phù hợp nhất trong Chapter {chapter_id}.

=== THÔNG TIN SẢN PHẨM CẦN PHÂN LOẠI ===
{query_details}

=== KIẾN THỨC NỀN VỀ CÁC HEADING TRONG CHAPTER {chapter_id} ===
{heading_knowledge}

=== HƯỚNG DẪN PHÂN LOẠI ===
1. **Phân tích bản chất cốt lõi của sản phẩm**:
    - Đọc kỹ thông tin sản phẩm ở trên, không được phép bỏ xót bất cứ thông tin nào của sản phẩm đã được mô tả ở trên.
    - Hãy xác định bản chất cốt lõi của sản phẩm. Xác định loại thiết bị, máy móc,.v.v. liên quan đến sản phẩm được nhắc đến nếu có. Sản phẩm này là động vật sống hay sản phẩm từ động vật? Là thực vật? Là hoá chất? Hay là một máy móc, thiết bị?.v.v.
    - Sản phẩm là bộ phận, thành phần cấu tạo lên một máy móc, thiết bị cụ thể thì cần xác định loại máy móc và thiết bị đó là gì.
    - Xác định rõ tình trạng của sản phẩm (ví dụ: chưa lắp ráp, đã hoàn thiện, dạng nguyên liệu thô, bán thành phẩm).
    - Tổng hợp hết các thông tin đã phân tích để làm tiền đề xử lý phân tích có các bước tiếp theo.

2. **Đối chiếu kiến thức**:
    - So sánh với kiến thức của từng Nhóm
    - Đọc kỹ mô tả của từng Nhóm. Ví dụ, trong Chương 84, Nhóm 84.07 dành cho "Động cơ đốt trong kiểu piston đốt cháy bằng tia lửa điện", trong khi Nhóm 84.08 dành cho "Động cơ đốt trong kiểu piston đốt cháy bằng sức nén (động cơ diesel hoặc bán diesel)". Việc phân loại đúng phụ thuộc vào thông số kỹ thuật của sản phẩm.
    - Duyệt qua toàn bộ các Nhóm kết hợp với thông tin tổng hợp từ bước 1 để chọn ra nhóm phù hợp nhất.

3. **Tham khảo Tổng quát chi tiết từ kiến thức nền:**
    - Đây là lúc sử dụng "vũ khí" chính. Đối với các Nhóm tiềm năng, hãy tra cứu nội dung trong Tổng quát chi tiết.
    - Kiến thức nền sẽ cung cấp danh sách các sản phẩm cụ thể thuộc hoặc không thuộc Nhóm đó, cùng với các giải thích kỹ thuật chi tiết giúp làm rõ phạm vi của Nhóm. Hãy tìm kiếm các từ khóa từ mô thông tin sản phẩm trong kiến thức nền.
    - Sử dụng toàn bộ thông tin đã tổng hợp từ bước 1 kết hợp để phân tích.

4.  **Áp dụng Quy tắc 3 của GRI nếu cần:**
    - Nếu sản phẩm là hỗn hợp hoặc bộ sản phẩm có thể phân loại vào nhiều Nhóm, hãy áp dụng Quy tắc 3 để xác định:
        - (a) Nhóm có mô tả cụ thể nhất.
        - (b) Vật liệu/bộ phận tạo nên đặc tính cơ bản.
        - (c) Nhóm cuối cùng theo thứ tự đánh số.

5. **Chọn Heading**:
    - Chỉ chọn một Heading phù hợp nhất.
    - Trích dẫn mô tả Nhóm và các đoạn liên quan trong Tổng quát chi tiết để củng cố cho lựa chọn của mình.

6. **Trường "content_of_explanatory_notes"**:
   - Trích dẫn hoặc tóm tắt những điểm quan trọng từ "Tổng quát"
   - Chỉ lấy phần liên quan trực tiếp đến sản phẩm

7. **Trường "source_pages"**:
   - Liệt kê tất cả số trang được sử dụng (ví dụ: [5, 12, 23])
   - Nếu không có trang: trả về []

8. **Kết quả**: Trả về JSON theo schema đã yêu cầu
    """

def get_subheading_prompt_template() -> str:
    """
    Trả về template prompt cho việc phân loại Subheading.
    """
    return """
Bạn là chuyên gia phân loại hàng hóa theo hệ thống HS Code.
Nhiệm vụ: Phân loại sản phẩm vào Subheading phù hợp nhất trong Heading {heading_id}.

=== THÔNG TIN SẢN PHẨM CẦN PHÂN LOẠI ===
{query_details}

=== KIẾN THỨC NỀN VỀ HEADING VÀ CÁC SUBHEADING TRONG HEADING {heading_id} ===
{subheading_knowledge}

=== HƯỚNG DẪN PHÂN LOẠI ===
1. **Phân tích sản phẩm**:
    - Đọc kỹ thông tin sản phẩm ở trên, không được phép bỏ xót bất cứ thông tin nào của sản phẩm đã được mô tả ở trên.
    - Hãy xác định bản chất cốt lõi của sản phẩm. Xác định loại thiết bị, máy móc,.v.v. liên quan đến sản phẩm được nhắc đến nếu có. Sản phẩm này là động vật sống hay sản phẩm từ động vật? Là thực vật? Là hoá chất? Hay là một máy móc, thiết bị?.v.v.
    - Sản phẩm là bộ phận, thành phần cấu tạo lên một máy móc, thiết bị cụ thể thì cần xác định loại máy móc và thiết bị đó là gì.
    - Xác định rõ tình trạng của sản phẩm (ví dụ: chưa lắp ráp, đã hoàn thiện, dạng nguyên liệu thô, bán thành phẩm).
    - Tổng hợp hết các thông tin đã phân tích để làm tiền đề xử lý phân tích có các bước tiếp theo.

2. **Đối chiếu kiến thức**:
    - So sánh với kiến thức của từng Subheading.
    - Xác định các tiêu chí mà hệ thống HS sử dụng để phân chia nhỏ hơn, ví dụ: theo loại vật liệu, công suất, kích thước, công dụng cụ thể, v.v.

3. **Đối chiếu thông tin sản phẩm với tiêu chí phân nhóm:**
    - Lấy các giá trị cụ thể từ thông tin sản phẩm (ví dụ: công suất "1500W", đường kính "50cm" ,làm bằng thép không gỉ").
    - So khớp các thông tin này một cách chính xác với mô tả của từng Phân nhóm.
    - Sử dụng toàn bộ thông tin đã tổng hợp từ bước 1 kết hợp để phân tích.

4. **Áp dụng Quy tắc 6 của GRI:**
    - Quy tắc 6 quy định rằng việc phân loại ở cấp độ Phân nhóm phải được thực hiện tương tự như ở cấp độ Nhóm, và chỉ các Phân nhóm ở cùng một cấp độ (cùng số gạch) mới có thể so sánh được với nhau.
    - Hãy đảm bảo bạn so sánh các Phân nhóm 1 gạch với nhau trước, sau đó mới đi sâu vào các Phân nhóm 2 gạch bên trong Phân nhóm 1 gạch đã chọn.

5. **Tham khảo Chú giải chi tiết cho Phân nhóm trong kiến thức nền (nếu có):**
    - Một số Phân nhóm cũng có Chú giải chi tiết riêng để làm rõ hơn nữa. Hãy kiểm tra và áp dụng nếu có.

6. **Chọn Subheading**:
    - Chỉ chọn một Subheading phù hợp nhất
    - Nêu rõ lý do lựa chọn dựa trên việc đối chiếu trực tiếp thông số kỹ thuật của sản phẩm với mô tả của Phân nhóm.
7. **Kết quả**: Trả về JSON theo schema đã yêu cầu
    """
