import { useState, useEffect } from "react";

const AuditLog = ({ api }) => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Pagination
  const [skip, setSkip] = useState(0);
  const limit = 20;

  useEffect(() => {
    fetchLogs();
    fetchStats();
  }, [skip, actionFilter, dateFrom, dateTo]);

  const fetchStats = async () => {
    try {
      const response = await api.get('/audit-logs/stats');
      setStats(response.data);
    } catch (err) {
      // Stats are optional, don't block on failure
    }
  };

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const params = { skip, limit };
      if (actionFilter) params.action = actionFilter;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const response = await api.get('/audit-logs', { params });
      const data = response.data;
      if (Array.isArray(data)) {
        setLogs(data);
        setTotal(data.length >= limit ? skip + data.length + 1 : skip + data.length);
      } else {
        setLogs(data.logs || data.items || []);
        setTotal(data.total || data.count || 0);
      }
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to load audit logs.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const actionTypes = [
    '', 'credential_created', 'credential_deleted', 'credential_tested',
    'credential_rotated', 'login', 'logout', 'team_created', 'team_updated',
    'export', 'import', 'webhook_created', 'scan_performed'
  ];

  const formatTimestamp = (ts) => {
    if (!ts) return '-';
    const date = new Date(ts);
    return date.toLocaleString();
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Audit Log</h2>

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

      {/* Summary Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-indigo-50 rounded-lg p-4">
            <p className="text-sm text-indigo-600 font-medium">Last 7 Days</p>
            <p className="text-2xl font-bold text-indigo-900">{stats.last_7_days ?? stats.total ?? '-'}</p>
            <p className="text-xs text-indigo-500">actions recorded</p>
          </div>
          <div className="bg-green-50 rounded-lg p-4">
            <p className="text-sm text-green-600 font-medium">Last 24 Hours</p>
            <p className="text-2xl font-bold text-green-900">{stats.last_24_hours ?? '-'}</p>
            <p className="text-xs text-green-500">actions recorded</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-sm text-gray-600 font-medium">Total</p>
            <p className="text-2xl font-bold text-gray-900">{stats.total ?? '-'}</p>
            <p className="text-xs text-gray-500">all-time actions</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6 p-4 bg-gray-50 rounded-lg">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Action Type</label>
          <select
            value={actionFilter}
            onChange={(e) => { setActionFilter(e.target.value); setSkip(0); }}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">All Actions</option>
            {actionTypes.filter(a => a).map(action => (
              <option key={action} value={action}>{action.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">From Date</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); setSkip(0); }}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">To Date</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); setSkip(0); }}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={() => { setActionFilter(''); setDateFrom(''); setDateTo(''); setSkip(0); }}
            className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2"
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Resource</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Details</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {logs.map((log, idx) => (
                  <tr key={log.id || idx}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatTimestamp(log.timestamp || log.created_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 text-xs font-medium rounded-full bg-indigo-100 text-indigo-800">
                        {(log.action || '').replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {log.resource_type || '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">
                      {typeof log.details === 'object' ? JSON.stringify(log.details) : (log.details || '-')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {logs.length === 0 && (
            <div className="text-center py-8">
              <p className="text-gray-500">No audit log entries found.</p>
            </div>
          )}

          {/* Pagination */}
          <div className="flex justify-between items-center mt-4">
            <p className="text-sm text-gray-500">
              Showing {skip + 1} - {skip + logs.length} {total > 0 ? `of ${total}` : ''}
            </p>
            <div className="flex space-x-2">
              <button
                onClick={() => setSkip(Math.max(0, skip - limit))}
                disabled={skip === 0}
                className="px-3 py-1 text-sm border border-gray-300 rounded-md disabled:opacity-50 hover:bg-gray-50"
              >
                Previous
              </button>
              <button
                onClick={() => setSkip(skip + limit)}
                disabled={logs.length < limit}
                className="px-3 py-1 text-sm border border-gray-300 rounded-md disabled:opacity-50 hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AuditLog;
