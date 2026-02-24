"""PDFPlumber-based parser for table-heavy documents."""

import re
from pathlib import Path

import pdfplumber

from pdf_parser.models.document import DocumentElement, ElementType, ParsedDocument
from pdf_parser.parsers.base import BaseParser


class PDFPlumberParser(BaseParser):
    """Parser using pdfplumber for precise table and text extraction."""

    def __init__(self, min_table_confidence: float = 0.5) -> None:
        """
        Initialize the PDFPlumber parser.

        Args:
            min_table_confidence: Minimum confidence threshold for table detection
        """
        super().__init__()
        self.min_table_confidence = min_table_confidence

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if pdfplumber can parse this PDF."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Check if we can access pages
                return len(pdf.pages) > 0
        except Exception:
            return False

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """
        Parse PDF using pdfplumber.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ParsedDocument with extracted content

        Raises:
            ValueError: If parsing fails
        """
        self.validate_file(pdf_path)

        elements: list[DocumentElement] = []
        metadata = {}

        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extract metadata
                if pdf.metadata:
                    metadata = {
                        key.replace("/", ""): value
                        for key, value in pdf.metadata.items()
                        if value is not None
                    }

                # Process each page
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_elements = self._extract_page_elements(page, page_num)
                    elements.extend(page_elements)

                return ParsedDocument(
                    filename=pdf_path.name,
                    elements=elements,
                    metadata=metadata,
                    total_pages=len(pdf.pages),
                )

        except Exception as e:
            raise ValueError(f"Failed to parse PDF with pdfplumber: {e}") from e

    def _extract_page_elements(
        self, page: pdfplumber.page.Page, page_num: int
    ) -> list[DocumentElement]:
        """
        Extract elements from a single page.

        Args:
            page: pdfplumber page object
            page_num: Page number (1-indexed)

        Returns:
            List of document elements
        """
        elements: list[DocumentElement] = []

        # Extract tables first
        tables = page.extract_tables()
        table_bboxes = [table.bbox for table in page.find_tables()]

        for table_data in tables:
            if table_data and len(table_data) > 0:
                # Clean table data
                cleaned_table = self._clean_table_data(table_data)
                if cleaned_table:
                    elements.append(
                        DocumentElement(
                            type=ElementType.TABLE,
                            content=cleaned_table,
                            page_number=page_num,
                        )
                    )

        # Extract text, filtering out table regions
        text = page.extract_text(layout=True)

        if text:
            # Split into paragraphs and identify headings
            text_elements = self._process_text(text, page_num)
            elements.extend(text_elements)

        return elements

    def _clean_table_data(self, table_data: list[list[str | None]]) -> list[list[str]]:
        """
        Clean and normalize table data.

        Args:
            table_data: Raw table data from pdfplumber

        Returns:
            Cleaned table data with empty cells replaced
        """
        cleaned = []
        for row in table_data:
            # Replace None with empty string and strip whitespace
            cleaned_row = [
                (str(cell).strip() if cell is not None else "") for cell in row
            ]
            # Only include rows that have at least one non-empty cell
            if any(cell for cell in cleaned_row):
                cleaned.append(cleaned_row)

        return cleaned if len(cleaned) > 1 else []

    def _process_text(self, text: str, page_num: int) -> list[DocumentElement]:
        """
        Process text and identify structure (headings, paragraphs).

        Args:
            text: Extracted text content
            page_num: Page number

        Returns:
            List of text elements with appropriate types
        """
        elements: list[DocumentElement] = []
        lines = text.split("\n")

        current_paragraph = []

        for line in lines:
            line = line.strip()

            if not line:
                # Empty line - end current paragraph if any
                if current_paragraph:
                    elements.append(
                        DocumentElement(
                            type=ElementType.TEXT,
                            content=" ".join(current_paragraph),
                            page_number=page_num,
                        )
                    )
                    current_paragraph = []
                continue

            # Check if line is a heading
            if self._is_heading(line):
                # Save current paragraph first
                if current_paragraph:
                    elements.append(
                        DocumentElement(
                            type=ElementType.TEXT,
                            content=" ".join(current_paragraph),
                            page_number=page_num,
                        )
                    )
                    current_paragraph = []

                # Add heading
                heading_level = self._detect_heading_level(line)
                elements.append(
                    DocumentElement(
                        type=ElementType.HEADING,
                        content=line,
                        page_number=page_num,
                        metadata={"level": heading_level},
                    )
                )
            else:
                # Regular text - add to current paragraph
                current_paragraph.append(line)

        # Add final paragraph if any
        if current_paragraph:
            elements.append(
                DocumentElement(
                    type=ElementType.TEXT,
                    content=" ".join(current_paragraph),
                    page_number=page_num,
                )
            )

        return elements

    def _is_heading(self, line: str) -> bool:
        """
        Detect if a line is likely a heading.

        Args:
            line: Text line to check

        Returns:
            True if line appears to be a heading
        """
        # Common heading patterns
        patterns = [
            r"^[A-Z][A-Z\s]+$",  # ALL CAPS
            r"^\d+\.\s+[A-Z]",  # Numbered heading (1. Title)
            r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$",  # Title Case
            r"^(ARTICLE|SECTION|CHAPTER|APPENDIX)",  # Common heading words
        ]

        # Short lines that are capitalized are often headings
        if len(line) < 100 and any(re.match(pattern, line) for pattern in patterns):
            return True

        return False

    def _detect_heading_level(self, line: str) -> int:
        """
        Detect heading level (1-6).

        Args:
            line: Heading text

        Returns:
            Heading level (default: 2)
        """
        # If starts with number like "1.", "1.1.", it's a structured heading
        if re.match(r"^\d+\.\s", line):
            return 2  # h2 for main sections
        elif re.match(r"^\d+\.\d+\.\s", line):
            return 3  # h3 for subsections

        # ALL CAPS are typically major headings
        if line.isupper():
            return 2

        # Default to h3
        return 3
