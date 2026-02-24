# Claude Vision Integration Guide

This document explains how to use Claude Vision for parsing image-based (scanned) PDFs.

## Quick Start

### 1. Get an API Key

Visit [Anthropic Console](https://console.anthropic.com/) and create an API key.

### 2. Set Environment Variable

```bash
export ANTHROPIC_API_KEY='your-api-key-here'

# Or add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
echo 'export ANTHROPIC_API_KEY="your-api-key"' >> ~/.bashrc
```

### 3. Verify It's Working

```bash
uv run pdf-parser info
```

You should see:
```
Claude Vision Status:
  ✓ Enabled (ANTHROPIC_API_KEY found)
  Model: claude-3-5-haiku-20241022
```

### 4. Parse a Scanned PDF

```bash
# The parser automatically detects image-based PDFs
uv run pdf-parser parse data/scanned-document.pdf

# Check PDF type first
uv run pdf-parser inspect data/scanned-document.pdf
```

## How It Works

### Automatic Detection

The parser automatically detects if a PDF is image-based by checking text content:
- **< 50 characters per page** = Image-based → Uses Claude Vision
- **≥ 50 characters per page** = Text-based → Uses PDFPlumber/PyMuPDF

### Processing Flow

For image-based PDFs:

1. **Extract pages as images** (PNG, 150 DPI)
2. **Send to Claude Vision** (page by page)
3. **Parse markdown response** (tables, headings, text)
4. **Combine into document** (all pages)
5. **Export as markdown** (same as text PDFs)

### What Claude Extracts

Claude Vision is prompted to extract:
- ✓ **Headings** - Identified by formatting and marked with `#`
- ✓ **Tables** - Converted to markdown table format
- ✓ **Lists** - Numbered and bulleted lists
- ✓ **Text** - All visible text, preserving structure
- ✓ **Formatting** - Bold, emphasis where visible

## Cost & Performance

### Pricing (Claude 3.5 Haiku)

- **Input**: ~$0.25 per million tokens
- **Typical page**: 1,000-3,000 tokens
- **Cost per page**: $0.001 - $0.003 (less than a penny)
- **100-page document**: ~$0.10 - $0.30

### Performance

- **Speed**: ~2-5 seconds per page
- **Accuracy**: Very high for printed documents
- **Limits**: No hard limits for Haiku tier

### Example Costs

| Document Type | Pages | Est. Cost |
|--------------|-------|-----------|
| Receipt | 1 | $0.001 |
| Contract | 10 | $0.02 |
| Report | 50 | $0.10 |
| Book | 200 | $0.50 |

## Configuration

### Environment Variables

```bash
# Required
export ANTHROPIC_API_KEY='sk-ant-...'

# Optional (defaults shown)
export CLAUDE_MODEL='claude-3-5-haiku-20241022'
export MIN_TEXT_CHARS_PER_PAGE=50
```

### Model Options

You can change the model in `pdf_parser/core/config.py`:

- `claude-3-5-haiku-20241022` (default) - Fast, cheap, excellent for documents
- `claude-3-5-sonnet-20241022` - More expensive, better for complex layouts
- `claude-opus-4` - Most powerful, expensive, use for critical documents

## Example Usage

### Basic Parsing

```bash
# Single image-based PDF
uv run pdf-parser parse data/scanned.pdf

# Batch process directory (mix of text and image PDFs)
uv run pdf-parser batch data/
```

### With Verbose Logging

```bash
uv run pdf-parser parse data/scanned.pdf -v
```

Output shows:
```
INFO: PDF type: image-based (scanned)
INFO: Using Claude Vision to parse image-based PDF
INFO: Extracted 2 pages as images
INFO: Processing page 1/2 with Claude...
INFO: Processing page 2/2 with Claude...
INFO: Successfully parsed with ClaudeVisionParser: 45 elements extracted
```

### Inspecting Before Parsing

```bash
uv run pdf-parser inspect data/document.pdf
```

Shows:
```
PDF Information: document.pdf

  Pages: 5
  Size: 2.3 MB
  Type: Image-based (scanned)
  → Will use Claude Vision for parsing
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

```bash
# Check if set
echo $ANTHROPIC_API_KEY

# Set temporarily
export ANTHROPIC_API_KEY='your-key'

# Set permanently (add to ~/.bashrc)
echo 'export ANTHROPIC_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

### "Rate limit exceeded"

Add delays between pages or use a higher tier API key.

### "Invalid API key"

- Verify key at https://console.anthropic.com/
- Check for extra spaces or quotes
- Ensure key starts with `sk-ant-`

### Poor extraction quality

- Try higher DPI: Edit `pdf_detector.py` and increase `dpi=150` to `dpi=200`
- Use better model: Change to `claude-3-5-sonnet-20241022`
- Check if PDF is heavily degraded or low quality

### Cost concerns

- **Start small**: Test with 1-2 pages first
- **Monitor usage**: Check https://console.anthropic.com/usage
- **Set limits**: Configure billing alerts in Anthropic Console
- **Optimize**: Only use for scanned PDFs (text PDFs are free)

## Comparison: Text vs Image-Based Parsing

| Feature | Text-Based PDFs | Image-Based PDFs |
|---------|----------------|------------------|
| **Method** | Direct text extraction | AI vision processing |
| **Libraries** | pdfplumber, PyMuPDF | Claude Vision API |
| **Cost** | Free | ~$0.001-0.003/page |
| **Speed** | Very fast (<1s) | Fast (2-5s/page) |
| **Accuracy** | Perfect | Very high |
| **API Key** | Not required | Required |
| **Offline** | Yes | No |
| **Tables** | Excellent | Very good |

## Best Practices

1. **Check PDF type first**: Use `inspect` to see if Claude Vision is needed
2. **Batch wisely**: Consider costs for large batches
3. **Test first**: Try 1-2 pages before processing hundreds
4. **Mix and match**: System automatically uses free parsers for text PDFs
5. **Monitor usage**: Check Anthropic Console regularly
6. **Version control**: Don't commit API keys to git

## Security

### Protecting Your API Key

```bash
# Bad - committed to git
echo "ANTHROPIC_API_KEY=sk-ant-123" > .env

# Good - use environment variables
export ANTHROPIC_API_KEY='sk-ant-123'

# Better - use system keychain
# macOS: Store in Keychain Access
# Linux: Use secret-tool or pass
```

### Data Privacy

- PDFs are sent to Anthropic's API
- Review Anthropic's privacy policy
- Don't process sensitive documents without authorization
- Consider on-premise solutions for highly sensitive data

## FAQ

**Q: Do I need Claude for all PDFs?**
A: No, only for scanned/image-based PDFs. Text PDFs work without any API key.

**Q: Can I use other vision models?**
A: Currently only Claude is supported. Open an issue to request others.

**Q: What if my PDF has both text and images?**
A: The detector checks average characters per page. It will route to the appropriate parser.

**Q: Can I force use of Claude Vision?**
A: Yes, use `--parser ClaudeVisionParser`

**Q: Is my data private?**
A: PDFs are sent to Anthropic's API. Review their privacy policy at https://anthropic.com/privacy

**Q: Can I run this offline?**
A: For text PDFs, yes. For image PDFs, no (requires API call).

## Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Anthropic Docs**: https://docs.anthropic.com/
- **API Status**: https://status.anthropic.com/
