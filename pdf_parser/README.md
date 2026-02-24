# PDF to Markdown Parser

A universal PDF parser that converts PDF documents to clean, readable markdown format with intelligent table extraction.

## Features

- **Universal Parsing**: Handles both text-based AND image-based (scanned) PDFs
- **Smart Routing**: Automatically detects PDF type and uses appropriate parser
- **Table Preservation**: Intelligent table detection and markdown formatting
- **Claude Vision Integration**: AI-powered parsing for scanned/image-based PDFs
- **Batch Processing**: Process entire directories of PDFs
- **Multiple Parsers**: Cascade strategy tries multiple parsers for best results
- **CLI Interface**: Easy-to-use command-line interface
- **Flexible**: Works without API keys for text PDFs, Claude optional for images

## Installation

This project uses `uv` for dependency management. The virtual environment is automatically managed.

### Prerequisites

- Python 3.11+
- uv (if not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Setup

```bash
# Clone or navigate to the project
cd pdf_parser

# Dependencies are automatically installed when you run commands
# Or manually sync:
uv sync
```

### Optional: Claude Vision for Image-Based PDFs

To enable AI-powered parsing of scanned/image-based PDFs:

1. **Get an Anthropic API key**: Visit [Anthropic Console](https://console.anthropic.com/)
2. **Set environment variable**:
   ```bash
   export ANTHROPIC_API_KEY='your-api-key-here'
   ```

3. **Verify it's enabled**:
   ```bash
   uv run pdf-parser info
   ```

**Note**: Claude Vision is **optional**. The parser works perfectly for text-based PDFs without any API key. Claude is only needed for image-based (scanned) PDFs.

**Cost**: Uses Claude 3.5 Haiku (~$0.25 per million input tokens). A typical scanned page costs < $0.01.

## Usage

### Parse a Single PDF

```bash
# Basic usage - outputs to ./output/
uv run pdf-parser parse data/document.pdf

# Specify output file
uv run pdf-parser parse data/document.pdf -o custom_output.md

# Use specific parser
uv run pdf-parser parse data/document.pdf --parser PDFPlumberParser

# Verbose mode
uv run pdf-parser parse data/document.pdf -v
```

### Batch Process Directory

```bash
# Parse all PDFs in ./data/
uv run pdf-parser batch data/

# Specify output directory
uv run pdf-parser batch data/ -o markdown_output/

# Stop on first error
uv run pdf-parser batch data/ --no-continue-on-error
```

### Inspect PDF

```bash
# View PDF metadata without parsing
uv run pdf-parser inspect data/document.pdf
```

### Parser Information

```bash
# List available parsers
uv run pdf-parser info
```

## Architecture

```
pdf_parser/
├── pdf_parser/
│   ├── models/          # Data models (ParsedDocument, DocumentElement)
│   ├── parsers/         # Parser implementations
│   │   ├── base.py                   # Abstract parser interface
│   │   ├── pdfplumber_parser.py     # Primary: table extraction
│   │   ├── pymupdf_parser.py        # Fallback: fast text extraction
│   │   └── claude_vision_parser.py  # AI: image-based PDFs
│   ├── services/        # Business logic
│   │   ├── parser_service.py        # Smart routing & orchestration
│   │   └── export_service.py        # Markdown export
│   ├── utils/           # Utilities
│   │   ├── file_handler.py          # File I/O
│   │   ├── markdown_builder.py      # Markdown formatting
│   │   └── pdf_detector.py          # PDF type detection
│   ├── core/            # Configuration
│   └── main.py          # CLI entry point
├── data/                # Input PDFs
├── output/              # Generated markdown files
└── tests/               # Test suite
```

## Parsing Strategy

The system uses **smart routing** with automatic PDF type detection:

### For Text-Based PDFs (Default)

1. **PDFPlumber** (Primary)
   - Excellent for table-heavy documents
   - Precise text positioning
   - Structured content extraction

2. **PyMuPDF** (Fallback)
   - Fast text extraction
   - Good for text-heavy documents
   - Lightweight processing

### For Image-Based PDFs (Scanned Documents)

3. **Claude Vision** (AI-Powered)
   - Uses Claude 3.5 Haiku vision model
   - Extracts text from scanned pages
   - Preserves tables, headings, and structure
   - Requires ANTHROPIC_API_KEY

**How it works**: The parser automatically detects if a PDF is image-based (< 50 chars/page) and routes it to the appropriate parser. No manual selection needed!

## Output Format

Generated markdown includes:

- Document metadata (title, author, dates)
- Page separators
- Headings (auto-detected from structure)
- Tables (formatted as markdown tables)
- Paragraphs with proper spacing
- Preserved document structure

Example output:

```markdown
# Terms of Business Agreement

## Document Metadata
- **Date**: 29th January 2025
- **Pages**: 2

**Page 1**

## COMPANY FEE. COMPANY PAYMENT OPTIONS

| No | Online services | Company Fee, % |
|---|---|---|
| 1 | Internet acquiring, EUR | 3.8 % |
| 1 | Apple Pay and Google Pay | 5.0 % |

---

**Page 2**

...
```

## Development

### Run Tests

```bash
uv run pytest
```

### Code Formatting

```bash
uv run black pdf_parser/
uv run ruff check pdf_parser/
```

### Add Dependencies

```bash
uv add package-name
```

## Libraries Used

- **pdfplumber**: Table extraction and precise text positioning
- **PyMuPDF (fitz)**: Fast text extraction, metadata, and image rendering
- **anthropic**: Claude AI integration for image-based PDFs
- **click**: CLI interface
- **pillow**: Image processing support

## Troubleshooting

### Image-based PDF not parsing

If you see "0 elements extracted" for a scanned PDF:

1. **Check if API key is set**:
   ```bash
   uv run pdf-parser inspect your-file.pdf
   ```

2. **Enable Claude Vision**:
   ```bash
   export ANTHROPIC_API_KEY='your-key'
   uv run pdf-parser parse your-file.pdf
   ```

3. **Verify it's working**:
   ```bash
   uv run pdf-parser info  # Should show "Claude Vision: Enabled"
   ```

### No output generated

- Check that PDF is not encrypted
- Verify file is a valid PDF
- Try verbose mode: `-v`
- For scanned PDFs, ensure ANTHROPIC_API_KEY is set

### Tables not detected

- PDFPlumber is designed for table extraction but may miss complex layouts
- Claude Vision can handle scanned tables
- Check output for text content - it may have been extracted as paragraphs

### Parser errors

- System automatically tries fallback parsers
- Check logs for specific error messages
- Some PDFs may be corrupted or have unusual encodings

### Claude API errors

- **Rate limits**: Claude Haiku has generous limits, but consider adding delays for large batches
- **Network errors**: Check internet connection
- **Invalid API key**: Verify key at https://console.anthropic.com/
- **Cost concerns**: Each page costs ~$0.001-0.01 depending on content

## License

[Your License]

## Contributing

[Contributing guidelines]
