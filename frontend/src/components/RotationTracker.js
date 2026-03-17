import { useState, useEffect } from "react";

const RotationTracker = ({ api }) => {
  const [policies, setPolicies] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showPolicyForm, setShowPolicyForm] = useState(null);
  const [policyForm, setPolicyForm] = useState({ rotation_interval_days: 90 });
  const [actionLoading, setActionLoading] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [policiesRes, credsRes] = await Promise.all([
        api.get('/rotation-policies'),
        api.get('/credentials')
      ]);
      setPolicies(policiesRes.data);
      setCredentials(credsRes.data);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to load rotation data.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const getRotationStatus = (credId) => {
    const policy = policies.find(p => p.credential_id === credId);
    if (!policy) return { status: 'no-policy', label: 'No Policy', color: 'bg-gray-100 text-gray-600' };

    const lastRotated = policy.last_rotated_at ? new Date(policy.last_rotated_at) : new Date(policy.created_at);
    const now = new Date();
    const daysSinceRotation = Math.floor((now - lastRotated) / (1000 * 60 * 60 * 24));
    const daysUntilDue = policy.rotation_interval_days - daysSinceRotation;

    if (daysUntilDue < 0) {
      return { status: 'overdue', label: `Overdue by ${Math.abs(daysUntilDue)} days`, color: 'bg-red-100 text-red-800' };
    } else if (daysUntilDue <= 7) {
      return { status: 'due-soon', label: `Due in ${daysUntilDue} days`, color: 'bg-yellow-100 text-yellow-800' };
    } else {
      return { status: 'ok', label: `OK (${daysUntilDue} days left)`, color: 'bg-green-100 text-green-800' };
    }
  };

  const handleSetPolicy = async (credentialId) => {
    setActionLoading(credentialId);
    setError('');
    try {
      await api.post('/rotation-policies', {
        credential_id: credentialId,
        rotation_interval_days: policyForm.rotation_interval_days
      });
      setShowPolicyForm(null);
      setPolicyForm({ rotation_interval_days: 90 });
      await fetchData();
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to set rotation policy.';
      setError(message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkRotated = async (credentialId) => {
    setActionLoading(credentialId);
    setError('');
    try {
      const policy = policies.find(p => p.credential_id === credentialId);
      if (policy) {
        await api.put(`/rotation-policies/${policy.id}/rotate`);
        await fetchData();
      }
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to mark as rotated.';
      setError(message);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        <p className="mt-2 text-sm text-gray-500">Loading rotation policies...</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Rotation Tracker</h2>
        <button
          onClick={fetchData}
          className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
        >
          Refresh
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

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Credential</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Environment</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rotation Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Interval</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {credentials.map((cred) => {
              const rotationInfo = getRotationStatus(cred.id);
              const policy = policies.find(p => p.credential_id === cred.id);
              return (
                <tr key={cred.id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900 capitalize">{cred.api_name}</div>
                    {cred.api_key_preview && (
                      <div className="text-xs text-gray-500 font-mono">{cred.api_key_preview}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">{cred.environment}</span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${rotationInfo.color}`}>
                      {rotationInfo.label}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {policy ? `${policy.rotation_interval_days} days` : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                    {policy ? (
                      <button
                        onClick={() => handleMarkRotated(cred.id)}
                        disabled={actionLoading === cred.id}
                        className="text-green-600 hover:text-green-900 disabled:opacity-50"
                      >
                        {actionLoading === cred.id ? 'Updating...' : 'Mark Rotated'}
                      </button>
                    ) : (
                      <button
                        onClick={() => setShowPolicyForm(showPolicyForm === cred.id ? null : cred.id)}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        Set Policy
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showPolicyForm && (
        <div className="mt-4 p-4 border border-gray-200 rounded-lg bg-gray-50">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            Set Rotation Policy for {credentials.find(c => c.id === showPolicyForm)?.api_name}
          </h3>
          <div className="flex items-center space-x-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Rotation Interval (days)</label>
              <select
                value={policyForm.rotation_interval_days}
                onChange={(e) => setPolicyForm({ rotation_interval_days: parseInt(e.target.value) })}
                className="px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
                <option value={180}>180 days</option>
                <option value={365}>365 days</option>
              </select>
            </div>
            <button
              onClick={() => handleSetPolicy(showPolicyForm)}
              disabled={actionLoading === showPolicyForm}
              className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 text-sm disabled:opacity-50"
            >
              {actionLoading === showPolicyForm ? 'Saving...' : 'Save Policy'}
            </button>
            <button
              onClick={() => setShowPolicyForm(null)}
              className="bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {credentials.length === 0 && !error && (
        <div className="text-center py-8">
          <p className="text-gray-500">No credentials found. Add credentials first to set rotation policies.</p>
        </div>
      )}
    </div>
  );
};

export default RotationTracker;
