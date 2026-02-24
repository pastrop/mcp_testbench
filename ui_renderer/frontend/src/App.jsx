import React, { useState, useEffect } from 'react';
import { Renderer } from './lib/Renderer';
import apiClient from './lib/api';
import './App.css';

function App() {
  const [contracts, setContracts] = useState([]);
  const [selectedContract, setSelectedContract] = useState(null);
  const [contractData, setContractData] = useState(null);
  const [uiSpec, setUiSpec] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load available contracts on mount
  useEffect(() => {
    loadContracts();
  }, []);

  const loadContracts = async () => {
    try {
      setError(null);
      const data = await apiClient.listContracts();
      setContracts(data.contracts || []);
    } catch (err) {
      setError(`Failed to load contracts: ${err.message}`);
      console.error(err);
    }
  };

  const handleSelectContract = async (filename) => {
    if (!filename) return;

    setSelectedContract(filename);
    setLoading(true);
    setError(null);

    try {
      console.log('Loading contract:', filename);

      // Load contract data
      const data = await apiClient.getContractData(filename);
      console.log('Contract data loaded:', Object.keys(data));
      setContractData(data);

      // Generate UI specification
      console.log('Generating UI spec...');
      const spec = await apiClient.generateUI(filename);
      console.log('UI spec received:', spec);
      console.log('Components count:', spec.components?.length);
      setUiSpec(spec);

      console.log('Rendering UI...');
    } catch (err) {
      setError(`Failed to process contract: ${err.message}`);
      console.error('Error details:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-content">
          <h1 className="app__title">Contract UI Renderer</h1>
          <p className="app__subtitle">
            AI-powered dynamic UI generation for financial contracts
          </p>
        </div>
      </header>

      <div className="app__toolbar">
        <div className="app__toolbar-content">
          <label htmlFor="contract-select" className="app__label">
            Select Contract:
          </label>
          <select
            id="contract-select"
            className="app__select"
            value={selectedContract || ''}
            onChange={(e) => handleSelectContract(e.target.value)}
            disabled={loading}
          >
            <option value="">-- Choose a contract --</option>
            {contracts.map((contract) => (
              <option key={contract} value={contract}>
                {contract}
              </option>
            ))}
          </select>
          {loading && <div className="app__spinner">Generating UI...</div>}
        </div>
      </div>

      <main className="app__main">
        {error && (
          <div className="app__error">
            <strong>Error:</strong> {error}
          </div>
        )}

        {!selectedContract && !error && (
          <div className="app__empty">
            <p>Select a contract from the dropdown above to view its details</p>
          </div>
        )}

        {/* Debug info */}
        {selectedContract && (
          <div style={{ padding: '1rem', background: '#f0f0f0', marginBottom: '1rem', fontSize: '0.875rem' }}>
            <strong>Debug:</strong> Selected: {selectedContract} |
            Loading: {loading ? 'Yes' : 'No'} |
            Has Spec: {uiSpec ? 'Yes' : 'No'} |
            Has Data: {contractData ? 'Yes' : 'No'} |
            Components: {uiSpec?.components?.length || 0}
          </div>
        )}

        {uiSpec && contractData && !loading && (
          <div className="app__content">
            <Renderer spec={uiSpec} contractData={contractData} />
          </div>
        )}

        {loading && selectedContract && (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <h3>Loading...</h3>
          </div>
        )}
      </main>

      <footer className="app__footer">
        <p>
          Powered by Claude Haiku • {contracts.length} contracts available
        </p>
      </footer>
    </div>
  );
}

export default App;
