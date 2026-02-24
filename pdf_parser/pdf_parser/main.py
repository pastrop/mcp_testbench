"""CLI entry point for PDF to Markdown parser."""

import logging
from pathlib import Path

import click

from pdf_parser.core.config import Config
from pdf_parser.services.export_service import ExportService
from pdf_parser.services.parser_service import ParserService
from pdf_parser.utils.file_handler import FileHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """
    PDF to Markdown Parser - Universal PDF parser with table extraction.

    Convert PDF documents to clean, readable markdown format.
    """
    pass


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path. If not specified, saves to ./output/",
)
@click.option(
    "-p",
    "--parser",
    type=click.Choice(["PDFPlumberParser", "PyMuPDFParser"], case_sensitive=False),
    help="Specific parser to use. Default: auto-select best parser",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
def parse(
    pdf_path: Path, output: Path | None, parser: str | None, verbose: bool
) -> None:
    """
    Parse a single PDF file to markdown.

    Example:
        pdf-parser parse document.pdf

        pdf-parser parse document.pdf -o custom_output.md

        pdf-parser parse document.pdf --parser PDFPlumberParser
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Initialize services
        parser_service = ParserService()
        export_service = ExportService()

        # Parse PDF
        click.echo(f"Parsing: {pdf_path.name}")
        document = parser_service.parse(pdf_path, preferred_parser=parser)

        # Export to markdown
        output_path = export_service.export_markdown(document, output)

        # Display results
        click.echo(f"✓ Successfully parsed {document.total_pages} pages")
        click.echo(f"✓ Extracted {len(document.elements)} elements")
        click.echo(f"✓ Saved to: {output_path}")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./data",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Output directory. Default: ./output/",
)
@click.option(
    "--continue-on-error",
    is_flag=True,
    default=True,
    help="Continue processing if a file fails",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
def batch(
    directory: Path, output_dir: Path | None, continue_on_error: bool, verbose: bool
) -> None:
    """
    Parse all PDF files in a directory.

    Example:
        pdf-parser batch ./data

        pdf-parser batch ./documents -o ./markdown_output
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Find all PDFs
        file_handler = FileHandler()
        pdf_files = file_handler.find_pdf_files(directory)

        if not pdf_files:
            click.echo(f"No PDF files found in {directory}")
            return

        click.echo(f"Found {len(pdf_files)} PDF files")

        # Initialize services
        parser_service = ParserService()
        export_service = ExportService()

        # Set output directory
        if output_dir is None:
            output_dir = Config.get_output_dir()

        # Parse all PDFs
        with click.progressbar(
            pdf_files, label="Parsing PDFs", show_pos=True
        ) as pdf_bar:
            results = {}
            for pdf_path in pdf_bar:
                try:
                    document = parser_service.parse(pdf_path)
                    results[pdf_path] = document
                except Exception as e:
                    logger.error(f"Failed to parse {pdf_path.name}: {e}")
                    if not continue_on_error:
                        raise

        # Export all documents
        click.echo("\nExporting to markdown...")
        successful_docs = {
            k: v for k, v in results.items() if not isinstance(v, Exception)
        }
        export_results = export_service.export_batch(successful_docs, output_dir)

        # Display summary
        click.echo(f"\n✓ Successfully processed {len(export_results)} files")
        click.echo(f"✓ Output directory: {output_dir}")

        if len(export_results) < len(pdf_files):
            failed = len(pdf_files) - len(export_results)
            click.echo(f"✗ {failed} files failed (check logs for details)", err=True)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
def info() -> None:
    """Display information about available parsers."""
    parser_service = ParserService()

    click.echo("PDF to Markdown Parser\n")
    click.echo("Available Parsers:\n")

    parsers_info = {
        "PDFPlumberParser": {
            "description": "Best for table-heavy documents and structured content",
            "type": "Text-based",
            "primary": True,
        },
        "PyMuPDFParser": {
            "description": "Fast text extraction, good for text-heavy documents",
            "type": "Text-based",
            "primary": False,
        },
        "ClaudeVisionParser": {
            "description": "AI-powered extraction for image-based (scanned) PDFs using Claude",
            "type": "Image-based",
            "primary": False,
        },
    }

    # Show available parsers
    for parser in parser_service.parsers:
        parser_name = parser.name
        if parser_name in parsers_info:
            info = parsers_info[parser_name]
            primary = " [PRIMARY]" if info["primary"] else ""
            click.echo(f"  • {parser_name}{primary}")
            click.echo(f"    Type: {info['type']}")
            click.echo(f"    {info['description']}\n")

    # Show Claude Vision status
    from pdf_parser.core.config import Config

    click.echo("\nClaude Vision Status:")
    if Config.has_anthropic_key():
        click.echo("  ✓ Enabled (ANTHROPIC_API_KEY found)")
        click.echo(f"  Model: {Config.CLAUDE_MODEL}")
    else:
        click.echo("  ✗ Disabled (ANTHROPIC_API_KEY not set)")
        click.echo("  To enable: export ANTHROPIC_API_KEY='your-api-key'")

    click.echo("\nStrategy: Smart routing based on PDF type")
    click.echo("  - Text-based PDFs → PDFPlumber/PyMuPDF")
    click.echo("  - Image-based PDFs → Claude Vision (if enabled)")


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
def inspect(pdf_path: Path) -> None:
    """
    Inspect PDF metadata and type without parsing.

    Example:
        pdf-parser inspect document.pdf
    """
    import fitz

    from pdf_parser.utils.pdf_detector import PDFDetector

    try:
        doc = fitz.open(pdf_path)

        click.echo(f"\nPDF Information: {pdf_path.name}\n")
        click.echo(f"  Pages: {doc.page_count}")

        # Check file size
        size_mb = pdf_path.stat().st_size / (1024 * 1024)
        click.echo(f"  Size: {size_mb:.2f} MB")

        # Detect PDF type
        detector = PDFDetector()
        is_image_based = detector.is_image_based(pdf_path)
        pdf_type = "Image-based (scanned)" if is_image_based else "Text-based"
        click.echo(f"  Type: {pdf_type}")

        if is_image_based:
            from pdf_parser.core.config import Config

            if Config.has_anthropic_key():
                click.echo("  → Will use Claude Vision for parsing")
            else:
                click.echo(
                    "  → ⚠️  Set ANTHROPIC_API_KEY to parse with Claude Vision"
                )

        if doc.metadata:
            click.echo("\n  Metadata:")
            for key, value in doc.metadata.items():
                if value:
                    click.echo(f"    {key}: {value}")

        doc.close()

    except Exception as e:
        click.echo(f"✗ Error inspecting PDF: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    cli()
