import json
import os
from pathlib import Path

def load_section_summaries_only(folder_path: str, language: str = 'vi') -> str:
    """
    Read all JSON files and return only summary information (section_id, title, summary)
    to be used for the pre-classification step.
    
    Args:
        folder_path: Path to the directory containing section JSON files
        language: Language to display (default is 'vi')
    
    Returns:
        str: String containing summary information of all sections
    """
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"Error: Directory '{folder_path}' does not exist or is not a directory")
            return ""
        
        json_files = sorted(folder.glob('Section_*_Knowledge_Base.json'))
        
        if not json_files:
            print(f"Error: No JSON files found in directory '{folder_path}'")
            return ""
        
        all_section_summaries = []
        
        def get_lang_content(data_field, lang):
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''
        
        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            sections_to_process = data if isinstance(data, list) else [data]
            
            for section in sections_to_process:
                if not isinstance(section, dict):
                    continue
                
                section_id = section.get('section_id', '')
                section_title = get_lang_content(section.get('section_title', ''), language)
                summary = get_lang_content(section.get('summary', ''), language)
                
                section_summary = (
                    f"- **Section {section_id}: {section_title}**\n"
                    f"  - Tóm tắt: {summary}"
                )
                
                # Add chapter information
                chapters = section.get('chapters', [])
                if chapters:
                    section_summary += "\n  - Các Chapter thuộc Section này:"
                    for chapter in chapters:
                        chapter_id = chapter.get('chapter_id', '')
                        chapter_title = get_lang_content(chapter.get('chapter_title', ''), language)
                        section_summary += f"\n    - Chapter {chapter_id}: {chapter_title}"
                
                all_section_summaries.append(section_summary)
        
        # Add section "Other"
        other_section = (
            "- **Section Other: Các sản phẩm khác không thuộc các Section trên**\n"
            "  - Tóm tắt: Section này bao gồm các sản phẩm không thuộc bất kỳ Section nào được liệt kê ở trên."
        )
        all_section_summaries.append(other_section)
        
        return "\n\n".join(all_section_summaries)
    
    except Exception as e:
        print(f"Error loading section summaries: {e}")
        return ""


def load_section_details(folder_path: str, section_ids: list[str], language: str = 'vi') -> str:
    """
    Load detailed information (including notes and general) only for the specified section IDs.
    
    Args:
        folder_path: Path to the directory containing section JSON files
        section_ids: List of section IDs to load details for
        language: Language to display (default is 'vi')
    
    Returns:
        str: String containing detailed information of the selected sections
    """
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"Error: Directory '{folder_path}' does not exist")
            return ""
        
        json_files = sorted(folder.glob('Section_*_Knowledge_Base.json'))
        selected_sections = []
        
        def get_lang_content(data_field, lang):
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''
        
        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            sections_to_process = data if isinstance(data, list) else [data]
            
            for section in sections_to_process:
                if not isinstance(section, dict):
                    continue
                
                section_id = section.get('section_id', '')
                if section_id not in section_ids:
                    continue
                
                section_title = get_lang_content(section.get('section_title', ''), language)
                summary = get_lang_content(section.get('summary', ''), language)
                file_name = section.get('file_name', 'N/A')
                file_path = section.get('file_path', 'N/A')

                section_string = (
                    f"- **Section {section_id}: {section_title}** (File: {file_name}, Path: {file_path})\n"
                    f"  - Tóm tắt: {summary}"
                )

                notes_data = section.get('notes')
                if isinstance(notes_data, list):
                    for item in notes_data:
                        page = item.get('page')
                        content = get_lang_content(item.get('content', ''), language)
                        if content:
                            section_string += f"\n  - Chú giải (Trang {page}): {content}"
                elif notes_data:
                    content = get_lang_content(notes_data, language)
                    if content:
                        section_string += f"\n  - Chú giải: {content}"

                general_data = section.get('general')
                if isinstance(general_data, list):
                    for item in general_data:
                        page = item.get('page')
                        content = get_lang_content(item.get('content', ''), language)
                        if content:
                            section_string += f"\n  - Khái quát chung (Trang {page}): {content}"
                elif general_data:
                    content = get_lang_content(general_data, language)
                    if content:
                        section_string += f"\n  - Khái quát chung: {content}"
                    
                selected_sections.append(section_string)
        
        # Add "Other" if requested
        if "Other" in section_ids:
            other_section = (
                "- **Section Other: Các sản phẩm khác không thuộc các Section trên**\n"
                "  - Tóm tắt: Section này bao gồm các sản phẩm không thuộc bất kỳ Section nào được liệt kê ở trên, "
                "hoặc các sản phẩm bị loại trừ khỏi các Section cụ thể theo quy tắc loại trừ được nêu trong Chú giải của các Section.\n"
                "  - Ghi chú: Khi phân loại vào Section Other, cần xác định rõ lý do tại sao sản phẩm không thuộc các Section khác, "
                "và nếu có quy tắc loại trừ cụ thể, cần trích dẫn file_name và file_path của Section chứa quy tắc đó."
            )
            selected_sections.append(other_section)
        
        return "\n\n".join(selected_sections)
    
    except Exception as e:
        print(f"Error loading section details: {e}")
        return ""


def load_section_knowledge_base(folder_path: str, language: str = 'vi') -> str:
    """
    Read all JSON files in the sections_knownledge_base directory
    and format them into an easy-to-understand string for LLM for Section classification.
    
    Args:
        folder_path: Path to the directory containing section JSON files
        language: Language to display (default is 'vi')
    
    Returns:
        str: String containing information of all sections
    """
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"Error: Directory '{folder_path}' does not exist or is not a directory")
            return ""
        
        # Get all JSON files in the directory
        json_files = sorted(folder.glob('Section_*_Knowledge_Base.json'))
        
        if not json_files:
            print(f"Error: No JSON files found in directory '{folder_path}'")
            return ""
        
        all_knowledge_sections = []
        
        def get_lang_content(data_field, lang):
            """Helper function to extract language-specific content"""
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''
        
        # Read each JSON file
        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle both cases: data as array or single object
            sections_to_process = data if isinstance(data, list) else [data]
            
            # Each file contains one or more sections
            for section in sections_to_process:
                if not isinstance(section, dict):
                    print(f"Warning: Section is not a dictionary in file {json_file}")
                    continue
                
                section_title = get_lang_content(section.get('section_title', ''), language)
                summary = get_lang_content(section.get('summary', ''), language)
                file_name = section.get('file_name', 'N/A')
                file_path = section.get('file_path', 'N/A')

                section_string = (
                    f"- **Section {section['section_id']}: {section_title}** (File: {file_name}, Path: {file_path})\n"
                    f"  - Tóm tắt: {summary}"
                )

                notes_data = section.get('notes')
                if isinstance(notes_data, list):
                    for item in notes_data:
                        page = item.get('page')
                        content = get_lang_content(item.get('content', ''), language)
                        if content:
                            section_string += f"\n  - Chú giải (Trang {page}): {content}"
                elif notes_data:
                    content = get_lang_content(notes_data, language)
                    if content:
                        section_string += f"\n  - Chú giải: {content}"

                general_data = section.get('general')
                if isinstance(general_data, list):
                    for item in general_data:
                        page = item.get('page')
                        content = get_lang_content(item.get('content', ''), language)
                        if content:
                            section_string += f"\n  - Khái quát chung (Trang {page}): {content}"
                elif general_data:
                    content = get_lang_content(general_data, language)
                    if content:
                        section_string += f"\n  - Khái quát chung: {content}"

                # if 'chapters' in section and section['chapters']:
                #     section_string += "\n  - Chapters include:"
                #     for chapter in section['chapters']:
                #         chapter_title = get_lang_content(chapter.get('chapter_title', ''), language)
                #         section_string += f"\n    - Chapter {chapter['chapter_id']}: {chapter_title}"
                    
                all_knowledge_sections.append(section_string)
        
        # Add section "Other" to the end of the list
        other_section = (
            "- **Section Other: Các sản phẩm khác không thuộc các Section trên**\n"
            "  - Tóm tắt: Section này bao gồm các sản phẩm không thuộc bất kỳ Section nào được liệt kê ở trên, "
            "hoặc các sản phẩm bị loại trừ khỏi các Section cụ thể theo quy tắc loại trừ được nêu trong Chú giải của các Section.\n"
            "  - Ghi chú: Khi phân loại vào Section Other, cần xác định rõ lý do tại sao sản phẩm không thuộc các Section khác, "
            "và nếu có quy tắc loại trừ cụ thể, cần trích dẫn file_name và file_path của Section chứa quy tắc đó."
        )
        all_knowledge_sections.append(other_section)
        
        return "\n\n".join(all_knowledge_sections)

    except Exception as e:
        print(f"Error loading knowledge base for section: {e}")
        return ""

def load_chapter_knowledge_base(folder_path: str, chapter_ids: list[str], language: str = 'vi') -> str:
    """
    Load and filter background knowledge from chapters_knowledge_base folder,
    retrieving only information about specific chapters.
    
    Args:
        folder_path: Path to the directory containing chapter JSON files
        chapter_ids: List of chapter IDs to load (e.g., ['39', '40', '72'])
        language: Language to display (default is 'vi')
    
    Returns:
        str: String containing detailed information of the selected chapters
    """
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"Error: Directory '{folder_path}' does not exist or is not a directory")
            return ""
        
        json_files = sorted(folder.glob('Chapter_*_Section_*_Knowledge_Base.json'))
        
        if not json_files:
            print(f"Error: No JSON files found in directory '{folder_path}'")
            return ""
        
        print(f"Found {len(json_files)} chapter files in {folder_path}")
        print(f"Looking for chapter IDs: {chapter_ids}")
        
        chapter_details = []
        
        def get_lang_content(data_field, lang):
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''
        
        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data:
                print(f"Skipping {json_file.name}: Empty data")
                continue
            
            # Handle both array and direct object formats
            if isinstance(data, list):
                if len(data) == 0:
                    print(f"Skipping {json_file.name}: Empty array")
                    continue
                chapter = data[0]
            elif isinstance(data, dict):
                chapter = data
            else:
                print(f"Skipping {json_file.name}: Invalid data format")
                continue
            
            chapter_id = str(chapter.get('chapter_id', '')).strip()
            
            print(f"File {json_file.name}: chapter_id = '{chapter_id}', looking for: {chapter_ids}")
            
            if chapter_id not in chapter_ids:
                print(f"Skipping chapter {chapter_id} - not in requested list")
                continue
            
            print(f"✓ Processing chapter {chapter_id} from {json_file.name}")
            
            chapter_title = get_lang_content(chapter.get('chapter_title', ''), language)
            summary = get_lang_content(chapter.get('summary', ''), language)
            
            chapter_info = (
                f"- **Chương {chapter_id}: {chapter_title}**\n"
                f"  - Tóm tắt: {summary}\n"
            )

            notes_list = []
            for note in chapter.get('notes', []):
                page = note.get('page', 'N/A')
                content = get_lang_content(note.get('content', ''), language)
                notes_list.append(f"    - Chú giải (Trang {page}): {content}")
            
            general_list = []
            for item in chapter.get('general', []):
                page = item.get('page', 'N/A')
                content = get_lang_content(item.get('content', ''), language)
                general_list.append(f"    - Khái quát chung (Trang {page}): {content}")

            if notes_list:
                chapter_info += "\n".join(notes_list) + "\n"
            if general_list:
                chapter_info += "\n".join(general_list)

            chapter_details.append(chapter_info)
        
        print(f"✓ Successfully loaded {len(chapter_details)} chapters: {[id for id in chapter_ids if any(f'Chương {id}:' in detail for detail in chapter_details)]}")
        
        if not chapter_details:
            print(f"ERROR: No chapter details collected!")
            return ""
        
        result = "\n\n".join(chapter_details)
        print(f"Returning chapter knowledge with {len(result)} characters")
        return result

    except Exception as e:
        print(f"Error loading chapter knowledge base: {e}")
        return ""

def load_heading_knowledge_base(folder_path: str, chapter_id: str, language: str = 'vi') -> str:
    """
    Load and filter background knowledge from headings_knowledge_base folder,
    retrieving only information about headings belonging to a specific Chapter.

    Args:
        folder_path: Path to the directory containing chapter JSON files
        chapter_id: Chapter ID to load (e.g., '39')
        language: Language to display (default is 'vi')

    Returns:
        str: String containing detailed information of the selected chapters
    """
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"Error: Directory '{folder_path}' does not exist or is not a directory")
            return ""

        json_files = sorted(folder.glob('Heading_*_Chapter_*_Section_*_Knowledge_Base.json'))
        if not json_files:
            print(f"Error: No heading files found in directory '{folder_path}'")
            return ""

        heading_details = []

        def get_lang_content(data_field, lang):
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''

        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not data:
                print(f"Skipping {json_file.name}: Empty data")
                continue

            # Handle both array and direct object formats
            if isinstance(data, list):
                if len(data) == 0:
                    print(f"Skipping {json_file.name}: Empty array")
                    continue
                heading = data[0]
            elif isinstance(data, dict):
                heading = data
            else:
                print(f"Skipping {json_file.name}: Invalid data format")
                continue

            heading_id = str(heading.get('heading_id', '')).strip()

            print(f"File {json_file.name}: heading_id = '{heading_id}', looking for chapter: {chapter_id}")
            print(f"✓ Processing heading {heading_id} chapter {chapter_id} from {json_file.name}")

            heading_title = get_lang_content(heading.get('heading_title', ''), language)
            summary = get_lang_content(heading.get('summary', ''), language)

            heading_info = (
                f"- **Nhóm {heading_id}: {heading_title}**\n"
                f"  - Tóm tắt: {summary}\n"
            )

            description_list = []
            for item in heading.get('description', []):
                page = item.get('page', 'N/A')
                content = get_lang_content(item.get('content', ''), language)
                description_list.append(f"    - Khái quát chung (Trang {page}): {content}")

            if description_list:
                heading_info += "\n".join(description_list)

            heading_details.append(heading_info)

        print(f"✓ Successfully loaded {len(heading_details)} headings for chapter: {chapter_id}")

        if not heading_details:
            print(f"ERROR: No heading details collected!")
            return ""

        result = "\n\n".join(heading_details)
        print(f"Returning headings knowledge with {len(result)} characters")
        return result

    except Exception as e:
        print(f"Error loading headings knowledge base: {e}")
        return ""

def load_subheading_knowledge_base(knowledge_base_file: str, heading_id: str, language: str = 'vi') -> str:
    """
    Load and filter background knowledge from subheadings_knowledge_base.json file,
    retrieving only information about subheadings belonging to a specific Heading.
    """
    try:
        with open(knowledge_base_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        subheadings = data.get('subheadings', [])
        if not subheadings:
            print(f"Subheading for '{heading_id}' not found in Heading knowledge base in file {knowledge_base_file}.")
            return ""

        def get_lang_content(data_field, lang):
            if isinstance(data_field, dict):
                return data_field.get(lang, '')
            return str(data_field) if data_field else ''
        
        heading_details = []
        heading_title = get_lang_content(data.get('heading_title', ''), language)
        summary = get_lang_content(data.get('summary', ''), language)

        heading_info = (
            f"- **Nhóm {heading_id}: {heading_title}**\n"
            f"  - Tóm tắt: {summary}\n"
        )

        description_list = []
        for item in data.get('description', []):
            page = item.get('page', 'N/A')
            content = get_lang_content(item.get('content', ''), language)
            description_list.append(f"    - Khái quát chung (Trang {page}): {content}")

        if description_list:
            heading_info += "\n".join(description_list) + "\n\n"

        subheading_details = []
        for sub_heading in subheadings:
            page = sub_heading.get('page', 'N/A')
            subheading_title = get_lang_content(sub_heading.get('subheading_title', ''), language)
            two_dash_subheading = get_lang_content(sub_heading.get('two_dash_subheading', ''), language)
            hasTwoDashSubheading = [item for item in subheading_details if two_dash_subheading and f"{two_dash_subheading}" in item]

            if hasTwoDashSubheading:
                subheading_details[len(subheading_details) - 1] += (
                    f"  - **Phân Nhóm {sub_heading['subheading_id']} (Trang {page}): {subheading_title}.**\n"
                )
                continue

            if two_dash_subheading:
                subheading_info = (
                    f"- **Phân nhóm cấp 2: {two_dash_subheading}.**\n"
                    f"  - **Phân Nhóm {sub_heading['subheading_id']} (Trang {page}): {subheading_title}.**\n"
                )
            else:
              subheading_info = (
                  f"- **Phân nhóm cấp 1 {sub_heading['subheading_id']} (Trang {page}): {subheading_title}.**\n"
              )

            subheading_details.append(subheading_info)

        if subheading_details:
            heading_info += "\n".join(subheading_details)

        heading_details.append(heading_info)

        return "\n\n".join(heading_details)

    except Exception as e:
        print(f"Error loading knowledge base for subheading: {e}")
        return ""
