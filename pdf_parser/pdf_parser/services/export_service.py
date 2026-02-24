"""Export service for saving parsed documents."""

import logging
from pathlib import Path

from pdf_parser.models.document import ParsedDocument
from pdf_parser.utils.file_handler import FileHandler

logger = logging.getLogger(__name__)


class ExportService:
    """Handles exporting parsed documents to various formats."""

    def __init__(self) -> None:
        """Initialize the export service."""
        self.file_handler = FileHandler()

    def export_markdown(
        self, document: ParsedDocument, output_path: Path | None = None
    ) -> Path:
        """
        Export document as markdown.

        Args:
            document: Parsed document to export
            output_path: Optional output path. If None, auto-generates path.

        Returns:
            Path where file was saved

        Raises:
            IOError: If file cannot be written
        """
        # Generate markdown content
        markdown_content = document.to_markdown()

        # Determine output path
        if output_path is None:
            # Auto-generate path in output directory
            pdf_name = Path(document.filename).stem
            output_path = Path.cwd() / "output" / f"{pdf_name}.md"

        # Save to file
        self.file_handler.save_markdown(markdown_content, output_path)
        logger.info(f"Exported markdown to: {output_path}")

        return output_path

    def export_batch(
        self, documents: dict[Path, ParsedDocument], output_dir: Path | None = None
    ) -> dict[Path, Path]:
        """
        Export multiple documents to markdown.

        Args:
            documents: Dictionary mapping PDF paths to ParsedDocuments
            output_dir: Optional output directory

        Returns:
            Dictionary mapping input paths to output paths
        """
        if output_dir is None:
            output_dir = Path.cwd() / "output"

        results: dict[Path, Path] = {}

        for pdf_path, document in documents.items():
            output_path = self.file_handler.get_output_path(pdf_path, output_dir)
            exported_path = self.export_markdown(document, output_path)
            results[pdf_path] = exported_path

        logger.info(f"Batch export complete: {len(results)} files saved")

        return results
