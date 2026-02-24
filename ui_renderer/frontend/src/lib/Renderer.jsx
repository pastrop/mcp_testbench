import React from 'react';
import * as Components from '../components';

/**
 * Component Registry
 * Maps component type strings to actual React components
 */
const COMPONENT_MAP = {
  // Layout
  Container: Components.Container,
  Grid: Components.Grid,
  Card: Components.Card,
  Section: Components.Section,
  Tabs: Components.Tabs,
  Accordion: Components.Accordion,

  // Data Display
  Table: Components.Table,
  KeyValueList: Components.KeyValueList,
  BadgeList: Components.BadgeList,
  MetricCard: Components.MetricCard,
  FeeCard: Components.FeeCard,
  TieredPricing: Components.TieredPricing,

  // Text
  Heading: Components.Heading,
  Text: Components.Text,
  Label: Components.Label,
};

/**
 * Resolve data from JSON using a path like "fees_and_rates[0].amount"
 */
const resolveDataPath = (data, path) => {
  if (!path) return undefined;

  const keys = path.split(/\.|\[|\]/).filter(Boolean);
  let result = data;

  for (const key of keys) {
    if (result === undefined || result === null) return undefined;
    result = result[key];
  }

  return result;
};

/**
 * Transform data using predefined transformers
 */
const transformData = (value, transformName) => {
  if (!transformName) return value;

  const transformers = {
    formatCurrency: (val) => {
      if (typeof val === 'number') {
        return val.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
      }
      return val;
    },
    formatPercentage: (val) => {
      if (typeof val === 'number') {
        return `${(val * 100).toFixed(2)}%`;
      }
      return val;
    },
    formatDate: (val) => {
      if (!val) return val;
      try {
        return new Date(val).toLocaleDateString();
      } catch {
        return val;
      }
    },
    uppercase: (val) => String(val).toUpperCase(),
    lowercase: (val) => String(val).toLowerCase(),
    capitalize: (val) => {
      const str = String(val);
      return str.charAt(0).toUpperCase() + str.slice(1);
    },
  };

  const transformer = transformers[transformName];
  return transformer ? transformer(value) : value;
};

/**
 * Apply data bindings to props
 */
const applyDataBindings = (props, dataBindings, contractData) => {
  if (!dataBindings) return props;

  const boundProps = { ...props };

  Object.entries(dataBindings).forEach(([propName, binding]) => {
    const rawValue = resolveDataPath(contractData, binding.path);
    const transformedValue = transformData(rawValue, binding.transform);
    const finalValue = transformedValue !== undefined ? transformedValue : binding.default_value;

    // Debug logging
    console.log(`Binding ${propName}:`, {
      path: binding.path,
      rawValue: rawValue,
      finalValue: finalValue,
      hasData: !!contractData
    });

    boundProps[propName] = finalValue;
  });

  return boundProps;
};

/**
 * Check if component should be rendered based on condition
 */
const shouldRender = (condition, contractData) => {
  if (!condition) return true;

  const value = resolveDataPath(contractData, condition);
  return Boolean(value);
};

/**
 * Render a single component from spec
 */
const renderComponent = (spec, contractData, index = 0) => {
  if (!spec || !spec.type) {
    console.warn('Invalid spec - missing type', spec);
    return null;
  }

  try {
    // Check conditional rendering
    if (!shouldRender(spec.condition, contractData)) {
      return null;
    }

    const Component = COMPONENT_MAP[spec.type];
    if (!Component) {
      console.warn(`Unknown component type: ${spec.type}`);
      return (
        <div style={{ padding: '1rem', border: '1px dashed red' }}>
          Unknown component: {spec.type}
        </div>
      );
    }

    // Build props
    let props = { ...spec.props };

    // Apply data bindings
    if (spec.data_bindings) {
      props = applyDataBindings(props, spec.data_bindings, contractData);
    }

    // Apply style config
    if (spec.style) {
      const { variant, size, color, className } = spec.style;
      if (variant) props.variant = variant;
      if (size) props.size = size;
      if (color) props.color = color;
      if (className) props.className = (props.className || '') + ' ' + className;
    }

    // Add key
    props.key = spec.id || `component-${index}`;

    // Render children if present
    const children = spec.children
      ? spec.children.map((childSpec, idx) =>
          renderComponent(childSpec, contractData, idx)
        )
      : null;

    return <Component {...props}>{children}</Component>;
  } catch (error) {
    console.error(`Error rendering component ${spec.type}:`, error);
    return (
      <div style={{ padding: '1rem', background: '#fee', border: '1px solid red' }}>
        <strong>Error rendering {spec.type}</strong>: {error.message}
      </div>
    );
  }
};

/**
 * Main Renderer Component
 * Takes a UI specification and contract data, renders the complete UI
 */
export const Renderer = ({ spec, contractData }) => {
  console.log('Renderer called with:', {
    hasSpec: !!spec,
    hasComponents: !!spec?.components,
    componentCount: spec?.components?.length,
    hasData: !!contractData
  });

  if (!spec || !spec.components) {
    console.warn('No spec or components available');
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
        No UI specification available
      </div>
    );
  }

  try {
    return (
      <div className="renderer">
        {spec.components.map((componentSpec, index) => {
          console.log(`Rendering component ${index}:`, componentSpec.type);
          return renderComponent(componentSpec, contractData, index);
        })}
      </div>
    );
  } catch (error) {
    console.error('Renderer error:', error);
    return (
      <div style={{ padding: '2rem', color: 'red' }}>
        <h3>Rendering Error</h3>
        <p>{error.message}</p>
        <pre>{error.stack}</pre>
      </div>
    );
  }
};

/**
 * Export utility functions for external use
 */
export { resolveDataPath, transformData, applyDataBindings };
