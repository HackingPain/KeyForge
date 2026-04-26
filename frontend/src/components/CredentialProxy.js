import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const CredentialProxy = ({ api }) => {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [newToken, setNewToken] = useState({ credential_id: '', ttl: 3600 });
  const [createdToken, setCreatedToken] = useState(null);

  useEffect(() => {
    fetchTokens();
  }, []);

  const fetchTokens = async () => {
    setLoading(true);
    try {
      const response = await api.get('/proxy/tokens');
      setTokens(response.data.tokens || response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load proxy tokens.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    setSuccess('');
    setCreatedToken(null);
    try {
      const response = await api.post('/proxy/tokens', {
        credential_id: newToken.credential_id,
        ttl: parseInt(newToken.ttl, 10),
      });
      setCreatedToken(response.data);
      setSuccess('Proxy token created successfully.');
      setShowForm(false);
      setNewToken({ credential_id: '', ttl: 3600 });
      fetchTokens();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create proxy token.');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (tokenId) => {
    setRevokingId(tokenId);
    setError('');
    try {
      await api.delete(`/proxy/tokens/${tokenId}`);
      setSuccess('Token revoked.');
      fetchTokens();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to revoke token.');
    } finally {
      setRevokingId(null);
    }
  };

  const formatTTL = (seconds) => {
    if (!seconds) return 'N/A';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Credential Proxy</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium"
        >
          {showForm ? 'Cancel' : 'Create Proxy Token'}
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

      {/* Created Token Display */}
      {createdToken && createdToken.token && (
        <div className="mb-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-sm font-medium text-yellow-800 dark:text-yellow-300 mb-1">New Proxy Token (copy now, shown once):</p>
          <code className="text-sm bg-yellow-100 dark:bg-yellow-900/40 px-2 py-1 rounded text-yellow-900 dark:text-yellow-200 break-all">
            {createdToken.token}
          </code>
        </div>
      )}

      {/* Create Form */}
      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Credential ID</label>
              <input
                type="text"
                value={newToken.credential_id}
                onChange={(e) => setNewToken({ ...newToken, credential_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                placeholder="Enter credential ID"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"><JargonTerm term="TTL">TTL</JargonTerm> (seconds)</label>
              <input
                type="number"
                value={newToken.ttl}
                onChange={(e) => setNewToken({ ...newToken, ttl: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                min="60"
                max="86400"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="mt-3 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >
            {creating ? 'Creating...' : 'Create Token'}
          </button>
        </form>
      )}

      {/* Tokens List */}
      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : tokens.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p className="text-lg mb-2">No active proxy tokens</p>
          <p className="text-sm">Create a proxy token to provide temporary credential access.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Token</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Credential</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"><JargonTerm term="TTL">TTL</JargonTerm></th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Created</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {tokens.map((t, idx) => (
                <tr key={t.id || idx}>
                  <td className="px-6 py-4 text-sm font-mono text-gray-900 dark:text-gray-100">
                    {t.token_masked || t.token_prefix || `${(t.token || t.id || '').substring(0, 8)}...`}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                    {t.credential_name || t.credential_id}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {formatTTL(t.ttl || t.ttl_seconds)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {t.created_at ? new Date(t.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      t.status === 'active' || t.active
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-gray-100 text-gray-600 dark:bg-gray-600 dark:text-gray-300'
                    }`}>
                      {t.status || (t.active ? 'Active' : 'Expired')}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => handleRevoke(t.id)}
                      disabled={revokingId === t.id}
                      className="px-3 py-1 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
                    >
                      {revokingId === t.id ? 'Revoking...' : 'Revoke'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CredentialProxy;
