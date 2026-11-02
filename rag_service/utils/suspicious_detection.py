import hashlib
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("rag_service.security")

PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("prompt_injection_ignore", re.compile(r"ignore\s+(all|previous|prior)\s+instructions", re.I)),
    ("prompt_injection_system", re.compile(r"system\s+prompt|developer\s+message", re.I)),
    ("prompt_injection_bypass", re.compile(r"bypass\s+policy|override\s+policy", re.I)),
    ("prompt_injection_jailbreak", re.compile(r"jailbreak|do\s+anything\s+now|\bdan\b", re.I)),
    ("prompt_injection_role", re.compile(r"you\s+are\s+chatgpt|act\s+as\s+a\s+system", re.I)),
    ("prompt_injection_leak", re.compile(r"reveal\s+the\s+system|show\s+the\s+prompt", re.I)),
]

FIELDS_TO_SCAN = [
    "product_name",
    "product_description",
    "function",
    "material",
    "specifications",
    "other_information",
]


def _hash_request(values: List[str]) -> str:
    joined = "|".join(values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def detect_suspicious_request(
    query_data: Dict[str, Any],
    endpoint: str,
    collection_name: str,
) -> None:
    values: List[str] = []
    matches: List[Tuple[str, str]] = []

    for field in FIELDS_TO_SCAN:
        raw_value = query_data.get(field)
        if not raw_value:
            continue
        text = str(raw_value)
        values.append(text)
        for pattern_id, pattern in PATTERNS:
            if pattern.search(text):
                matches.append((pattern_id, field))

    if not matches:
        return

    request_hash = _hash_request(values)
    matched_patterns = sorted({pattern_id for pattern_id, _ in matches})
    matched_fields = sorted({field for _, field in matches})

    logger.warning(
        "Suspicious search request detected endpoint=%s collection=%s patterns=%s fields=%s request_hash=%s",
        endpoint,
        collection_name,
        matched_patterns,
        matched_fields,
        request_hash,
    )
