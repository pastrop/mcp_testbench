# UI Renderer Frontend

React-based frontend for rendering financial contracts using AI-generated component specifications.

## Features

- Dynamic component rendering based on AI-generated specs
- Extensible component library
- Data binding with JSON path resolution
- Support for conditional rendering
- Data transformation utilities (currency, percentages, dates)

## Component Library

### Layout Components
- **Container** - Responsive container wrapper
- **Grid** - Flexible grid layout
- **Card** - Card container with header/content
- **Section** - Named section with heading
- **Tabs** - Tabbed interface
- **Accordion** - Expandable accordion panels

### Data Display Components
- **Table** - Sortable data table
- **KeyValueList** - Key-value pair display
- **BadgeList** - Tag/badge list
- **MetricCard** - Metric display card
- **FeeCard** - Specialized fee information card
- **TieredPricing** - Tiered pricing structure display

### Text Components
- **Heading** - Headings (h1-h6)
- **Text** - Styled text paragraphs
- **Label** - Small label text

## Setup

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create `.env` file (optional):
```bash
cp .env.example .env
```

### Running the App

```bash
# Development mode
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The app will be available at `http://localhost:5173`

## Architecture

```
frontend/
├── src/
│   ├── components/        # Component library
│   │   ├── layout/       # Layout components
│   │   ├── data/         # Data display components
│   │   └── text/         # Text components
│   ├── lib/
│   │   ├── Renderer.jsx  # Main renderer logic
│   │   └── api.js        # API client
│   ├── styles/           # Global styles
│   ├── App.jsx           # Main application
│   └── main.jsx          # Entry point
└── public/               # Static assets
```

## Adding New Components

To extend the component library:

1. Create component in appropriate directory:
```jsx
// src/components/data/MyComponent.jsx
import React from 'react';
import './MyComponent.css';

export const MyComponent = ({ children, ...props }) => {
  return <div className="my-component">{children}</div>;
};
```

2. Create styles:
```css
/* src/components/data/MyComponent.css */
.my-component {
  /* styles */
}
```

3. Export from `src/components/index.js`:
```js
export { MyComponent } from './data/MyComponent';
```

4. Register in Renderer:
```js
// src/lib/Renderer.jsx
import * as Components from '../components';

const COMPONENT_MAP = {
  // ... existing components
  MyComponent: Components.MyComponent,
};
```

5. Update backend component schema:
```python
# backend/app/schemas/component_spec.py
class ComponentType(str, Enum):
    # ... existing types
    MY_COMPONENT = "MyComponent"
```

## Data Binding

The renderer supports JSON path-based data binding:

```json
{
  "data_bindings": {
    "value": {
      "path": "fees_and_rates[0].amount",
      "transform": "formatCurrency",
      "default_value": "N/A"
    }
  }
}
```

### Available Transforms
- `formatCurrency` - Format as currency
- `formatPercentage` - Format as percentage
- `formatDate` - Format as date
- `uppercase` - Convert to uppercase
- `lowercase` - Convert to lowercase
- `capitalize` - Capitalize first letter

## API Integration

The frontend communicates with the backend via REST API:

- `GET /api/v1/contracts` - List contracts
- `GET /api/v1/contracts/{filename}` - Get contract
- `GET /api/v1/contracts/{filename}/data` - Get raw data
- `POST /api/v1/generate-ui?filename={filename}` - Generate UI

## Development

### Code Style
- Use functional components with hooks
- Follow React best practices
- Use CSS modules or scoped CSS
- Keep components small and focused

### Testing Locally
1. Start the backend server (see backend/README.md)
2. Start the frontend dev server: `npm run dev`
3. Open http://localhost:5173
4. Select a contract from the dropdown

## License

MIT
