import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const AuditIntegrity = ({ api }) => {
  const [stats, setStats] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const response = await api.get('/audit/integrity/stats');
      setStats(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load audit chain stats.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/audit/integrity/verify');
      setVerifyResult(response.data);
      if (response.data.valid || response.data.is_valid) {
        setSuccess('Audit chain integrity verified successfully.');
      } else {
        setError('Audit chain integrity check found issues.');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Verification failed.');
    } finally {
      setVerifying(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await api.get('/audit/integrity/export', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'audit-chain-export.json');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || 'Export failed.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Audit Integrity</h2>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 text-sm font-medium disabled:opacity-50"
          >
            {exporting ? 'Exporting...' : 'Export Chain'}
          </button>
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >
            {verifying ? 'Verifying...' : 'Verify Chain'}
          </button>
        </div>
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
          {/* Chain Stats */}
          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-4">
                <p className="text-sm text-indigo-600 dark:text-indigo-400 font-medium">Total Entries</p>
                <p className="text-2xl font-bold text-indigo-900 dark:text-indigo-200">{stats.total_entries ?? 0}</p>
                <p className="text-xs text-indigo-500 dark:text-indigo-400">in <JargonTerm term="audit chain">audit chain</JargonTerm></p>
              </div>
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                <p className="text-sm text-green-600 dark:text-green-400 font-medium">Chain Status</p>
                <p className="text-2xl font-bold text-green-900 dark:text-green-200">
                  {stats.chain_valid || stats.is_valid ? 'Valid' : 'Broken'}
                </p>
                <p className="text-xs text-green-500 dark:text-green-400">integrity status</p>
              </div>
              <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
                <p className="text-sm text-purple-600 dark:text-purple-400 font-medium">Last Verified</p>
                <p className="text-lg font-bold text-purple-900 dark:text-purple-200">
                  {stats.last_verified ? new Date(stats.last_verified).toLocaleDateString() : 'Never'}
                </p>
                <p className="text-xs text-purple-500 dark:text-purple-400">verification date</p>
              </div>
            </div>
          )}

          {/* Verification Result */}
          {verifyResult && (
            <div className={`rounded-lg p-4 mb-6 border ${
              verifyResult.valid || verifyResult.is_valid
                ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
            }`}>
              <h3 className={`text-lg font-semibold mb-3 ${
                verifyResult.valid || verifyResult.is_valid ? 'text-green-800 dark:text-green-300' : 'text-red-800 dark:text-red-300'
              }`}>
                Verification Result: {verifyResult.valid || verifyResult.is_valid ? 'Valid' : 'Broken'}
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Entries Checked</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100">{verifyResult.entries_checked ?? verifyResult.total_entries ?? 0}</p>
                </div>
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Gaps Found</p>
                  <p className="font-semibold text-gray-900 dark:text-gray-100">{verifyResult.gaps ?? verifyResult.gap_count ?? 0}</p>
                </div>
                {verifyResult.first_entry && (
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">First Entry</p>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">{new Date(verifyResult.first_entry).toLocaleDateString()}</p>
                  </div>
                )}
                {verifyResult.last_entry && (
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">Last Entry</p>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">{new Date(verifyResult.last_entry).toLocaleDateString()}</p>
                  </div>
                )}
              </div>
              {verifyResult.broken_links && verifyResult.broken_links.length > 0 && (
                <div className="mt-3">
                  <p className="text-sm font-medium text-red-600 dark:text-red-400 mb-1">Broken Links:</p>
                  <ul className="list-disc list-inside text-sm text-red-500 dark:text-red-400">
                    {verifyResult.broken_links.map((link, i) => (
                      <li key={i}>Entry #{link.entry_id || link}: {link.reason || 'hash mismatch'}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {!stats && !verifyResult && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p className="text-lg mb-2">No audit data</p>
              <p className="text-sm">Click "Verify Chain" to check audit log integrity.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AuditIntegrity;
