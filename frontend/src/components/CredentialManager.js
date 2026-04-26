import { useState, useEffect } from "react";
import CredentialWalkthrough from "./CredentialWalkthrough";
import GitHubConnect from "./GitHubConnect";

const CredentialManager = ({ api }) => {
  const [credentials, setCredentials] = useState([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCredential, setNewCredential] = useState({ api_name: '', api_key: '', environment: 'development' });
  const [apiOptions, setApiOptions] = useState([]);
  const [walkthroughProviders, setWalkthroughProviders] = useState([]);
  const [error, setError] = useState('');
  const [testingId, setTestingId] = useState(null);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    fetchCredentials();
    fetchApiCatalog();
    fetchWalkthroughProviders();
  }, []);

  const fetchApiCatalog = async () => {
    try {
      const response = await api.get('/api-catalog');
      const apis = response.data?.apis || response.data || [];
      setApiOptions(apis.map(a => ({ value: a.id, label: a.name })));
    } catch (err) {
      // Fallback to defaults if catalog endpoint is unavailable
      setApiOptions([
        { value: 'openai', label: 'OpenAI' },
        { value: 'stripe', label: 'Stripe' },
        { value: 'github', label: 'GitHub' },
        { value: 'supabase', label: 'Supabase' },
        { value: 'firebase', label: 'Firebase' },
        { value: 'vercel', label: 'Vercel' }
      ]);
    }
  };

  const fetchWalkthroughProviders = async () => {
    try {
      const response = await api.get('/walkthroughs');
      const providers = Array.isArray(response.data) ? response.data : [];
      setWalkthroughProviders(providers.map(p => p.provider));
    } catch (err) {
      // No walkthroughs available; the bare paste form remains the fallback.
      setWalkthroughProviders([]);
    }
  };

  const hasWalkthrough = (provider) =>
    Boolean(provider) && walkthroughProviders.includes(provider);

  const fetchCredentials = async () => {
    setError('');
    try {
      const response = await api.get('/credentials');
      setCredentials(response.data);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to load credentials.';
      setError(message);
    }
  };

  const handleAddCredential = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await api.post('/credentials', newCredential);
      setNewCredential({ api_name: '', api_key: '', environment: 'development' });
      setShowAddForm(false);
      fetchCredentials();
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to add credential.';
      setError(message);
    }
  };

  const testCredential = async (credentialId) => {
    setTestingId(credentialId);
    setTestResult(null);
    setError('');
    try {
      const response = await api.post(`/credentials/${credentialId}/test`);
      const result = response.data.test_result || response.data;
      const isActive = result.status === 'active' || result.status === 'format_valid';
      setTestResult({ id: credentialId, success: isActive, message: result.message || `Status: ${result.status}` });
      fetchCredentials();
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Test failed.';
      setTestResult({ id: credentialId, success: false, message });
    } finally {
      setTestingId(null);
    }
  };

  const deleteCredential = async (credentialId) => {
    if (!window.confirm('Are you sure you want to delete this credential?')) return;

    setError('');
    try {
      await api.delete(`/credentials/${credentialId}`);
      fetchCredentials();
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to delete credential.';
      setError(message);
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      active: 'bg-green-100 text-green-800',
      invalid: 'bg-red-100 text-red-800',
      expired: 'bg-yellow-100 text-yellow-800',
      rate_limited: 'bg-orange-100 text-orange-800',
      unknown: 'bg-gray-100 text-gray-800'
    };
    return colors[status] || colors.unknown;
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Credential Management</h2>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700"
        >
          Add Credential
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-red-600 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-red-700">{error}</p>
          </div>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-3">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {showAddForm && (
        <div className="mb-6 p-4 border border-gray-200 rounded-lg">
          <div className="space-y-4">
            <div>
              <label htmlFor="api-name-select" className="block text-sm font-medium text-gray-700 mb-1">API Name</label>
              <select
                id="api-name-select"
                value={newCredential.api_name}
                onChange={(e) => setNewCredential({...newCredential, api_name: e.target.value})}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select API</option>
                {apiOptions.map((opt) => (
                  <option key={opt.value || opt.name} value={opt.value || opt.name}>
                    {opt.label || opt.display_name || opt.name}
                  </option>
                ))}
              </select>
              {hasWalkthrough(newCredential.api_name) && (
                <p className="mt-1 text-xs text-indigo-700">
                  KeyForge has a guided walkthrough for this provider.
                </p>
              )}
            </div>

            {newCredential.api_name === 'github' ? (
              <GitHubConnect
                api={api}
                onCredentialMinted={() => {
                  setNewCredential({ api_name: '', api_key: '', environment: 'development' });
                  setShowAddForm(false);
                  fetchCredentials();
                }}
              />
            ) : hasWalkthrough(newCredential.api_name) ? (
              <CredentialWalkthrough
                api={api}
                provider={newCredential.api_name}
                onComplete={() => {
                  setNewCredential({ api_name: '', api_key: '', environment: 'development' });
                  setShowAddForm(false);
                  fetchCredentials();
                }}
                onCancel={() => setShowAddForm(false)}
              />
            ) : (
              <form onSubmit={handleAddCredential} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                  <p className="text-xs text-gray-500 mb-2">
                    An API key (sometimes called a token or PAT) is a long string the provider issued you when you signed up.
                    Paste it below; KeyForge stores it encrypted and never shows it in your browser again.
                  </p>
                  <input
                    type="password"
                    value={newCredential.api_key}
                    onChange={(e) => setNewCredential({...newCredential, api_key: e.target.value})}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Enter API key"
                  />
                </div>
                <div>
                  <label htmlFor="environment-select" className="block text-sm font-medium text-gray-700 mb-1">Environment</label>
                  <select
                    id="environment-select"
                    value={newCredential.environment}
                    onChange={(e) => setNewCredential({...newCredential, environment: e.target.value})}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="development">Development</option>
                    <option value="staging">Staging</option>
                    <option value="production">Production</option>
                  </select>
                </div>
                <div className="flex space-x-2">
                  <button
                    type="submit"
                    className="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700"
                  >
                    Add Credential
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    className="bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      <div className="space-y-4">
        {credentials.map((cred) => (
          <div key={cred.id} className="border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center space-x-2 mb-2">
                  <h3 className="font-semibold text-gray-900 capitalize">{cred.api_name}</h3>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusBadge(cred.status)}`}>
                    {cred.status}
                  </span>
                  <span className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">
                    {cred.environment}
                  </span>
                </div>
                {cred.api_key_preview && (
                  <p className="text-sm text-gray-500 font-mono mb-1">{cred.api_key_preview}</p>
                )}
                <p className="text-sm text-gray-600">
                  Last tested: {cred.last_tested ? new Date(cred.last_tested).toLocaleDateString() : 'Never'}
                </p>
                {testResult && testResult.id === cred.id && (
                  <div className={`mt-2 text-sm px-3 py-1.5 rounded-md ${testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    {testResult.message}
                  </div>
                )}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => testCredential(cred.id)}
                  disabled={testingId === cred.id}
                  className="text-indigo-600 hover:text-indigo-900 text-sm font-medium disabled:opacity-50"
                >
                  {testingId === cred.id ? (
                    <span className="flex items-center">
                      <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-indigo-600 mr-1"></div>
                      Testing...
                    </span>
                  ) : (
                    'Test'
                  )}
                </button>
                <button
                  onClick={() => deleteCredential(cred.id)}
                  className="text-red-600 hover:text-red-900 text-sm font-medium"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}

        {credentials.length === 0 && !error && (
          <div className="text-center py-8">
            <p className="text-gray-500">No credentials added yet. Click "Add Credential" to get started.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default CredentialManager;
