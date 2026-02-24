import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * API Client for UI Renderer Backend
 */
export const apiClient = {
  /**
   * List all available contracts
   */
  async listContracts() {
    const response = await api.get('/contracts');
    return response.data;
  },

  /**
   * Get contract data by filename
   */
  async getContract(filename) {
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.get(`/contracts/${encodedFilename}`);
    return response.data;
  },

  /**
   * Get raw contract JSON data
   */
  async getContractData(filename) {
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.get(`/contracts/${encodedFilename}/data`);
    return response.data;
  },

  /**
   * Generate UI specification for a contract using AI
   */
  async generateUI(filename) {
    const response = await api.post('/generate-ui', null, {
      params: { filename },
    });
    return response.data;
  },

  /**
   * Health check
   */
  async healthCheck() {
    const response = await api.get('/health');
    return response.data;
  },
};

export default apiClient;
