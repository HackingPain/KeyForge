import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const IPAllowlist = ({ api }) => {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [newIp, setNewIp] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [checkIp, setCheckIp] = useState('');
  const [checkResult, setCheckResult] = useState(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    fetchEntries();
  }, []);

  const fetchEntries = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/ip-allowlist');
      setEntries(response.data.entries || response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load IP allowlist.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newIp.trim()) return;
    setAdding(true);
    setError('');
    setSuccess('');
    try {
      await api.post('/ip-allowlist', { ip: newIp.trim(), description: newDescription.trim() });
      setSuccess('IP added to allowlist.');
      setNewIp('');
      setNewDescription('');
      fetchEntries();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add IP.');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id) => {
    setDeleting(id);
    setError('');
    try {
      await api.delete(`/ip-allowlist/${id}`);
      setSuccess('IP removed from allowlist.');
      fetchEntries();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to remove IP.');
    } finally {
      setDeleting(null);
    }
  };

  const handleCheck = async () => {
    if (!checkIp.trim()) return;
    setChecking(true);
    setCheckResult(null);
    setError('');
    try {
      const response = await api.post('/ip-allowlist/check', { ip: checkIp.trim() });
      setCheckResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to check IP.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">IP Allowlist</h2>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs">Dismiss</button>
        </div>
      )}

      {success && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4 flex items-center justify-between">
          <p className="text-sm text-green-700">{success}</p>
          <button onClick={() => setSuccess('')} className="text-green-500 text-xs">Dismiss</button>
        </div>
      )}

      {/* Add IP Form */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Add IP / <JargonTerm term="CIDR">CIDR</JargonTerm></h3>
        <form onSubmit={handleAdd} className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">IP Address or <JargonTerm term="CIDR">CIDR</JargonTerm></label>
            <input
              type="text"
              value={newIp}
              onChange={(e) => setNewIp(e.target.value)}
              placeholder="192.168.1.0/24"
              className="px-3 py-2 border border-gray-300 rounded-md text-sm w-48"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Description</label>
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Office network"
              className="px-3 py-2 border border-gray-300 rounded-md text-sm w-48"
            />
          </div>
          <button
            type="submit"
            disabled={adding || !newIp.trim()}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >
            {adding ? 'Adding...' : 'Add'}
          </button>
        </form>
      </div>

      {/* Check IP */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Check IP</h3>
        <div className="flex gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">IP Address</label>
            <input
              type="text"
              value={checkIp}
              onChange={(e) => setCheckIp(e.target.value)}
              placeholder="192.168.1.100"
              className="px-3 py-2 border border-gray-300 rounded-md text-sm w-48"
            />
          </div>
          <button
            onClick={handleCheck}
            disabled={checking || !checkIp.trim()}
            className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 text-sm font-medium disabled:opacity-50"
          >
            {checking ? 'Checking...' : 'Check'}
          </button>
        </div>
        {checkResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${checkResult.allowed ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {checkResult.allowed ? 'IP is allowed' : 'IP is not allowed'}
            {checkResult.matched_rule && <span className="ml-2 text-xs">({checkResult.matched_rule})</span>}
          </div>
        )}
      </div>

      {/* Entries Table */}
      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : entries.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No IP allowlist entries</p>
          <p className="text-sm">Add IPs or <JargonTerm term="CIDR">CIDR</JargonTerm> ranges above to restrict access.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">IP / <JargonTerm term="CIDR">CIDR</JargonTerm></th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Added</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {entries.map((entry, idx) => (
                <tr key={entry.id || idx}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">{entry.ip}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{entry.description || '-'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {entry.created_at ? new Date(entry.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <button
                      onClick={() => handleDelete(entry.id)}
                      disabled={deleting === entry.id}
                      className="px-3 py-1 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50"
                    >
                      {deleting === entry.id ? 'Removing...' : 'Remove'}
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

export default IPAllowlist;
