import { useState } from "react";

const ImportExport = ({ api }) => {
  const [activeTab, setActiveTab] = useState('import');
  const [importType, setImportType] = useState('env');
  const [envContent, setEnvContent] = useState('');
  const [jsonContent, setJsonContent] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleImportEnv = async () => {
    if (!envContent.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const response = await api.post('/import/env', envContent, {
        headers: { 'Content-Type': 'text/plain' },
      });
      setResult(response.data);
      setEnvContent('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Import failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleImportJson = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const parsed = JSON.parse(jsonContent);
      const response = await api.post('/import/json', parsed);
      setResult(response.data);
      setJsonContent('');
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError('Invalid JSON format.');
      } else {
        setError(err.response?.data?.detail || 'Import failed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format) => {
    setLoading(true);
    setError('');
    try {
      const includeKeys = window.confirm('Include decrypted API keys in the export? This is sensitive data.');
      const url = format === 'env' ? '/export/env' : `/export/json?include_keys=${includeKeys}`;
      const response = await api.get(url);

      const content = typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2);
      const blob = new Blob([content], { type: format === 'env' ? 'text/plain' : 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = format === 'env' ? 'credentials.env' : 'credentials.json';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      setError(err.response?.data?.detail || 'Export failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Import / Export</h2>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs mt-1">Dismiss</button>
        </div>
      )}

      {result && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-sm text-green-700 font-medium">{result.message}</p>
          {result.imported?.length > 0 && (
            <ul className="mt-2 text-xs text-green-600">
              {result.imported.map((item, i) => (
                <li key={i}>{item.api_name} ({item.env_key || item.environment || 'imported'})</li>
              ))}
            </ul>
          )}
          {result.skipped?.length > 0 && (
            <p className="text-xs text-yellow-600 mt-1">Skipped: {result.skipped.length} entries</p>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 mb-6 border-b">
        <button
          onClick={() => setActiveTab('import')}
          className={`pb-2 text-sm font-medium border-b-2 ${activeTab === 'import' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500'}`}
        >
          Import
        </button>
        <button
          onClick={() => setActiveTab('export')}
          className={`pb-2 text-sm font-medium border-b-2 ${activeTab === 'export' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500'}`}
        >
          Export
        </button>
      </div>

      {activeTab === 'import' && (
        <div>
          <div className="flex space-x-4 mb-4">
            <button
              onClick={() => setImportType('env')}
              className={`px-3 py-1.5 text-sm rounded ${importType === 'env' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'}`}
            >
              .env Format
            </button>
            <button
              onClick={() => setImportType('json')}
              className={`px-3 py-1.5 text-sm rounded ${importType === 'json' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'}`}
            >
              JSON Format
            </button>
          </div>

          {importType === 'env' ? (
            <div>
              <textarea
                value={envContent}
                onChange={(e) => setEnvContent(e.target.value)}
                placeholder={"OPENAI_API_KEY=sk-...\nSTRIPE_SECRET_KEY=sk_test_...\nGITHUB_TOKEN=ghp_..."}
                className="w-full h-48 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              />
              <button
                onClick={handleImportEnv}
                disabled={loading || !envContent.trim()}
                className="mt-3 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm disabled:opacity-50"
              >
                {loading ? 'Importing...' : 'Import from .env'}
              </button>
            </div>
          ) : (
            <div>
              <textarea
                value={jsonContent}
                onChange={(e) => setJsonContent(e.target.value)}
                placeholder={'[\n  {"api_name": "openai", "api_key": "sk-...", "environment": "development"}\n]'}
                className="w-full h-48 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              />
              <button
                onClick={handleImportJson}
                disabled={loading || !jsonContent.trim()}
                className="mt-3 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm disabled:opacity-50"
              >
                {loading ? 'Importing...' : 'Import from JSON'}
              </button>
            </div>
          )}
        </div>
      )}

      {activeTab === 'export' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-2">.env Format</h3>
            <p className="text-sm text-gray-500 mb-4">Download credentials as a .env file for use in your projects.</p>
            <button
              onClick={() => handleExport('env')}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm disabled:opacity-50"
            >
              Export .env
            </button>
          </div>
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-2">JSON Format</h3>
            <p className="text-sm text-gray-500 mb-4">Download credentials as JSON for backup or migration.</p>
            <button
              onClick={() => handleExport('json')}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm disabled:opacity-50"
            >
              Export JSON
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImportExport;
