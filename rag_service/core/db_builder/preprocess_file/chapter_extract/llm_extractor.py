import asyncio
import json
import os
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from llama_index.core.llms import ChatMessage
from pydantic import BaseModel, Field, ValidationError

from rag_service.core.llm_wrapper import get_llm


class HSCodeType(str, Enum):
    HS_HEADING = "hs-code_heading"
    HS_SUBHEADING = "hs-code_subheading"


class HSCodeEntry(BaseModel):
    """One HS code entry."""
    hs_code: str = Field(..., description="The HS code, e.g., '0301.99.31'")
    code_type: Optional[HSCodeType] = Field(
        None,
        description="Type of HS code: heading or subheading"
    )
    chapter: str = Field(..., description="2-digit chapter number, e.g., '01', '87'")
    content: str = Field(..., description="Description text belonging to this HS code")
    keywords: List[str] = Field(..., description="8–10 concise English keywords relevant to the HS code")


class ListHScode(BaseModel):
    """List of HS code entries."""
    list_hs_code: List[HSCodeEntry]


# Use multi-provider LLM with fallback support
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1")
llm = get_llm(provider=LLM_PROVIDER, model=LLM_MODEL, temperature=0)


async def parse_hscode_heading(
    sem: asyncio.Semaphore,
    notes: str,
    general: str,
    heading: Dict
) -> List[Dict[str, Any]]:
    prompt = f"""
    You are given part of an HS Code document (Notes, General rules, and one Heading).
    Extract and structure its content into a JSON array of HSCodeEntry objects.
    Find in heading content and extract list of hscode.
    Notes:
    {notes}

    General:
    {general}

    Heading content:
    {heading}
    """
    async with sem:
        try:
            sllm = llm.as_structured_llm(output_cls=ListHScode)
            input_msg = ChatMessage.from_str(prompt)
            output = await sllm.achat([input_msg])

            if isinstance(output, ListHScode):
                return output.model_dump()["list_hs_code"]

            elif isinstance(output.raw, str):
                parsed = json.loads(output.raw)
                return parsed.get("list_hs_code", [])

            elif hasattr(output.raw, "model_dump"):
                return output.raw.model_dump()["list_hs_code"]

            print("⚠️ Unknown output format:", type(output.raw))
            return []

        except (ValidationError, Exception) as e:
            print(f"⚠️ Extract heading error: {e}")
            return []


async def process_chapter(chapter: Dict, processed_ids: set) -> Dict:
    sem = asyncio.Semaphore(4)
    tasks = []

    notes = chapter.get("notes", "")
    general = chapter.get("general", "")
    headings = chapter.get("headings", [])

    for heading in headings:
        heading_id = f'{chapter.get("chapter_number")}_{heading.get("content","")[:30]}'
        if heading_id in processed_ids:
            continue
        tasks.append(parse_hscode_heading(sem, notes, general, heading.get("content", "")))
        processed_ids.add(heading_id)

    results = await asyncio.gather(*tasks)
    hs_json = [item for sublist in results for item in sublist]

    return {
        "chapter_number": chapter.get("chapter_number"),
        "extract_hscode": hs_json,
    }


async def main(input_file: str, output_file: str, state_file: str):
    with open(input_file, "r", encoding="utf-8") as f:
        chapters = json.load(f)

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

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(list(processed_ids), f, ensure_ascii=False, indent=2)

        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main("./hs_code_by_chapter.json", "./hs_code.json", "./processed.json"))
