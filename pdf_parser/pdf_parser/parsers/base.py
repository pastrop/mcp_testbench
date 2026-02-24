"""Base parser interface for PDF parsing strategies."""

from abc import ABC, abstractmethod
from pathlib import Path

from pdf_parser.models.document import ParsedDocument


class BaseParser(ABC):
    """Abstract base class for PDF parsers."""

    def __init__(self) -> None:
        """Initialize the parser."""
        self.name = self.__class__.__name__

    @abstractmethod
    def can_parse(self, pdf_path: Path) -> bool:
        """
        Check if this parser can handle the given PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            True if the parser can handle this PDF, False otherwise
        """
        pass

    @abstractmethod
    def parse(self, pdf_path: Path) -> ParsedDocument:
        """
        Parse the PDF file and return structured document.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            ParsedDocument containing all extracted elements

        Raises:
            ValueError: If the file cannot be parsed
            FileNotFoundError: If the file doesn't exist
        """
        pass

    def validate_file(self, pdf_path: Path) -> None:
        """
        Validate that the file exists and is a PDF.

        Args:
            pdf_path: Path to validate

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a PDF
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if not pdf_path.is_file():
            raise ValueError(f"Path is not a file: {pdf_path}")

        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {pdf_path}")
