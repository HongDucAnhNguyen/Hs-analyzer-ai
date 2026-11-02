#!/usr/bin/env python3
"""
Script để phát hiện và xóa các phần tiếng Việt khỏi JSON files
Chia đoạn theo các thẻ heading markdown: #, ##, ###, ####
"""

import json
import re
import random
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from pathlib import Path
import argparse
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def split_by_headings(text):
    
    heading_pattern = r'(?:^|\n)(#{1,4})\s+([^\n]+)'
    

    headings = list(re.finditer(heading_pattern, text))
    
    if not headings:

        return [('', '', text)]
    
    sections = []
    

    if headings[0].start() > 0:
        pre_content = text[:headings[0].start()]
        if pre_content.strip():
            sections.append(('', '', pre_content))
    
    for i, match in enumerate(headings):
        heading_level = match.group(1) 
        heading_text = match.group(2).strip()
        
       
        start_pos = match.start()
        
   
        if i + 1 < len(headings):
            end_pos = headings[i + 1].start()
        else:
            end_pos = len(text)
        

        full_section_content = text[start_pos:end_pos]
        
        sections.append((heading_level, heading_text, full_section_content))
    
    return sections


def detect_language_safe(text):
    
  
    clean_text = re.sub(r'[^\w\s]', ' ', text)
    clean_text = ' '.join(clean_text.split())
    
    if len(clean_text.strip()) < 10:  
        return 'unknown'
    
    try:
        detected_lang = detect(clean_text)
        return detected_lang
    except LangDetectException:
        return 'unknown'


def is_vietnamese_heading(heading_text):
  
    if not heading_text.strip():
        return False
        
   
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    
   
    if any(char in vietnamese_chars for char in heading_text):
        logger.info(f"Vietnamese heading detected (Vietnamese chars): {heading_text}")
        return True
    

    heading_lang = detect_language_safe(heading_text)
    if heading_lang == 'vi':
        logger.info(f"Vietnamese heading detected (langdetect): {heading_text}")
        return True
    
    return False


def get_common_vietnamese_words():
    
    return {

        'và', 'của', 'có', 'là', 'được', 'cho', 'với', 'từ', 'này', 'đó', 'các', 'một', 'hai', 'ba', 'bốn', 'năm',
        'trong', 'ngoài', 'trên', 'dưới', 'theo', 'về', 'đến', 'tại', 'sau', 'trước', 'khi', 'nếu', 'mà', 'để',
        'sẽ', 'đã', 'đang', 'sự', 'việc', 'cách', 'loại', 'dạng', 'hình', 'thể', 'phần', 'bộ', 'nhóm', 'lớp',
        'nước', 'người', 'thời', 'gian', 'ngày', 'năm', 'tháng', 'tuần', 'giờ', 'phút', 'giây',
        'lần', 'lượt', 'số', 'tỷ', 'triệu', 'nghìn', 'trăm', 'chục', 'đơn', 'vị',
        'cao', 'thấp', 'lớn', 'nhỏ', 'dài', 'ngắn', 'rộng', 'hẹp', 'dày', 'mỏng', 'nặng', 'nhẹ',
        'mới', 'cũ', 'trẻ', 'già', 'tốt', 'xấu', 'đẹp', 'xấu', 'sạch', 'bẩn', 'nóng', 'lạnh',
        'đỏ', 'xanh', 'vàng', 'đen', 'trắng', 'xám', 'nâu', 'hồng', 'tím', 'cam',
        'bằng', 'làm', 'dùng', 'sử', 'dụng', 'chế', 'tạo', 'sản', 'xuất', 'gia', 'công',
        'kim', 'sắt', 'thép', 'đồng', 'nhôm', 'chì', 'kẽm', 'thiếc', 'bạc', 'vàng',
        'ống', 'thanh', 'dây', 'tấm', 'lá', 'miếng', 'khối', 'cục', 'viên', 'hạt',
        'máy', 'thiết', 'bị', 'dụng', 'cụ', 'công', 'nghệ', 'kỹ', 'thuật', 'phương', 'pháp',
        'chất', 'liệu', 'vật', 'chất', 'hóa', 'học', 'vật', 'lý', 'cơ', 'khí',
        'ngang', 'dọc', 'thẳng', 'cong', 'tròn', 'vuông', 'chữ', 'nhật', 'tam', 'giác',
        'trung', 'tâm', 'giữa', 'cạnh', 'góc', 'mặt', 'bề', 'mặt', 'bên', 'trong', 'ngoài',
        'đầu', 'cuối', 'giữa', 'trước', 'sau', 'trái', 'phải', 'trên', 'dưới',
        'khoan', 'cắt', 'hàn', 'nối', 'ghép', 'lắp', 'ráp', 'tháo', 'rời',
        'gia', 'nhiệt', 'làm', 'lạnh', 'đun', 'nóng', 'nung', 'nấu', 'chảy', 'đông', 'cứng',
        'bao', 'gồm', 'chứa', 'đựng', 'chứa', 'đựng', 'có', 'thể', 'được', 'phải',
        'như', 'thì', 'mà', 'rằng', 'là', 'hay', 'hoặc', 'và', 'với', 'cùng',
        'qui', 'định', 'quy', 'tắc', 'luật', 'pháp', 'điều', 'khoản', 'mục', 'phần',
        'tinh', 'khiết', 'sạch', 'bẩn', 'trong', 'suốt', 'đục', 'trong', 'mờ',
        'xi', 'hóa', 'ô', 'nhiễm', 'bảo', 'vệ', 'an', 'toàn', 'nguy', 'hiểm',
        'sung', 'đầy', 'đủ', 'thiếu', 'hụt', 'dư', 'thừa', 'vừa', 'đủ',
        'quang', 'sáng', 'tối', 'mờ', 'rõ', 'mờ', 'nhạt', 'đậm', 'sắc', 'nét',
        'dung', 'tan', 'hòa', 'trộn', 'pha', 'lẫn', 'tách', 'rời', 'riêng', 'biệt',
        'xa', 'gần', 'kề', 'cạnh', 'bên', 'cách', 'xa', 'gần', 'sát', 'kề',
        'khung', 'xe', 'bavia', 'con', 'tay', 'mong', 'len', 'tinh', 'bitum','chung', 'mang','song','khuu','ren',
        
        'óng', 'duσc', 'bng', 'thiét', 'phu', 'kin', 'bi', 'hoc', 'st', 'mt', 'dàu', 'nói', 'vói', 
        'dê', 'yéu', 'chi', 'dung', 'lp', 'dt', 'tao', 'thành', 'phn', 'cua', 'vi', 'du', 'nhu', 
        'vòng', 'treo', 'thanh', 'chóng', 'try', 'tuong', 'ty', 'nhung', 'sn', 'phm', 'dnh', 'chóng', 
        'kep', 'xiét', 'cht', 'dai', 'dugc', 'sur', 'uón', 'mèm', 'duòng', 'cúmg', 'vüng', 'vòi',
        'nhóm', 'gòm', 'bao', 'su', 'ghép', 'hàn', 'giáp', 'mói', 'khác', 'bich', 'mng', 'sông',
        'loai', 'truòng', 'hop', 'cac', 'phy', 'cat', 'góc', 'vuòng', 'vát', 'tip', 'xúc', 'tháo',
        'mò', 'vây', 'cà', 'det', 'rèn', 'chuyn', 'tiép', 'chu', 'nhanh', 'khóp', 'ch', 'thp', 'np', 
        'nhánh', 'cut', 'chòng', 'tung', 'tay', 'vin', 'hinh', 'cáu', 'nhieu', 'khop', 'gom', 'làm', 'sach',
        'óc', 'du', 'dai', 'khí', 'cu', 'dc', 'bit', 'ké', 'ráp', 'bich', 'vói', 'rèn', 'óng', 'nói',
        'chuyn', 'tiép', 'chu', 'nhanh', 'khóp', 'ch', 'thp', 'np', 'dàu', 'nhánh', 'cut', 'mói', 'chòng',
        'tung', 'cua', 'tay', 'vin', 'hinh', 'cáu', 'kin', 'nhanh', 'bén', 'chi', 'tiét', 'nhieu', 'nhanh',
        'khop', 'mng', 'sông', 'gom', 'làm', 'sach', 'óc', 'du', 'vòng', 'kep', 'dai','trang','nhau','sinh','chai','than','danh','muc','dich','phanh','xung','quanh','khoai'  
    }


def extract_english_from_mixed_line(line):
    line = line.strip()
    if not line:
        return ""
    
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    vietnamese_words = get_common_vietnamese_words()
    
    # Chia dòng thành các từ
    words = line.split()
    english_segments = []
    current_segment = []
    
    for word in words:
        # Kiểm tra xem từ có phải tiếng Anh không
        is_english_word = False
        
        # Loại bỏ dấu câu để kiểm tra
        clean_word = re.sub(r'[^\w]', '', word).lower()
        
        if clean_word:
            # Kiểm tra blacklist từ tiếng Việt thông dụng
            if clean_word in vietnamese_words:
                is_english_word = False
            # Nếu có ký tự tiếng Việt có dấu
            elif any(char in vietnamese_chars for char in clean_word):
                is_english_word = False
            # Kiểm tra pattern tiếng Anh
            elif clean_word.isalpha() and clean_word.isascii():
                if len(clean_word) >= 2:
                    # Kiểm tra bằng language detection
                    word_lang = detect_language_safe(clean_word)
                    if word_lang in ['en', 'unknown']:
                        is_english_word = True
                else:
                    # Từ ngắn: a, of, in, to, etc. (nhưng không phải số)
                    is_english_word = True
        
        if is_english_word:
            current_segment.append(word)
        else:
            # Kết thúc segment hiện tại nếu có
            if current_segment:
                segment_text = ' '.join(current_segment)
                # Chỉ giữ segment nếu có ít nhất 2 từ hoặc 1 từ dài (> 4 ký tự)
                if len(current_segment) >= 2 or (len(current_segment) == 1 and len(current_segment[0]) > 4):
                    english_segments.append(segment_text)
                current_segment = []
    
    # Thêm segment cuối cùng nếu có
    if current_segment:
        segment_text = ' '.join(current_segment)
        if len(current_segment) >= 2 or (len(current_segment) == 1 and len(current_segment[0]) > 4):
            english_segments.append(segment_text)
    
    # Kết hợp các segment bằng dấu cách
    return ' '.join(english_segments)


def is_entirely_english_content(content):
   
    if not content.strip():
        return True  
    
  
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    
   
    if any(char in vietnamese_chars for char in content):
        return False
    
   
    vietnamese_words = get_common_vietnamese_words()
    words = re.findall(r'\b\w+\b', content.lower())
    
    if not words:
        return True 
    
    vietnamese_word_count = sum(1 for word in words if word in vietnamese_words)
    vietnamese_ratio = vietnamese_word_count / len(words)
    

    if vietnamese_ratio > 0.1:
        logger.debug(f"Found {vietnamese_word_count}/{len(words)} Vietnamese words ({vietnamese_ratio:.2%})")
        return False
    

    sections = split_by_headings(content)
    for heading_level, heading_text, section_content in sections:
        if heading_text.strip() and is_vietnamese_heading(heading_text):
            logger.debug(f"Found Vietnamese heading: {heading_text}")
            return False
    
    # Kiểm tra một số dòng ngẫu nhiên bằng language detection
    lines = [line.strip() for line in content.split('\n') if line.strip() and len(line.strip()) > 20]
    if lines:
        # Lấy tối đa 5 dòng ngẫu nhiên để kiểm tra
        sample_lines = random.sample(lines, min(5, len(lines)))
        
        for line in sample_lines:
            line_lang = detect_language_safe(line)
            if line_lang == 'vi':
                logger.debug(f"Found Vietnamese line: {line[:50]}...")
                return False
    
    return True


def is_vietnamese_line(line):
    """
    Kiểm tra xem một dòng có phải là tiếng Việt không
    """
    line = line.strip()
    if not line:
        return False
    
    # Kiểm tra ký tự tiếng Việt có dấu
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    
    # Nếu có ký tự tiếng Việt có dấu thì là tiếng Việt
    if any(char in vietnamese_chars for char in line):
        return True
    
    # Kiểm tra từ tiếng Việt thông dụng
    vietnamese_words = get_common_vietnamese_words()
    words = re.findall(r'\b\w+\b', line.lower())
    vietnamese_word_count = sum(1 for word in words if word in vietnamese_words)
    
    # Nếu > 30% từ là tiếng Việt thông dụng thì coi là dòng tiếng Việt
    if words and vietnamese_word_count / len(words) > 0.3:
        return True
    
    # Kiểm tra bằng language detection cho dòng dài hơn
    line_lang = detect_language_safe(line)
    return line_lang == 'vi'


def has_mixed_content(line):
    """
    Kiểm tra xem dòng có cả tiếng Việt và tiếng Anh không
    """
    line = line.strip()
    if not line:
        return False
    
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    
    # Chia dòng thành từ
    words = line.split()
    has_vietnamese = False
    has_english = False
    
    for word in words:
        if any(char in vietnamese_chars for char in word):
            has_vietnamese = True
        else:
            # Kiểm tra xem có phải từ tiếng Anh không
            if len(word) >= 2 and word.isalpha():
                has_english = True
    
    return has_vietnamese and has_english


def split_into_sentences(text):
    """
    Tách text thành các câu dựa trên dấu câu
    """
    # Sử dụng regex để tách câu dựa trên dấu câu chính
    sentence_pattern = r'[.!?;]+\s*'
    sentences = re.split(sentence_pattern, text)
    
    # Loại bỏ câu trống và giữ lại dấu câu
    result_sentences = []
    parts = re.split(f'({sentence_pattern})', text)
    
    current_sentence = ""
    for i, part in enumerate(parts):
        if re.match(sentence_pattern, part):
            # Đây là dấu câu
            if current_sentence.strip():
                result_sentences.append(current_sentence.strip() + part.strip())
                current_sentence = ""
        else:
            # Đây là nội dung câu
            current_sentence += part
    
    # Thêm câu cuối nếu có
    if current_sentence.strip():
        result_sentences.append(current_sentence.strip())
    
    return [s for s in result_sentences if s.strip()]


def is_corrupted_vietnamese_word(word):
    """
    Kiểm tra xem từ có phải là từ tiếng Việt bị lỗi encoding không
    Dựa trên pattern và heuristics
    """
    clean_word = re.sub(r'[^\w]', '', word).lower()
    
    if len(clean_word) < 2:
        return False
    
    # Pattern thường gặp trong corrupted Vietnamese text
    corrupted_patterns = [
        r'.*óng.*',  # ống -> óng
        r'.*duσc.*', # được -> duσc  
        r'.*bng.*',  # bằng -> bng
        r'.*thiét.*', # thiết -> thiét
        r'.*phu.*',  # phụ -> phu
        r'.*kin.*',  # kiện -> kin
        r'.*hoc.*',  # hoặc -> hoc
        r'.*vói.*',  # với -> vói
        r'.*dàu.*',  # đầu -> dàu
        r'.*mói.*',  # mới -> mói
        r'.*cua.*',  # của -> cua
        r'.*dugc.*', # được -> dugc
        r'.*duòng.*', # đường -> duòng
        r'.*gòm.*',  # gồm -> gòm
        r'.*nhóm.*', # nhóm -> nhóm (có thể bị lỗi)
    ]
    
    for pattern in corrupted_patterns:
        if re.match(pattern, clean_word):
            return True
    
    # Kiểm tra từ có chứa ký tự đặc biệt thường gặp trong lỗi encoding
    corrupted_chars = 'σμαβγδεζηθικλνξοπρστυφχψω'  # Greek letters thường xuất hiện
    if any(char in corrupted_chars for char in word):
        return True
    
    # Từ có độ dài ngắn và không phải tiếng Anh thông dụng
    if len(clean_word) <= 3 and clean_word.isalpha():
        english_short_words = {'a', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 
                              'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we', 'the', 'and',
                              'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one',
                              'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now',
                              'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say',
                              'she', 'too', 'use', 'oil', 'gas', 'may', 'end', 'run', 'cut', 'set', 'top',
                              'low', 'big', 'hot', 'off', 'far', 'own', 'few', 'lot', 'job', 'yet', 'try'}
        
        # Nếu không phải từ tiếng Anh ngắn thông dụng, có thể là từ tiếng Việt lỗi
        if clean_word not in english_short_words:
            # Kiểm tra thêm: từ có pattern giống tiếng Việt không
            vietnamese_patterns = ['ng', 'nh', 'ch', 'th', 'ph', 'gh', 'kh', 'tr', 'qu']
            has_vietnamese_pattern = any(pattern in clean_word for pattern in vietnamese_patterns)
            if has_vietnamese_pattern:
                return True
    
    return False


def clean_sentence(sentence):
    """
    Làm sạch một câu: loại bỏ từ tiếng Việt nhưng giữ cấu trúc câu
    """
    vietnamese_words = get_common_vietnamese_words()
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    vietnamese_chars += vietnamese_chars.upper()
    
    # Tách từ nhưng giữ lại dấu câu và khoảng trắng
    words = sentence.split()
    filtered_words = []
    
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word).lower()
        
       
        should_remove = False
        
        if clean_word:
           
            if clean_word in vietnamese_words:
                should_remove = True
           
            elif any(char in vietnamese_chars for char in word):
                should_remove = True
            
            elif is_corrupted_vietnamese_word(word):
                should_remove = True
         
            elif len(clean_word) <= 2 and clean_word.isalpha():
                
                common_short = {'a', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 
                               'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we'}
                if clean_word not in common_short:
                    should_remove = True
        
        if not should_remove:
            filtered_words.append(word)
    
    cleaned_sentence = ' '.join(filtered_words).strip()
    
    
    if len(filtered_words) >= 2 or (len(filtered_words) == 1 and 
                                   (not filtered_words[0].replace(',', '').replace('.', '').replace('(', '').replace(')', '').isalpha() 
                                    or len(filtered_words[0]) > 3)):
        return cleaned_sentence
    
    return ""


def clean_remaining_vietnamese_words(text):
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if not line.strip():
            cleaned_lines.append(line)
            continue
        
      
        sentences = split_into_sentences(line)
        if len(sentences) > 1:
       
            cleaned_sentences = []
            for sentence in sentences:
                cleaned_sentence = clean_sentence(sentence)
                if cleaned_sentence:
                    cleaned_sentences.append(cleaned_sentence)
            
            if cleaned_sentences:
               
                cleaned_line = ' '.join(cleaned_sentences)
                cleaned_lines.append(cleaned_line)
        else:
       
            cleaned_sentence = clean_sentence(line)
            if cleaned_sentence:
                cleaned_lines.append(cleaned_sentence)
    
    return '\n'.join(cleaned_lines)


def clean_vietnamese_lines(text):
  
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        if not is_vietnamese_line(line):
           
            filtered_lines.append(line)
        elif has_mixed_content(line):
          
            english_part = extract_english_from_mixed_line(line)
            if english_part.strip():
                filtered_lines.append(english_part)
                logger.debug(f"Extracted English from mixed line: {english_part.strip()}")
            else:
                logger.debug(f"Removed mixed line (no English found): {line.strip()}")
        else:
           
            logger.debug(f"Removed Vietnamese line: {line.strip()}")
    

    result_lines = []
    prev_empty = False
    
    for line in filtered_lines:
        is_empty = not line.strip()
        if not (is_empty and prev_empty): 
            result_lines.append(line)
        prev_empty = is_empty
    
    result_text = '\n'.join(result_lines)
    
  
    result_text = clean_remaining_vietnamese_words(result_text)
    
    return result_text


def remove_vietnamese_from_text(text):
    
    sections = split_by_headings(text)
    filtered_sections = []
    
    logger.info(f"Found {len(sections)} sections to analyze")
    
    for heading_level, heading_text, full_section_content in sections:
        
        if heading_text.strip() and is_vietnamese_heading(heading_text):
            logger.info(f"Removed Vietnamese section with heading: {heading_text}")
            continue
        else:
         
            filtered_sections.append(full_section_content)
    
    result = ''.join(filtered_sections)
 
    logger.info("Cleaning remaining Vietnamese lines...")
    result = clean_vietnamese_lines(result)
    
    return result


def process_json_file(input_file, output_file=None):
    
    logger.info(f"Processing file: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    

    total_pages = 0
    english_only_pages = 0
    bilingual_pages = 0
    processed_pages = []
    

    for page_data in data.get('pages', []):
        total_pages += 1
        page_num = page_data.get('page', '?')
        
        if 'content' in page_data:
            original_content = page_data['content']
            
           
            if is_entirely_english_content(original_content):
              
                english_only_pages += 1
                processed_pages.append(page_data)
                logger.info(f"Page {page_num}: English-only content, passed through")
            else:
               
                bilingual_pages += 1
                logger.info(f"Page {page_num}: Bilingual content detected, processing...")
                
                filtered_content = remove_vietnamese_from_text(original_content)
                
               
                if filtered_content.strip():
                    page_data['content'] = filtered_content
                    processed_pages.append(page_data)
                    logger.info(f"Page {page_num}: Processed and kept (Vietnamese content removed)")
                else:
                    logger.info(f"Page {page_num}: Removed (no content remaining after filtering)")
        else:
          
            processed_pages.append(page_data)
            logger.info(f"Page {page_num}: No content field, passed through")
    
  
    data['pages'] = processed_pages
    
   
    logger.info(f"Processing summary:")
    logger.info(f"  Total pages: {total_pages}")
    logger.info(f"  English-only pages (passed through): {english_only_pages}")
    logger.info(f"  Bilingual pages (processed): {bilingual_pages}")
    logger.info(f"  Final pages retained: {len(processed_pages)}")
    
 
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_filtered{input_path.suffix}"
    

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Filtered content saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Remove Vietnamese text from JSON files')
    parser.add_argument('input', help='Input JSON file or directory')
    parser.add_argument('-o', '--output', help='Output file or directory')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    input_path = Path(args.input)
    
    if input_path.is_file():
        
        process_json_file(input_path, args.output)
    elif input_path.is_dir():
       
        json_files = list(input_path.glob('*.json'))
        logger.info(f"Found {len(json_files)} JSON files to process")
        
        for json_file in json_files:
            try:
                if args.output:
                    output_dir = Path(args.output)
                    output_dir.mkdir(exist_ok=True)
                    output_file = output_dir / f"{json_file.stem}_filtered{json_file.suffix}"
                else:
                    output_file = None
                
                process_json_file(json_file, output_file)
            except Exception as e:
                logger.error(f"Error processing {json_file}: {e}")
    else:
        logger.error(f"Input path does not exist: {input_path}")


if __name__ == '__main__':
    main()
