"""Document data models for PDF parsing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ElementType(Enum):
    """Types of document elements."""

    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    LIST_ITEM = "list_item"
    IMAGE = "image"
    METADATA = "metadata"


@dataclass
class DocumentElement:
    """Represents a single element in a document."""

    type: ElementType
    content: str | list[list[str]]
    page_number: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate element type and content."""
        if self.type == ElementType.TABLE and not isinstance(self.content, list):
            raise ValueError("Table content must be a list of lists")
        if self.type != ElementType.TABLE and not isinstance(self.content, str):
            raise ValueError(f"{self.type.value} content must be a string")


@dataclass
class ParsedDocument:
    """Represents a fully parsed PDF document."""

    filename: str
    elements: list[DocumentElement]
    metadata: dict[str, Any] = field(default_factory=dict)
    total_pages: int = 0

    def to_markdown(self) -> str:
        """Convert document to markdown format."""
        from pdf_parser.utils.markdown_builder import MarkdownBuilder

        builder = MarkdownBuilder()
        return builder.build(self)

    def get_elements_by_type(self, element_type: ElementType) -> list[DocumentElement]:
        """Get all elements of a specific type."""
        return [elem for elem in self.elements if elem.type == element_type]

    def get_elements_by_page(self, page_number: int) -> list[DocumentElement]:
        """Get all elements from a specific page."""
        return [elem for elem in self.elements if elem.page_number == page_number]
