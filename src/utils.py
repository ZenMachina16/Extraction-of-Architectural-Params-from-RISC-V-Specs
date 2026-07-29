"""Utility helpers for logging, YAML parsing, and formatting."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def configure_logging(log_file: Path) -> None:
    """Configure application logging."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def strip_markdown_code_fences(text: str) -> str:
    """Remove surrounding Markdown code fences from model output."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_yaml_text(yaml_text: str) -> dict[str, Any]:
    """Parse a YAML string into a dictionary."""
    parsed = yaml.safe_load(yaml_text) or {}
    if isinstance(parsed, list):
        return {"parameters": parsed}
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a YAML mapping or list.")
    return parsed


def write_yaml_file(data: dict[str, Any], output_path: Path) -> None:
    """Write a dictionary to YAML with stable formatting."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file_handle:
        yaml.safe_dump(
            data,
            file_handle,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        )
