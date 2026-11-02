import asyncio
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from pydantic import (BaseModel, Field, ValidationError, root_validator,
                      validator)


# ===== Schema & helpers =====
class HSCodeType(str, Enum):
    HS_HEADING = "hs-code_heading"
    HS_SUBHEADING = "hs-code_subheading"


class HSCodeEntry(BaseModel):
    """
    One HS code entry.
    hs_code: e.g. "0101" or "010121" or "0101.21"
    code_type: automatically inferred if omitted (4 digits -> heading, 6 digits -> subheading)
    chapter: 2-digit chapter number (string, padded)
    content: description text
    keywords: list of keywords
    """
    hs_code: str = Field(..., description="The HS code, e.g., '84.01', '0101.21' or '0101.21'")
    code_type: Optional[HSCodeType] = Field(None, description="hs-code_heading or hs-code_subheading")
    chapter: str = Field(..., description="2-digit chapter number, e.g., '01', '87'")
    content: str = Field(..., description="description text belonging to this HS code")
    keywords: List[str] = Field(..., description="5–10 concise English keywords relevant to the HS code")



class ListHScode(BaseModel):
    list_hs_code: List[HSCodeEntry]


# ===== LLM (unchanged) =====
llm = OpenAI(model="gpt-5-mini")


async def parse_hscode_heading(
    sem: asyncio.Semaphore,
    notes: str,
    general: str,
    heading: Dict
) -> List[Dict[str, Any]]:
    """
    Parse a single heading + related notes/general into structured HS code JSONs.
    If error, return [].
    """
    prompt = f"""
    You are given part of an HS Code document (Notes, General rules, and one Heading).
    Extract and structure its content into a JSON array of HSCodeEntry objects.

    Notes:
    {notes}

    General:
    {general}

    Heading:
    {heading}
    """

    async with sem:
        try:
            sllm = llm.as_structured_llm(output_cls=ListHScode)
            input_msg = ChatMessage.from_str(prompt)
            output = await sllm.achat([input_msg])

            # ✅ Trường hợp output là BaseModel
            if isinstance(output, ListHScode):
                return output.model_dump()["list_hs_code"]

            # ✅ Trường hợp raw trả về string JSON
            elif isinstance(output.raw, str):
                parsed = json.loads(output.raw)
                return parsed.get("list_hs_code", [])

            # ✅ Trường hợp raw là BaseModel
            elif hasattr(output.raw, "model_dump"):
                return output.raw.model_dump()["list_hs_code"]

            else:
                print("⚠️ Unknown output format:", type(output.raw))
                return []

        except (ValidationError, Exception) as e:
            print(f"⚠️ Lỗi extract heading: {e}")
            return []

async def process_chapter(chapter: Dict, processed_ids: set) -> Dict:
    """
    Process a single chapter into structured HS codes.
    Only process headings not in processed_ids.
    """
    sem = asyncio.Semaphore(4)
    tasks = []

    notes = chapter.get("notes", "")
    general = chapter.get("general", "")
    headings = chapter.get("headings", [])

    for heading in headings:
        heading_id = f'{chapter.get("chapter_number")}_{heading.get("content","")[:30]}'
        if heading_id in processed_ids:
            continue  # skip if already processed
        tasks.append(parse_hscode_heading(sem, notes, general, heading.get("content", "")))
        processed_ids.add(heading_id)

    results = await asyncio.gather(*tasks)

    # Flatten list
    hs_json = [item for sublist in results for item in sublist]

    return {
        "chapter_number": chapter.get("chapter_number"),
        "extract_hscode": hs_json,
    }


async def main(input_file: str, output_file: str, state_file: str):
    # Load chapters
    with open(input_file, "r", encoding="utf-8") as f:
        chapters = json.load(f)

    # Load state file (list of processed heading ids)
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            processed_ids = set(json.load(f))
    except FileNotFoundError:
        processed_ids = set()

    outputs = []
    for chapter in chapters:
        result = await process_chapter(chapter, processed_ids)
        if result["extract_hscode"]:
            outputs.append(result)

        # Save state after each chapter (safe if crash)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(list(processed_ids), f, ensure_ascii=False, indent=2)

        # Append result to output file (JSONL: each line is one chapter)
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main("./hs_code_by_chapter.json", "./hs_code.json", "./processed.json"))
