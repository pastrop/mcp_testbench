"""File handling utilities."""

from pathlib import Path


class FileHandler:
    """Handles file I/O operations."""

    @staticmethod
    def save_markdown(content: str, output_path: Path) -> None:
        """
        Save markdown content to file.

        Args:
            content: Markdown content to save
            output_path: Path where to save the file

        Raises:
            IOError: If file cannot be written
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def get_output_path(pdf_path: Path, output_dir: Path | None = None) -> Path:
        """
        Generate output path for markdown file.

        Args:
            pdf_path: Path to input PDF
            output_dir: Optional output directory. If None, uses current directory.

        Returns:
            Path object for the output markdown file
        """
        if output_dir is None:
            output_dir = Path.cwd() / "output"

        # Create filename: original_name.pdf -> original_name.md
        markdown_filename = pdf_path.stem + ".md"
        return output_dir / markdown_filename

    @staticmethod
    def find_pdf_files(directory: Path) -> list[Path]:
        """
        Find all PDF files in a directory.

        Args:
            directory: Directory to search

        Returns:
            List of PDF file paths
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        return sorted(directory.glob("*.pdf"))
