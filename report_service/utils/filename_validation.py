"""Filename validation helpers for Report Service."""

import os

CHC_REQUIRED_FILENAME = "Public ECUS data for testing"
DATASET_REQUIRED_FILENAME = "Public HS data for testing"


def _normalize_filename(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def _strip_upload_prefix(base_name: str) -> str:
    parts = base_name.split("_", 2)
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
        return parts[2]
    return base_name


def validate_chc_filename(filename: str) -> None:
    base_name = os.path.splitext(os.path.basename(filename or ""))[0].strip()
    if not base_name:
        raise ValueError("Missing filename. Please rename the file before upload.")

    base_name = _strip_upload_prefix(base_name)
    if _normalize_filename(base_name) != _normalize_filename(CHC_REQUIRED_FILENAME):
        raise ValueError(
            f"Invalid filename. Please rename the file to '{CHC_REQUIRED_FILENAME}'."
        )


def validate_dataset_filename(filename: str) -> None:
    base_name = os.path.splitext(os.path.basename(filename or ""))[0].strip()
    if not base_name:
        raise ValueError("Missing filename. Please rename the file before upload.")

    base_name = _strip_upload_prefix(base_name)
    if _normalize_filename(base_name) != _normalize_filename(DATASET_REQUIRED_FILENAME):
        raise ValueError(
            f"Invalid filename. Please rename the file to '{DATASET_REQUIRED_FILENAME}'."
        )
