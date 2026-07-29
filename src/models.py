"""Data models and configuration for the extraction pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


ModelProvider = Literal["gemini", "openai", "groq"]


class Parameter(BaseModel):
    """A single extracted architectural parameter."""

    name: str
    description: str
    classification: str
    type: str
    constraints: List[str] | str
    evidence_quote: str

    @field_validator("constraints")
    @classmethod
    def parse_constraints(cls, v):
        if isinstance(v, str):
            if v.lower() == "unspecified":
                return []
            return [v]
        return v


class ExtractionMetadata(BaseModel):
    """Metadata stored alongside extracted parameters."""

    provider: str
    model: str
    source_file: str
    generated_at: str


class ExtractionDocument(BaseModel):
    """Validated YAML document structure."""

    metadata: ExtractionMetadata
    parameters: List[Parameter]


class ExtractionPayload(BaseModel):
    """LLM response structure prior to metadata injection."""

    parameters: List[Parameter] = Field(default_factory=list)


class AppConfig(BaseModel):
    """Application configuration loaded from environment variables."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_provider: ModelProvider
    model_name: str
    google_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    prompt_path: Path
    input_dir: Path
    output_dir: Path
    log_file: Path
    temperature: float = 0.1
    max_retries: int = 5
    backoff_base_seconds: float = 2.0

    @classmethod
    def from_env(cls, project_root: Path) -> "AppConfig":
        """Create configuration from environment variables."""
        provider = os.getenv("MODEL_PROVIDER", "gemini").strip().lower()
        model_name = os.getenv("MODEL_NAME", "").strip()

        prompt_path = project_root / "prompts" / "extraction_prompt.md"
        input_dir = project_root / "input"
        output_dir = project_root / "output"
        log_file = project_root / "extraction.log"

        if not model_name:
            model_name = (
                "gemini-2.0-flash-lite-001"
                if provider == "gemini"
                else "gpt-5"
            )

        try:
            return cls(
                model_provider=provider,  # type: ignore[arg-type]
                model_name=model_name,
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                groq_api_key=os.getenv("GROQ_API_KEY"),
                prompt_path=prompt_path,
                input_dir=input_dir,
                output_dir=output_dir,
                log_file=log_file,
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration: {exc}") from exc
