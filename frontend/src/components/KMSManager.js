import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const KMSManager = ({ api }) => {
  const [status, setStatus] = useState(null);
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusRes, providersRes] = await Promise.all([
        api.get('/kms/status'),
        api.get('/kms/providers'),
      ]);
      setStatus(statusRes.data);
      setProviders(providersRes.data.providers || providersRes.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load KMS data.');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnectivity = async () => {
    setTesting(true);
    setError('');
    setSuccess('');
    setTestResult(null);
    try {
      const response = await api.post('/kms/test');
      setTestResult(response.data);
      setSuccess(response.data.message || 'Connectivity test passed.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Connectivity test failed.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white"><JargonTerm term="KMS">KMS</JargonTerm> Manager</h2>
        <button
          onClick={handleTestConnectivity}
          disabled={testing}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
        >
          {testing ? 'Testing...' : 'Test Connectivity'}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-center justify-between">
          <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs">Dismiss</button>
        </div>
      )}

      {success && (
        <div className="mb-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 flex items-center justify-between">
          <p className="text-sm text-green-700 dark:text-green-400">{success}</p>
          <button onClick={() => setSuccess('')} className="text-green-500 text-xs">Dismiss</button>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : (
        <div>
          {/* Active Provider Status */}
          {status && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Active Provider</h3>
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <span className="text-gray-500 dark:text-gray-400">Provider:</span>
                  <span className="text-gray-900 dark:text-gray-100 font-medium">{status.provider || status.active_provider || 'None'}</span>
                  <span className="text-gray-500 dark:text-gray-400">Status:</span>
                  <span className={`font-medium ${status.connected || status.status === 'active' ? 'text-green-600' : 'text-red-600'}`}>
                    {status.connected || status.status === 'active' ? 'Connected' : 'Disconnected'}
                  </span>
                  {status.region && (
                    <>
                      <span className="text-gray-500 dark:text-gray-400">Region:</span>
                      <span className="text-gray-900 dark:text-gray-100">{status.region}</span>
                    </>
                  )}
                  {status.key_count !== undefined && (
                    <>
                      <span className="text-gray-500 dark:text-gray-400">Managed Keys:</span>
                      <span className="text-gray-900 dark:text-gray-100">{status.key_count}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Test Result */}
          {testResult && (
            <div className="mb-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-blue-700 dark:text-blue-300 mb-2">Test Result</h3>
              <p className="text-sm text-blue-600 dark:text-blue-400">
                Latency: {testResult.latency_ms ?? testResult.latency ?? 'N/A'}ms |
                Status: {testResult.success || testResult.status === 'ok' ? 'Passed' : 'Failed'}
              </p>
            </div>
          )}

          {/* Available Providers */}
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Available Providers</h3>
          {providers.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>No providers configured.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {providers.map((provider, idx) => (
                <div key={provider.id || idx} className="border dark:border-gray-600 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">{provider.name || provider.type}</h4>
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      provider.configured || provider.available
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-gray-100 text-gray-600 dark:bg-gray-600 dark:text-gray-300'
                    }`}>
                      {provider.configured || provider.available ? 'Available' : 'Not Configured'}
                    </span>
                  </div>
                  {provider.description && (
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">{provider.description}</p>
                  )}
                  {provider.requirements && (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Requirements:</p>
                      <ul className="list-disc list-inside text-xs text-gray-500 dark:text-gray-400">
                        {(Array.isArray(provider.requirements) ? provider.requirements : [provider.requirements]).map((req, i) => (
                          <li key={i}>{req}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default KMSManager;
