import { useState, useEffect } from "react";

const HealthChecks = ({ api }) => {
  const [results, setResults] = useState([]);
  const [schedule, setSchedule] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [runResult, setRunResult] = useState(null);
  const [intervalHours, setIntervalHours] = useState(24);

  useEffect(() => {
    fetchResults();
    fetchSchedule();
  }, []);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const response = await api.get('/health-checks/results?limit=50');
      setResults(response.data || []);
    } catch (err) {
      // Not critical
    } finally {
      setLoading(false);
    }
  };

  const fetchSchedule = async () => {
    try {
      const response = await api.get('/health-checks/schedule');
      setSchedule(response.data);
      if (response.data?.interval_hours) setIntervalHours(response.data.interval_hours);
    } catch (err) {
      // No schedule yet
    }
  };

  const handleRunChecks = async () => {
    setRunning(true);
    setError('');
    setRunResult(null);
    try {
      const response = await api.post('/health-checks/run');
      setRunResult(response.data);
      fetchResults();
    } catch (err) {
      setError(err.response?.data?.detail || 'Health check failed.');
    } finally {
      setRunning(false);
    }
  };

  const handleSaveSchedule = async () => {
    try {
      const response = await api.post('/health-checks/schedule', {
        interval_hours: intervalHours,
        enabled: true,
      });
      setSchedule(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save schedule.');
    }
  };

  const statusColor = (status) => {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-800';
      case 'format_valid': return 'bg-blue-100 text-blue-800';
      case 'invalid': case 'error': return 'bg-red-100 text-red-800';
      case 'expired': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Health Checks</h2>
        <button
          onClick={handleRunChecks}
          disabled={running}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
        >
          {running ? 'Running...' : 'Run Health Checks'}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs mt-1">Dismiss</button>
        </div>
      )}

      {/* Schedule Config */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Schedule Configuration</h3>
        <div className="flex items-center gap-4">
          <div>
            <label className="text-xs text-gray-500">Check every</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="1"
                max="168"
                value={intervalHours}
                onChange={(e) => setIntervalHours(parseInt(e.target.value) || 24)}
                className="w-20 px-2 py-1 border border-gray-300 rounded text-sm"
              />
              <span className="text-sm text-gray-500">hours</span>
            </div>
          </div>
          <button
            onClick={handleSaveSchedule}
            className="mt-4 px-3 py-1.5 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700"
          >
            Save Schedule
          </button>
          {schedule && (
            <div className="mt-4 text-xs text-gray-500">
              <p>Status: <span className={schedule.enabled ? 'text-green-600' : 'text-gray-500'}>{schedule.enabled ? 'Active' : 'Disabled'}</span></p>
              {schedule.next_run && <p>Next run: {new Date(schedule.next_run).toLocaleString()}</p>}
              {schedule.last_run && <p>Last run: {new Date(schedule.last_run).toLocaleString()}</p>}
            </div>
          )}
        </div>
      </div>

      {/* Run Result Summary */}
      {runResult && (
        <div className="mb-6 bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-sm font-medium text-green-800">
            Health check complete: {runResult.total_credentials} credential(s) checked
          </p>
          <p className="text-xs text-green-600 mt-1">Checked at: {new Date(runResult.checked_at).toLocaleString()}</p>
        </div>
      )}

      {/* Results Table */}
      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : results.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No health check results yet</p>
          <p className="text-sm">Click "Run Health Checks" to validate all your credentials.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Credential</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Response Time</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Message</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Checked At</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {results.map((result, idx) => (
                <tr key={result.id || idx}>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{result.credential_id?.slice(0, 8)}...</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs rounded-full ${statusColor(result.status)}`}>
                      {result.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{result.response_time}ms</td>
                  <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">{result.message}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{result.checked_at ? new Date(result.checked_at).toLocaleString() : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default HealthChecks;
