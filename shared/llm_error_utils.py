"""Shared helpers for detecting LLM quota/credit errors."""

from __future__ import annotations

from typing import Any, Optional


_QUOTA_MESSAGE_HINTS = (
    "insufficient quota",
    "insufficient_quota",
    "exceeded your current quota",
    "quota exceeded",
    "billing_hard_limit",
    "billing hard limit",
    "rate limit",
    "rate_limit",
    "payment required",
    "not enough credits",
    "insufficient credits",
)


def _extract_status_code(error: Any) -> Optional[int]:
    if error is None:
        return None

    for attr in ("status_code", "status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value

    return None


def is_quota_error(error: Any) -> bool:
    status_code = _extract_status_code(error)
    if status_code in (402, 429):
        return True

    message = str(error).lower() if error is not None else ""
    return any(hint in message for hint in _QUOTA_MESSAGE_HINTS)


def quota_error_detail() -> str:
    return "Insufficient quota. Please add more tokens to continue."
