"""LLM clients and extraction workflow for parameter generation."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from src.models import AppConfig, ExtractionDocument, ExtractionMetadata, ExtractionPayload
from src.utils import parse_yaml_text, strip_markdown_code_fences, utc_timestamp, write_yaml_file


class RateLimitException(Exception):
    """Raised when an LLM provider returns a rate limit error."""


class BaseLLMClient(ABC):
    """Common interface for model providers."""

    def __init__(self, model_name: str, temperature: float) -> None:
        self.model_name = model_name
        self.temperature = temperature

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate text from a prompt."""


class GeminiClient(BaseLLMClient):
    """Gemini implementation of the LLM client interface."""

    def __init__(self, model_name: str, api_key: str, temperature: float) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=api_key)
        self._types = types

    @property
    def provider_name(self) -> str:
        return "gemini"

    def generate(self, prompt: str) -> str:
        """Generate YAML text with Gemini."""
        from google.genai.errors import APIError
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=self.temperature,
                ),
            )
        except APIError as exc:
            if exc.code in (429, 503) or "429" in str(exc) or "503" in str(exc):
                raise RateLimitException(str(exc)) from exc
            raise
        except Exception as exc:
            if getattr(exc, "status_code", None) in (429, 503) or "429" in str(exc) or "503" in str(exc):
                raise RateLimitException(str(exc)) from exc
            raise

        text = getattr(response, "text", "")
        if not text:
            raise ValueError("Gemini returned an empty response.")
        return text


class OpenAIClient(BaseLLMClient):
    """OpenAI implementation of the LLM client interface."""

    def __init__(self, model_name: str, api_key: str, temperature: float) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "openai"

    def generate(self, prompt: str) -> str:
        """Generate YAML text with OpenAI."""
        import openai

        kwargs = {
            "model": self.model_name,
            "input": prompt,
        }
        if not (self.model_name.startswith("o1") or self.model_name.startswith("o3")):
            kwargs["temperature"] = self.temperature

        try:
            try:
                response = self._client.responses.create(**kwargs)
            except openai.BadRequestError as exc:
                if "temperature" in str(exc):
                    kwargs.pop("temperature", None)
                    response = self._client.responses.create(**kwargs)
                else:
                    raise
        except openai.RateLimitError as exc:
            raise RateLimitException(str(exc)) from exc

        text = response.output_text
        if not text:
            raise ValueError("OpenAI returned an empty response.")
        return text


class GroqClient(BaseLLMClient):
    """Groq implementation of the LLM client interface."""

    def __init__(self, model_name: str, api_key: str, temperature: float) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

        from groq import Groq

        self._client = Groq(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "groq"

    def generate(self, prompt: str) -> str:
        """Generate YAML text with Groq."""
        import groq

        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
        except groq.RateLimitError as exc:
            raise RateLimitException(str(exc)) from exc

        text = response.choices[0].message.content
        if not text:
            raise ValueError("Groq returned an empty response.")
        return text


def create_llm_client(config: AppConfig) -> BaseLLMClient:
    """Instantiate the configured provider client."""
    if config.model_provider == "gemini":
        if not config.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required for MODEL_PROVIDER=gemini.")
        return GeminiClient(
            model_name=config.model_name,
            api_key=config.google_api_key,
            temperature=config.temperature,
        )

    if config.model_provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for MODEL_PROVIDER=openai.")
        return OpenAIClient(
            model_name=config.model_name,
            api_key=config.openai_api_key,
            temperature=config.temperature,
        )

    if config.model_provider == "groq":
        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for MODEL_PROVIDER=groq.")
        return GroqClient(
            model_name=config.model_name,
            api_key=config.groq_api_key,
            temperature=config.temperature,
        )

    raise ValueError(f"Unsupported MODEL_PROVIDER: {config.model_provider}")


class ParameterExtractor:
    """Extract architectural parameters from specification snippets."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.prompt_template = self._load_prompt(config.prompt_path)
        self.client = create_llm_client(config)
        logging.info("%s model used: %s", self.client.provider_name.title(), self.client.model_name)

    def _load_prompt(self, prompt_path: Path) -> str:
        """Load the extraction prompt from disk."""
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8").strip()

    def _build_prompt(self, snippet_text: str) -> str:
        """Append the specification snippet to the prompt."""
        return f"{self.prompt_template}\n{snippet_text.strip()}\n"

    def _generate_with_retry(self, prompt: str) -> str:
        """Call the LLM with exponential backoff on rate limiting."""
        attempt = 0
        while True:
            try:
                return self.client.generate(prompt)
            except RateLimitException as exc:
                if attempt >= self.config.max_retries:
                    logging.error("Retry limit reached: %s", exc)
                    raise

                delay = self.config.backoff_base_seconds * (2 ** attempt)
                logging.warning(
                    "Retry attempt %s after rate limit from %s; sleeping %.1f seconds",
                    attempt + 1,
                    self.client.provider_name,
                    delay,
                )
                time.sleep(delay)
                attempt += 1

    def _parse_response(self, response_text: str) -> ExtractionPayload:
        """Strip fences, parse YAML, and validate the payload."""
        clean_text = strip_markdown_code_fences(response_text)
        parsed = parse_yaml_text(clean_text)
        return ExtractionPayload.model_validate(parsed)

    def extract(self, input_path: Path) -> ExtractionDocument:
        """Extract validated parameters from a snippet file."""
        logging.info("Processing file: %s", input_path.name)
        snippet_text = input_path.read_text(encoding="utf-8")
        prompt = self._build_prompt(snippet_text)
        response_text = self._generate_with_retry(prompt)
        payload = self._parse_response(response_text)

        document = ExtractionDocument(
            metadata=ExtractionMetadata(
                provider=self.client.provider_name,
                model=self.client.model_name,
                source_file=input_path.name,
                generated_at=utc_timestamp(),
            ),
            parameters=payload.parameters,
        )

        logging.info(
            "Number of extracted parameters for %s: %s",
            input_path.name,
            len(document.parameters),
        )
        return document

    def save_output(self, document: ExtractionDocument, output_path: Path) -> None:
        """Save the validated extraction document to a YAML file."""
        write_yaml_file(document.model_dump(mode="python"), output_path)
        logging.info("Output filename: %s", output_path.name)
