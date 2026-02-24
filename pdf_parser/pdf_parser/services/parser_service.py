"""Parser service that orchestrates different parsing strategies."""

import logging
from pathlib import Path

from pdf_parser.core.config import Config
from pdf_parser.models.document import ParsedDocument
from pdf_parser.parsers.base import BaseParser
from pdf_parser.parsers.pdfplumber_parser import PDFPlumberParser
from pdf_parser.parsers.pymupdf_parser import PyMuPDFParser
from pdf_parser.utils.pdf_detector import PDFDetector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParserService:
    """
    Service that manages multiple parsers and selects the best one.

    Uses a cascade strategy:
    1. Try PDFPlumber (best for tables and structured documents)
    2. Fallback to PyMuPDF (faster, good for text-heavy documents)
    3. For image-based PDFs: Try Claude Vision (if API key available)
    """

    def __init__(self) -> None:
        """Initialize the parser service with available parsers."""
        self.parsers: list[BaseParser] = [
            PDFPlumberParser(),  # Primary: excellent for tables
            PyMuPDFParser(),  # Fallback: fast text extraction
        ]

        # Add Claude Vision parser if API key is available
        if Config.has_anthropic_key():
            try:
                from pdf_parser.parsers.claude_vision_parser import ClaudeVisionParser

                self.parsers.append(ClaudeVisionParser())
                logger.info("Claude Vision parser enabled (ANTHROPIC_API_KEY found)")
            except Exception as e:
                logger.warning(f"Could not initialize Claude Vision parser: {e}")
        else:
            logger.info(
                "Claude Vision parser disabled (set ANTHROPIC_API_KEY to enable)"
            )

        self.detector = PDFDetector()

    def parse(self, pdf_path: Path, preferred_parser: str | None = None) -> ParsedDocument:
        """
        Parse a PDF using the best available parser.

        Intelligently routes to appropriate parser based on PDF type:
        - Text-based PDFs: Uses PDFPlumber or PyMuPDF
        - Image-based PDFs: Uses Claude Vision (if available)

        Args:
            pdf_path: Path to the PDF file
            preferred_parser: Optional name of preferred parser

        Returns:
            ParsedDocument containing extracted content

        Raises:
            ValueError: If no parser can handle the file
            FileNotFoundError: If file doesn't exist
        """
        pdf_path = Path(pdf_path)

        logger.info(f"Parsing PDF: {pdf_path.name}")

        # Detect if PDF is image-based
        is_image_based = self.detector.is_image_based(pdf_path)
        logger.info(
            f"PDF type: {'image-based (scanned)' if is_image_based else 'text-based'}"
        )

        # If preferred parser specified, try it first
        if preferred_parser:
            parser = self._get_parser_by_name(preferred_parser)
            if parser:
                logger.info(f"Using preferred parser: {parser.name}")
                try:
                    return parser.parse(pdf_path)
                except Exception as e:
                    logger.warning(
                        f"Preferred parser {parser.name} failed: {e}. "
                        "Falling back to cascade strategy."
                    )

        # Smart routing: Try appropriate parsers based on PDF type
        if is_image_based:
            # For image-based PDFs, prioritize Claude Vision
            result = self._try_image_based_parsers(pdf_path)
            if result:
                return result
        else:
            # For text-based PDFs, try text extraction parsers first
            result = self._try_text_based_parsers(pdf_path)
            if result:
                return result

        # If smart routing didn't work, try all parsers as fallback
        logger.info("Smart routing failed, trying all parsers...")
        for parser in self.parsers:
            logger.info(f"Trying parser: {parser.name}")

            if not parser.can_parse(pdf_path):
                logger.info(f"{parser.name} cannot parse this file, skipping")
                continue

            try:
                document = parser.parse(pdf_path)
                logger.info(
                    f"Successfully parsed with {parser.name}: "
                    f"{len(document.elements)} elements extracted"
                )
                return document
            except Exception as e:
                logger.warning(f"{parser.name} failed: {e}")
                continue

        # If all parsers fail
        error_msg = f"No parser could successfully parse {pdf_path.name}. "
        if is_image_based and not Config.has_anthropic_key():
            error_msg += (
                "This appears to be an image-based PDF. "
                "Set ANTHROPIC_API_KEY environment variable to enable Claude Vision parsing."
            )
        else:
            error_msg += "The PDF might be corrupted or encrypted."

        raise ValueError(error_msg)

    def _try_text_based_parsers(self, pdf_path: Path) -> ParsedDocument | None:
        """
        Try text-based parsers (PDFPlumber, PyMuPDF).

        Args:
            pdf_path: Path to PDF

        Returns:
            ParsedDocument if successful, None otherwise
        """
        text_parsers = [p for p in self.parsers if "Vision" not in p.name]

        for parser in text_parsers:
            logger.info(f"Trying text parser: {parser.name}")

            if not parser.can_parse(pdf_path):
                continue

            try:
                document = parser.parse(pdf_path)
                logger.info(
                    f"Successfully parsed with {parser.name}: "
                    f"{len(document.elements)} elements extracted"
                )
                return document
            except Exception as e:
                logger.warning(f"{parser.name} failed: {e}")
                continue

        return None

    def _try_image_based_parsers(self, pdf_path: Path) -> ParsedDocument | None:
        """
        Try image-based parsers (Claude Vision).

        Args:
            pdf_path: Path to PDF

        Returns:
            ParsedDocument if successful, None otherwise
        """
        vision_parsers = [p for p in self.parsers if "Vision" in p.name]

        if not vision_parsers:
            logger.warning(
                "No vision parser available for image-based PDF. "
                "Set ANTHROPIC_API_KEY to enable Claude Vision."
            )
            return None

        for parser in vision_parsers:
            logger.info(f"Trying vision parser: {parser.name}")

            if not parser.can_parse(pdf_path):
                continue

            try:
                document = parser.parse(pdf_path)
                logger.info(
                    f"Successfully parsed with {parser.name}: "
                    f"{len(document.elements)} elements extracted"
                )
                return document
            except Exception as e:
                logger.warning(f"{parser.name} failed: {e}")
                continue

        return None

    def _get_parser_by_name(self, name: str) -> BaseParser | None:
        """
        Get parser by class name.

        Args:
            name: Parser class name

        Returns:
            Parser instance or None if not found
        """
        for parser in self.parsers:
            if parser.name.lower() == name.lower():
                return parser
        return None

    def parse_batch(
        self, pdf_paths: list[Path], continue_on_error: bool = True
    ) -> dict[Path, ParsedDocument | Exception]:
        """
        Parse multiple PDFs.

        Args:
            pdf_paths: List of PDF paths to parse
            continue_on_error: If True, continue parsing even if one fails

        Returns:
            Dictionary mapping paths to ParsedDocument or Exception
        """
        results: dict[Path, ParsedDocument | Exception] = {}

        logger.info(f"Batch parsing {len(pdf_paths)} PDFs")

        for pdf_path in pdf_paths:
            try:
                document = self.parse(pdf_path)
                results[pdf_path] = document
            except Exception as e:
                logger.error(f"Failed to parse {pdf_path.name}: {e}")
                results[pdf_path] = e

                if not continue_on_error:
                    break

        successful = sum(
            1 for v in results.values() if isinstance(v, ParsedDocument)
        )
        logger.info(f"Batch complete: {successful}/{len(pdf_paths)} successful")

        return results

    def list_parsers(self) -> list[str]:
        """
        Get list of available parser names.

        Returns:
            List of parser class names
        """
        return [parser.name for parser in self.parsers]
