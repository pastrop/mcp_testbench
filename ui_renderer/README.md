# UI Renderer - Dynamic UI Generation for Financial Contracts

An AI-powered system for automatically generating user interfaces from financial contract JSON data. Uses Claude Haiku to intelligently analyze contract structures and generate optimal UI component specifications.

## System Overview

```
┌─────────────────────┐
│  Contract JSON Data │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  FastAPI Backend    │
│  - Contract Service │
│  - AI Service       │
│    (Claude Haiku)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  UI Specification   │
│  (JSON Schema)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  React Frontend     │
│  - Renderer         │
│  - Component Lib    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Rendered UI        │
└─────────────────────┘
```

## Features

### Backend
- **FastAPI** REST API with full CORS support
- **Claude Haiku** integration for intelligent UI generation
- **Contract Management** - Load and serve contract data
- **Extensible Schema** - Easy to add new component types
- **Type Safety** - Pydantic models for validation

### Frontend
- **React 18** with modern hooks
- **Extensible Component Library** - 15+ components out of the box
- **Dynamic Rendering** - Renders any valid UI spec
- **Data Binding** - JSON path-based data resolution
- **Transformers** - Built-in data formatting (currency, percentages, dates)
- **Responsive Design** - Mobile-friendly layouts

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- uv (Python package manager)
- Anthropic API key

### 1. Clone and Setup

```bash
cd ui_renderer
```

### 2. Backend Setup

```bash
cd backend

# Create .env file
cp .env.example .env

# Edit .env and add your Anthropic API key
# ANTHROPIC_API_KEY=your_key_here

# Install dependencies (already done if you ran uv commands)
source .venv/bin/activate

# Run the server
python -m app.main
```

Backend will start at `http://localhost:8000`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run the dev server
npm run dev
```

Frontend will start at `http://localhost:5173`

### 4. Test the System

1. Open `http://localhost:5173` in your browser
2. Select a contract from the dropdown
3. Watch the AI generate and render the UI automatically

## Project Structure

```
ui_renderer/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/            # API routes
│   │   ├── core/           # Configuration
│   │   ├── schemas/        # Pydantic models
│   │   │   ├── component_spec.py  # UI component schemas
│   │   │   └── contract.py        # Contract data schemas
│   │   └── services/
│   │       ├── ai_service.py      # Claude Haiku integration
│   │       └── contract_service.py # Contract management
│   ├── tests/
│   └── pyproject.toml
│
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/    # Component library
│   │   │   ├── layout/   # Container, Grid, Card, Section, Tabs, Accordion
│   │   │   ├── data/     # Table, FeeCard, MetricCard, etc.
│   │   │   └── text/     # Heading, Text, Label
│   │   ├── lib/
│   │   │   ├── Renderer.jsx  # Core rendering engine
│   │   │   └── api.js        # API client
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
│
└── data/
    └── Parsed_Contracts/  # Financial contract JSON files
```

## Available Components

### Layout Components
- **Container** - Responsive container wrapper
- **Grid** - Multi-column grid layout
- **Card** - Card with optional title/subtitle
- **Section** - Named section with heading
- **Tabs** - Tabbed interface
- **Accordion** - Expandable accordion

### Data Display Components
- **Table** - Data table with auto-generated columns
- **KeyValueList** - Key-value pair display
- **BadgeList** - List of tags/badges
- **MetricCard** - Single metric with label
- **FeeCard** - Specialized fee information display
- **TieredPricing** - Tiered pricing structure

### Text Components
- **Heading** - Headings (h1-h6)
- **Text** - Styled paragraphs
- **Label** - Label text

## API Endpoints

### Contracts
- `GET /api/v1/contracts` - List all contracts
- `GET /api/v1/contracts/{filename}` - Get contract metadata
- `GET /api/v1/contracts/{filename}/data` - Get raw contract data

### UI Generation
- `POST /api/v1/generate-ui?filename={filename}` - Generate UI specification

### Health
- `GET /health` - Health check
- `GET /` - Service info

## Component Specification Schema

The AI generates JSON specifications like:

```json
{
  "contract_id": "example.json",
  "title": "Payment Services Agreement",
  "description": "Fee structure and terms",
  "components": [
    {
      "id": "doc-info",
      "type": "Card",
      "props": {
        "title": "Document Information"
      },
      "data_bindings": {
        "subtitle": {
          "path": "document_info.company",
          "transform": "uppercase"
        }
      },
      "style": {
        "variant": "outlined"
      },
      "children": [
        {
          "id": "doc-details",
          "type": "KeyValueList",
          "data_bindings": {
            "items": {
              "path": "document_info"
            }
          }
        }
      ]
    }
  ]
}
```

## Extending the System

### Adding a New Component

1. **Create the React component** (`frontend/src/components/`)
2. **Export it** from `components/index.js`
3. **Register it** in `Renderer.jsx` COMPONENT_MAP
4. **Add to backend schema** (`backend/app/schemas/component_spec.py`)
5. **Update AI prompt** if needed (`backend/app/services/ai_service.py`)

The system is designed to be fully extensible - new components can be added without modifying core logic.

## Data Binding

The renderer supports powerful data binding:

```json
{
  "data_bindings": {
    "amount": {
      "path": "fees_and_rates[0].amount",
      "transform": "formatCurrency",
      "default_value": "0.00"
    }
  }
}
```

### Supported Transforms
- `formatCurrency` - Format numbers as currency
- `formatPercentage` - Format decimals as percentages
- `formatDate` - Format date strings
- `uppercase`, `lowercase`, `capitalize` - Text transformations

## Configuration

### Backend (.env)
```bash
ANTHROPIC_API_KEY=your_key_here
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
CONTRACTS_DATA_PATH=../data/Parsed_Contracts
```

### Frontend (.env)
```bash
VITE_API_URL=http://localhost:8000/api/v1
```

## Development

### Running Tests

Backend:
```bash
cd backend
pytest
```

Frontend:
```bash
cd frontend
npm run lint
```

### Code Formatting

Backend:
```bash
black app/
ruff check app/
```

## Architecture Decisions

### Why Claude Haiku?
- Fast inference for real-time UI generation
- Excellent at structured JSON output
- Cost-effective for production use
- Strong understanding of financial data structures

### Why Component-Based?
- Extensible - add new components easily
- Reusable - components work across different contracts
- Maintainable - clear separation of concerns
- Type-safe - Pydantic validation

### Why JSON Spec?
- Cacheable - save generated specs
- Versionable - track UI changes
- Portable - use with other renderers
- Debuggable - inspect generated specs

## Troubleshooting

### Backend won't start
- Check that port 8000 is available
- Verify ANTHROPIC_API_KEY is set
- Ensure contracts directory exists at correct path

### Frontend can't connect
- Verify backend is running on port 8000
- Check CORS settings in backend config
- Inspect browser console for errors

### UI not rendering
- Check browser console for component errors
- Verify contract data structure matches bindings
- Inspect generated UI spec in network tab

## Future Enhancements

- [ ] UI spec caching to reduce API calls
- [ ] Component preview mode for development
- [ ] Custom component registration API
- [ ] UI spec versioning and history
- [ ] Export rendered UI to static HTML
- [ ] Theme customization
- [ ] Accessibility improvements
- [ ] Mobile-optimized components

## License

MIT

## Contributing

This system is designed to be extensible. Contributions welcome:
- New components
- Additional data transformers
- UI improvements
- Bug fixes

---

Built with Claude Sonnet 4.5, FastAPI, React, and Claude Haiku
