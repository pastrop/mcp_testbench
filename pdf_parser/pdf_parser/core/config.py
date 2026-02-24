"""Configuration settings for the PDF parser."""

import os
from pathlib import Path


class Config:
    """Application configuration."""

    # Default directories
    DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
    DEFAULT_DATA_DIR = Path.cwd() / "data"

    # Parser settings
    DEFAULT_PARSER = "PDFPlumberParser"
    MIN_TABLE_CONFIDENCE = 0.5

    # LLM settings for image-based PDF processing
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = "claude-3-5-haiku-20241022"  # Haiku for fast, cost-effective processing
    CLAUDE_MAX_TOKENS = 4096
    CLAUDE_TEMPERATURE = 0.0  # Deterministic for document parsing

    # PDF detection settings
    MIN_TEXT_CHARS_PER_PAGE = 50  # Minimum chars to consider page as text-based

    # Logging
    LOG_LEVEL = "INFO"

    @classmethod
    def get_output_dir(cls) -> Path:
        """Get output directory, creating it if needed."""
        cls.DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return cls.DEFAULT_OUTPUT_DIR

    @classmethod
    def has_anthropic_key(cls) -> bool:
        """Check if Anthropic API key is configured."""
        return cls.ANTHROPIC_API_KEY is not None and len(cls.ANTHROPIC_API_KEY) > 0
