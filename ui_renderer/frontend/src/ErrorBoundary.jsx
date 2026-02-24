import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      error: error,
      errorInfo: errorInfo
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '2rem',
          margin: '2rem',
          background: '#fee',
          border: '2px solid #c00',
          borderRadius: '8px'
        }}>
          <h1 style={{ color: '#c00' }}>Something went wrong</h1>
          <details style={{ whiteSpace: 'pre-wrap', marginTop: '1rem' }}>
            <summary style={{ cursor: 'pointer', fontWeight: 'bold', marginBottom: '1rem' }}>
              Click to see error details
            </summary>
            <h3>Error:</h3>
            <pre style={{ background: '#fff', padding: '1rem', overflow: 'auto' }}>
              {this.state.error && this.state.error.toString()}
            </pre>
            <h3>Stack Trace:</h3>
            <pre style={{ background: '#fff', padding: '1rem', overflow: 'auto' }}>
              {this.state.errorInfo && this.state.errorInfo.componentStack}
            </pre>
          </details>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: '1rem',
              padding: '0.5rem 1rem',
              background: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
