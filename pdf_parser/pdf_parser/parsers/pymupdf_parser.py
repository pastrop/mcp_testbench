"""PyMuPDF-based parser for fast text extraction."""

import re
from pathlib import Path

import fitz  # PyMuPDF

from pdf_parser.models.document import DocumentElement, ElementType, ParsedDocument
from pdf_parser.parsers.base import BaseParser


class PyMuPDFParser(BaseParser):
    """Fast parser using PyMuPDF for text extraction."""

    def can_parse(self, pdf_path: Path) -> bool:
        """Check if PyMuPDF can parse this PDF."""
        try:
            doc = fitz.open(pdf_path)
            can_parse = doc.page_count > 0
            doc.close()
            return can_parse
        except Exception:
            return False

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """
        Parse PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ParsedDocument with extracted content

        Raises:
            ValueError: If parsing fails
        """
        self.validate_file(pdf_path)

        elements: list[DocumentElement] = []

        try:
            doc = fitz.open(pdf_path)

            # Extract metadata
            metadata = self._extract_metadata(doc)

            # Process each page
            for page_num in range(doc.page_count):
                page = doc[page_num]
                page_elements = self._extract_page_elements(page, page_num + 1)
                elements.extend(page_elements)

            doc.close()

            return ParsedDocument(
                filename=pdf_path.name,
                elements=elements,
                metadata=metadata,
                total_pages=doc.page_count,
            )

        except Exception as e:
            raise ValueError(f"Failed to parse PDF with PyMuPDF: {e}") from e

    def _extract_metadata(self, doc: fitz.Document) -> dict:
        """
        Extract document metadata.

        Args:
            doc: PyMuPDF document object

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        if doc.metadata:
            for key, value in doc.metadata.items():
                if value:
                    # Clean up key names
                    clean_key = key.lower().replace(" ", "_")
                    metadata[clean_key] = value

        return metadata

    def _extract_page_elements(
        self, page: fitz.Page, page_num: int
    ) -> list[DocumentElement]:
        """
        Extract elements from a single page.

        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)

        Returns:
            List of document elements
        """
        elements: list[DocumentElement] = []

        # Get text with layout preservation
        text = page.get_text("text")

        if not text.strip():
            return elements

        # Try to detect tables using text blocks
        blocks = page.get_text("dict")["blocks"]
        tables = self._detect_tables(blocks, page_num)
        elements.extend(tables)

        # Process text content
        text_elements = self._process_text(text, page_num)
        elements.extend(text_elements)

        return elements

    def _detect_tables(self, blocks: list, page_num: int) -> list[DocumentElement]:
        """
        Detect tables from text blocks.

        Args:
            blocks: Text blocks from PyMuPDF
            page_num: Page number

        Returns:
            List of table elements
        """
        tables: list[DocumentElement] = []

        # Simple heuristic: look for aligned text blocks that might be tables
        # This is a basic implementation - pdfplumber does this better

        # For now, skip table detection in PyMuPDF
        # Let pdfplumber handle tables
        return tables

    def _process_text(self, text: str, page_num: int) -> list[DocumentElement]:
        """
        Process text and identify structure.

        Args:
            text: Extracted text
            page_num: Page number

        Returns:
            List of text elements
        """
        elements: list[DocumentElement] = []
        lines = text.split("\n")

        current_paragraph = []

        for line in lines:
            line = line.strip()

            if not line:
                # Empty line - paragraph break
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

            # Check if heading
            if self._is_heading(line):
                # Save current paragraph
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
                current_paragraph.append(line)

        # Final paragraph
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
        """Check if line is a heading."""
        patterns = [
            r"^[A-Z][A-Z\s]+$",  # ALL CAPS
            r"^\d+\.\s+[A-Z]",  # Numbered
            r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$",  # Title Case
            r"^(ARTICLE|SECTION|CHAPTER|APPENDIX|TERMS|AGREEMENT)",
        ]

        if len(line) < 100 and any(re.match(pattern, line) for pattern in patterns):
            return True

        return False

    def _detect_heading_level(self, line: str) -> int:
        """Detect heading level."""
        if re.match(r"^\d+\.\s", line):
            return 2
        elif re.match(r"^\d+\.\d+\.\s", line):
            return 3
        elif line.isupper():
            return 2
        return 3
