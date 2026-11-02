import json
import os
import re
from typing import Dict, List


def split_chapters(text: str) -> List[Dict]:
    parts = re.split(r"(## Chapter \d+)", text)
    chapters = []

    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1].strip()
        chapter_number = re.search(r"## Chapter (\d+)", header).group(1).zfill(2)
        notes_match = re.search(r"### Notes(.*?)(### GENERAL|$)", body, re.S)
        notes = notes_match.group(1).strip() if notes_match else ""
        general_match = re.search(r"### GENERAL(.*?)(\*\*%s\.\d+ -|\Z)" % chapter_number, body, re.S)
        general = general_match.group(1).strip() if general_match else ""
        headings = []
        heading_pattern = rf"{chapter_number}\.\s*\d+\s*- .*?(?={chapter_number}\.\s*\d+\s*-|\Z)"
        heading_matches = list(re.finditer(heading_pattern, body, re.S))

        for m in heading_matches:
            heading_block = m.group(0).strip()
            code_match = re.match(rf"({chapter_number}\.\s*\d+)", heading_block)
            code = code_match.group(1) if code_match else None
            if code:
                headings.append({
                    "code": code,
                    "content": heading_block
                })

        chapters.append({
            "chapter_number": chapter_number,
            "notes": notes,
            "general": general,
            "headings": headings,
            "content": body
        })

    return chapters



def load_json_folder(folder_path: str) -> List[Dict]:
    data = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    content = json.load(f)
                    data.append(content)
                except json.JSONDecodeError as e:
                    print(f"Readfile error {filename}: {e}")
    return data

if __name__ == "__main__":
    datas = load_json_folder("./data")
    content = ""
    file_metadata = {}
    for data in datas:
        for item in data["pages"]:
            content += item["content"][5:]
        file_metadata[data["file_name"]] = {
            "chapter": str(data.get("chapter", "")),
            "file_name": data.get("file_name"),
            "file_path": str(data.get("file_path", "")),
            "title": data.get("title", "")
        }
    hs_json = split_chapters(content)
    with open("hs_code_by_chapter.json", "w", encoding="utf-8") as f:
        json.dump(hs_json, f, ensure_ascii=False, indent=2)
    with open("file_metadata.json", "w", encoding="utf-8") as f:
        json.dump(file_metadata, f, ensure_ascii=False, indent=2)
