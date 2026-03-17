import { useState } from "react";

const SecretScanner = ({ api }) => {
  const [scanType, setScanType] = useState('secrets');
  const [files, setFiles] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleScan = async (e) => {
    e.preventDefault();
    if (!files || files.length === 0) return;

    setLoading(true);
    setError('');
    setResults(null);

    const formData = new FormData();
    if (scanType === 'mask') {
      formData.append('file', files[0]);
    } else {
      for (const file of files) {
        formData.append('files', file);
      }
    }

    const endpoints = {
      secrets: '/scan/secrets',
      mask: '/scan/mask-suggestions',
      dependencies: '/scan/dependencies',
    };

    try {
      const response = await api.post(endpoints[scanType], formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Scan failed.');
    } finally {
      setLoading(false);
    }
  };

  const severityColor = (sev) => {
    switch (sev) {
      case 'critical': return 'bg-red-100 text-red-800';
      case 'high': return 'bg-orange-100 text-orange-800';
      default: return 'bg-yellow-100 text-yellow-800';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Secret Scanner</h2>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <form onSubmit={handleScan} className="mb-6">
        <div className="flex flex-wrap gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scan Type</label>
            <select
              value={scanType}
              onChange={(e) => setScanType(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm"
            >
              <option value="secrets">Secret Detection</option>
              <option value="mask">Masking Suggestions</option>
              <option value="dependencies">Dependency Analysis</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {scanType === 'mask' ? 'Upload File' : 'Upload Files'}
            </label>
            <input
              type="file"
              multiple={scanType !== 'mask'}
              onChange={(e) => setFiles(e.target.files)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={loading || !files}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
        >
          {loading ? 'Scanning...' : 'Run Scan'}
        </button>
      </form>

      {loading && (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      )}

      {results && scanType === 'secrets' && (
        <div>
          <div className="grid grid-cols-3 gap-4 mb-4">
            {Object.entries(results.severity_summary || {}).map(([sev, count]) => (
              <div key={sev} className={`rounded-lg p-3 ${severityColor(sev)}`}>
                <p className="text-xs font-medium capitalize">{sev}</p>
                <p className="text-2xl font-bold">{count}</p>
              </div>
            ))}
          </div>
          <h3 className="font-semibold mb-2">Findings ({results.total_findings})</h3>
          <div className="space-y-2">
            {(results.findings || []).map((finding, i) => (
              <div key={i} className="border border-gray-200 rounded p-3">
                <div className="flex justify-between">
                  <span className="font-medium text-sm">{finding.type || finding.pattern}</span>
                  <span className={`px-2 py-0.5 text-xs rounded-full ${severityColor(finding.severity)}`}>
                    {finding.severity}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1">{finding.filename} {finding.line ? '(line ' + finding.line + ')' : ''}</p>
                {finding.suggestion && <p className="text-xs text-gray-600 mt-1">{finding.suggestion}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {results && scanType === 'mask' && (
        <div>
          <h3 className="font-semibold mb-2">Masking Suggestions ({results.total_suggestions})</h3>
          <div className="space-y-3">
            {(results.suggestions || []).map((sug, i) => (
              <div key={i} className="border border-gray-200 rounded p-3">
                <p className="text-sm font-medium">{sug.env_var_name || sug.variable}</p>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Original</p>
                    <code className="text-xs bg-red-50 p-1 rounded block overflow-x-auto">{sug.original}</code>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Replacement</p>
                    <code className="text-xs bg-green-50 p-1 rounded block overflow-x-auto">{sug.replacement}</code>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {results && scanType === 'dependencies' && (
        <div>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-sm text-blue-600">Detected</p>
              <p className="text-2xl font-bold text-blue-900">{results.total_detected}</p>
            </div>
            <div className="bg-yellow-50 rounded-lg p-3">
              <p className="text-sm text-yellow-600">Missing Credentials</p>
              <p className="text-2xl font-bold text-yellow-900">{results.missing_credentials}</p>
            </div>
          </div>
          <div className="space-y-2">
            {(results.dependencies || []).map((dep, i) => (
              <div key={i} className="flex justify-between items-center border border-gray-200 rounded p-3">
                <div>
                  <span className="font-medium text-sm">{dep.package || dep.dependency}</span>
                  <span className="text-xs text-gray-500 ml-2">expects: {dep.expected_api}</span>
                </div>
                <span className={'px-2 py-1 text-xs rounded-full ' + (dep.has_credential ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800')}>
                  {dep.has_credential ? 'Configured' : 'Missing'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SecretScanner;
