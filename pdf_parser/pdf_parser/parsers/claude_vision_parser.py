"""Claude Vision parser for image-based PDFs."""

import logging
from pathlib import Path

from anthropic import Anthropic

from pdf_parser.core.config import Config
from pdf_parser.models.document import DocumentElement, ElementType, ParsedDocument
from pdf_parser.parsers.base import BaseParser
from pdf_parser.utils.pdf_detector import PDFDetector

logger = logging.getLogger(__name__)


class ClaudeVisionParser(BaseParser):
    """Parser using Claude Vision for image-based (scanned) PDFs."""

    def __init__(self) -> None:
        """Initialize Claude Vision parser."""
        super().__init__()

        if not Config.has_anthropic_key():
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Claude Vision parser requires an API key."
            )

        self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.CLAUDE_MODEL
        self.detector = PDFDetector()

    def can_parse(self, pdf_path: Path) -> bool:
        """
        Check if this parser can handle the PDF.

        Returns True only for image-based PDFs and if API key is available.
        """
        if not Config.has_anthropic_key():
            return False

        # Only process image-based PDFs
        return self.detector.is_image_based(pdf_path)

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """
        Parse image-based PDF using Claude Vision.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ParsedDocument with extracted content

        Raises:
            ValueError: If parsing fails
        """
        self.validate_file(pdf_path)

        logger.info(f"Using Claude Vision to parse image-based PDF: {pdf_path.name}")

        try:
            # Extract all pages as images
            page_images = self.detector.extract_all_pages_as_images(pdf_path)
            logger.info(f"Extracted {len(page_images)} pages as images")

            # Process each page with Claude
            elements: list[DocumentElement] = []

            for page_num, image_bytes in enumerate(page_images, start=1):
                logger.info(f"Processing page {page_num}/{len(page_images)} with Claude...")
                page_elements = self._process_page_with_claude(
                    image_bytes, page_num, pdf_path.name
                )
                elements.extend(page_elements)

            return ParsedDocument(
                filename=pdf_path.name,
                elements=elements,
                metadata={"parser": "ClaudeVisionParser", "model": self.model},
                total_pages=len(page_images),
            )

        except Exception as e:
            raise ValueError(f"Failed to parse PDF with Claude Vision: {e}") from e

    def _process_page_with_claude(
        self, image_bytes: bytes, page_num: int, filename: str
    ) -> list[DocumentElement]:
        """
        Process a single page image with Claude Vision.

        Args:
            image_bytes: PNG image bytes
            page_num: Page number (1-indexed)
            filename: PDF filename for context

        Returns:
            List of extracted document elements
        """
        # Encode image to base64
        image_base64 = self.detector.encode_image_base64(image_bytes)

        # Create prompt for Claude
        prompt = self._create_extraction_prompt(filename, page_num)

        # Call Claude API
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=Config.CLAUDE_MAX_TOKENS,
                temperature=Config.CLAUDE_TEMPERATURE,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            # Extract text content from response
            response_text = message.content[0].text

            # Parse response into document elements
            elements = self._parse_claude_response(response_text, page_num)

            return elements

        except Exception as e:
            logger.error(f"Claude API error on page {page_num}: {e}")
            # Return empty elements rather than failing completely
            return []

    def _create_extraction_prompt(self, filename: str, page_num: int) -> str:
        """
        Create extraction prompt for Claude.

        Args:
            filename: PDF filename
            page_num: Page number

        Returns:
            Prompt string
        """
        return f"""You are processing page {page_num} from a PDF document: {filename}

Please extract ALL text content from this image in markdown format. Follow these guidelines:

1. **Preserve structure**: Identify and mark headings with appropriate markdown (# ## ###)
2. **Tables**: Format any tables as markdown tables with proper alignment
3. **Lists**: Use markdown list syntax (- or 1. 2. 3.)
4. **Text formatting**: Use **bold** for emphasized text if clearly visible
5. **Accuracy**: Extract text exactly as it appears, preserving spelling and formatting
6. **Completeness**: Extract ALL visible text, including headers, footers, page numbers

Output the content in clean markdown format. Do NOT add any commentary or explanations - just output the extracted markdown content."""

    def _parse_claude_response(
        self, response_text: str, page_num: int
    ) -> list[DocumentElement]:
        """
        Parse Claude's markdown response into document elements.

        Args:
            response_text: Markdown text from Claude
            page_num: Page number

        Returns:
            List of document elements
        """
        elements: list[DocumentElement] = []

        # Split response into lines
        lines = response_text.split("\n")

        current_paragraph = []
        in_table = False
        table_rows = []

        for line in lines:
            line_stripped = line.strip()

            # Detect markdown table
            if line_stripped.startswith("|") and "|" in line_stripped[1:]:
                in_table = True
                # Parse table row
                cells = [cell.strip() for cell in line_stripped.split("|")[1:-1]]
                table_rows.append(cells)
                continue
            elif in_table and not line_stripped.startswith("|"):
                # End of table
                if table_rows and len(table_rows) > 1:
                    # Filter out separator rows (----)
                    clean_rows = [
                        row
                        for row in table_rows
                        if not all(
                            cell.replace("-", "").strip() == "" for cell in row
                        )
                    ]
                    if clean_rows:
                        elements.append(
                            DocumentElement(
                                type=ElementType.TABLE,
                                content=clean_rows,
                                page_number=page_num,
                            )
                        )
                table_rows = []
                in_table = False

            # Skip table separator lines and empty lines in non-paragraph context
            if not line_stripped or line_stripped.startswith("|---"):
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

            # Detect headings
            if line_stripped.startswith("#"):
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

                # Extract heading
                heading_level = len(line_stripped) - len(line_stripped.lstrip("#"))
                heading_text = line_stripped.lstrip("#").strip()

                elements.append(
                    DocumentElement(
                        type=ElementType.HEADING,
                        content=heading_text,
                        page_number=page_num,
                        metadata={"level": heading_level},
                    )
                )
            else:
                # Regular text
                current_paragraph.append(line_stripped)

        # Add final paragraph if any
        if current_paragraph:
            elements.append(
                DocumentElement(
                    type=ElementType.TEXT,
                    content=" ".join(current_paragraph),
                    page_number=page_num,
                )
            )

        # Add final table if any
        if table_rows and len(table_rows) > 1:
            clean_rows = [
                row
                for row in table_rows
                if not all(cell.replace("-", "").strip() == "" for cell in row)
            ]
            if clean_rows:
                elements.append(
                    DocumentElement(
                        type=ElementType.TABLE,
                        content=clean_rows,
                        page_number=page_num,
                    )
                )

        return elements
