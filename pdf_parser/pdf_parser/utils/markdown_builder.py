"""Markdown formatting utilities."""

from pdf_parser.models.document import DocumentElement, ElementType, ParsedDocument


class MarkdownBuilder:
    """Builds markdown from parsed document elements."""

    def build(self, document: ParsedDocument) -> str:
        """
        Convert a ParsedDocument to markdown format.

        Args:
            document: The parsed document to convert

        Returns:
            Markdown-formatted string
        """
        lines = []

        # Add document title if available
        if "title" in document.metadata:
            lines.append(f"# {document.metadata['title']}\n")

        # Add metadata if available
        if document.metadata:
            lines.append(self._build_metadata_section(document.metadata))

        # Process elements
        current_page = -1
        for element in document.elements:
            # Add page separator if page changed
            if element.page_number != current_page:
                if current_page != -1:
                    lines.append("\n---\n")
                lines.append(f"**Page {element.page_number}**\n")
                current_page = element.page_number

            # Add element based on type
            lines.append(self._format_element(element))

        return "\n".join(lines)

    def _build_metadata_section(self, metadata: dict) -> str:
        """Build metadata section in markdown."""
        lines = ["## Document Metadata\n"]
        for key, value in metadata.items():
            if key != "title":  # Title is already in heading
                formatted_key = key.replace("_", " ").title()
                lines.append(f"- **{formatted_key}**: {value}")
        lines.append("")
        return "\n".join(lines)

    def _format_element(self, element: DocumentElement) -> str:
        """
        Format a single document element as markdown.

        Args:
            element: The element to format

        Returns:
            Markdown-formatted string
        """
        if element.type == ElementType.HEADING:
            # Determine heading level from metadata or default to h2
            level = element.metadata.get("level", 2)
            return f"{'#' * level} {element.content}\n"

        elif element.type == ElementType.TABLE:
            return self._format_table(element.content) + "\n"

        elif element.type == ElementType.LIST_ITEM:
            return f"- {element.content}"

        elif element.type == ElementType.TEXT:
            # Add paragraph spacing
            return f"{element.content}\n"

        elif element.type == ElementType.IMAGE:
            alt_text = element.metadata.get("alt", "Image")
            return f"![{alt_text}]({element.content})\n"

        return str(element.content)

    def _format_table(self, table_data: list[list[str]]) -> str:
        """
        Format table data as markdown table.

        Args:
            table_data: 2D list representing table rows and columns

        Returns:
            Markdown-formatted table string
        """
        if not table_data:
            return ""

        lines = []

        # First row is header
        if len(table_data) > 0:
            header = table_data[0]
            lines.append("| " + " | ".join(str(cell) for cell in header) + " |")
            lines.append("|" + "|".join("---" for _ in header) + "|")

        # Remaining rows are data
        for row in table_data[1:]:
            # Pad row if needed to match header length
            padded_row = row + [""] * (len(table_data[0]) - len(row))
            lines.append("| " + " | ".join(str(cell) for cell in padded_row) + " |")

        return "\n".join(lines)
