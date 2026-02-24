"""Utilities for detecting PDF type and extracting images."""

import base64
import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from pdf_parser.core.config import Config


class PDFDetector:
    """Detects PDF type and extracts images from PDF pages."""

    @staticmethod
    def is_image_based(pdf_path: Path) -> bool:
        """
        Detect if PDF is image-based (scanned) or text-based.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if PDF appears to be image-based, False if text-based
        """
        try:
            doc = fitz.open(pdf_path)

            # Sample first 3 pages to determine type
            pages_to_check = min(3, doc.page_count)
            text_char_counts = []

            for page_num in range(pages_to_check):
                page = doc[page_num]
                text = page.get_text("text").strip()
                text_char_counts.append(len(text))

            doc.close()

            # If average text per page is below threshold, it's likely image-based
            avg_chars = sum(text_char_counts) / len(text_char_counts)
            is_image_based = avg_chars < Config.MIN_TEXT_CHARS_PER_PAGE

            return is_image_based

        except Exception:
            # If we can't determine, assume text-based (safer default)
            return False

    @staticmethod
    def extract_page_as_image(
        pdf_path: Path, page_num: int, dpi: int = 150
    ) -> bytes:
        """
        Extract a PDF page as PNG image bytes.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            dpi: Resolution for image extraction

        Returns:
            PNG image as bytes

        Raises:
            ValueError: If page extraction fails
        """
        try:
            doc = fitz.open(pdf_path)

            if page_num >= doc.page_count:
                raise ValueError(f"Page {page_num} does not exist in PDF")

            page = doc[page_num]

            # Render page to pixmap (image)
            mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI is default
            pix = page.get_pixmap(matrix=mat)

            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")

            doc.close()

            return img_data

        except Exception as e:
            raise ValueError(f"Failed to extract page {page_num} as image: {e}") from e

    @staticmethod
    def extract_all_pages_as_images(
        pdf_path: Path, dpi: int = 150
    ) -> list[bytes]:
        """
        Extract all PDF pages as PNG images.

        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for image extraction

        Returns:
            List of PNG images as bytes
        """
        doc = fitz.open(pdf_path)
        images = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            images.append(img_data)

        doc.close()
        return images

    @staticmethod
    def encode_image_base64(image_bytes: bytes) -> str:
        """
        Encode image bytes to base64 string.

        Args:
            image_bytes: Image data as bytes

        Returns:
            Base64 encoded string
        """
        return base64.standard_b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def get_pdf_page_count(pdf_path: Path) -> int:
        """
        Get number of pages in PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of pages
        """
        doc = fitz.open(pdf_path)
        count = doc.page_count
        doc.close()
        return count
