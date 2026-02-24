# UI Renderer Backend

AI-powered backend service for dynamically generating UI specifications from financial contract JSON data.

> **Current Model**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
> **Last Updated**: 2026-01-27
> **Status**: ✅ Production Ready

## Recent Updates

**2026-01-27**: Critical bug fixes for data binding
- ✅ Fixed Table component to use `data` prop (not `rows`)
- ✅ Fixed KeyValueList component binding pattern
- ✅ Enhanced AI prompts with explicit prop name requirements
- See [SESSION_LOG.md](../SESSION_LOG.md) for details

## Features

- FastAPI-based REST API
- Claude Haiku integration for intelligent UI generation
- Extensible component specification schema
- Contract data management
- CORS-enabled for frontend integration

## Architecture

```
backend/
├── app/
│   ├── api/              # API endpoints
│   ├── core/             # Configuration and settings
│   ├── schemas/          # Pydantic models
│   └── services/         # Business logic
│       ├── ai_service.py      # AI-powered UI generation
│       └── contract_service.py # Contract data management
├── tests/                # Test suite
└── pyproject.toml        # Project dependencies
```

## Setup

### Prerequisites

- Python 3.11+
- uv package manager
- Anthropic API key

### Installation

1. Create `.env` file from example:
```bash
cp .env.example .env
```

2. Add your Anthropic API key to `.env`:
```
ANTHROPIC_API_KEY=your_key_here
```

3. Install dependencies with uv:
```bash
uv pip install -e .
```

For development dependencies:
```bash
uv pip install -e ".[dev]"
```

### Running the Server

```bash
# Development mode with auto-reload
python -m app.main

# Or using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /health` - Service health check

### Contracts
- `GET /api/v1/contracts` - List all available contracts
- `GET /api/v1/contracts/{filename}` - Get contract with metadata
- `GET /api/v1/contracts/{filename}/data` - Get raw contract JSON

### UI Generation
- `POST /api/v1/generate-ui?filename={filename}` - Generate UI specification

## Component Types

The system supports the following UI components:

### Layout Components
- `Container` - Generic container
- `Grid` - Grid layout
- `Card` - Card container
- `Section` - Named section
- `Tabs` - Tabbed interface
- `Accordion` - Expandable sections

### Data Display
- `Table` - Data table
- `KeyValueList` - Key-value pairs
- `BadgeList` - Tag/badge list
- `MetricCard` - Single metric display
- `FeeCard` - Fee information card
- `TieredPricing` - Tiered pricing display

### Text Components
- `Heading` - Headings (h1-h6)
- `Text` - Plain text
- `Label` - Label text

## Component Specification Schema

```json
{
  "contract_id": "contract.json",
  "title": "Contract Name",
  "description": "Brief description",
  "components": [
    {
      "id": "unique-id",
      "type": "Card",
      "props": {
        "title": "Section Title"
      },
      "data_bindings": {
        "value": {
          "path": "fees_and_rates[0].amount",
          "transform": "formatCurrency"
        }
      },
      "style": {
        "variant": "outlined",
        "size": "medium"
      },
      "children": []
    }
  ]
}
```

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black app/
```

### Linting
```bash
ruff check app/
```

## Environment Variables

See `.env.example` for all available configuration options.

## License

MIT
