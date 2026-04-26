import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const EnvelopeEncryption = ({ api }) => {
  const [keyStatus, setKeyStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rotating, setRotating] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchKeyStatus();
  }, []);

  const fetchKeyStatus = async () => {
    setLoading(true);
    try {
      const response = await api.get('/encryption/envelope/keys/status');
      setKeyStatus(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load key status.');
    } finally {
      setLoading(false);
    }
  };

  const handleRotateKey = async () => {
    setRotating(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/encryption/envelope/keys/rotate-user');
      setSuccess(response.data.message || 'User data key rotated successfully.');
      fetchKeyStatus();
    } catch (err) {
      setError(err.response?.data?.detail || 'Key rotation failed.');
    } finally {
      setRotating(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white"><JargonTerm term="envelope encryption">Envelope Encryption</JargonTerm></h2>
        <button
          onClick={handleRotateKey}
          disabled={rotating}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
        >
          {rotating ? 'Rotating...' : (<>Rotate User Data Key (<JargonTerm term="DEK">DEK</JargonTerm>)</>)}
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
      ) : keyStatus ? (
        <div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-4">
              <p className="text-sm text-indigo-600 dark:text-indigo-400 font-medium">Key ID</p>
              <p className="text-lg font-bold text-indigo-900 dark:text-indigo-200 truncate" title={keyStatus.key_id}>
                {keyStatus.key_id || 'N/A'}
              </p>
              <p className="text-xs text-indigo-500 dark:text-indigo-400">current active key</p>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
              <p className="text-sm text-green-600 dark:text-green-400 font-medium">Created At</p>
              <p className="text-lg font-bold text-green-900 dark:text-green-200">
                {keyStatus.created_at ? new Date(keyStatus.created_at).toLocaleDateString() : 'N/A'}
              </p>
              <p className="text-xs text-green-500 dark:text-green-400">
                {keyStatus.created_at ? new Date(keyStatus.created_at).toLocaleTimeString() : ''}
              </p>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400 font-medium">Credential Count</p>
              <p className="text-2xl font-bold text-purple-900 dark:text-purple-200">{keyStatus.credential_count ?? 0}</p>
              <p className="text-xs text-purple-500 dark:text-purple-400">encrypted credentials</p>
            </div>
          </div>

          {keyStatus.algorithm && (
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Key Details</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-gray-500 dark:text-gray-400">Algorithm:</span>
                <span className="text-gray-900 dark:text-gray-100">{keyStatus.algorithm}</span>
                {keyStatus.status && (
                  <>
                    <span className="text-gray-500 dark:text-gray-400">Status:</span>
                    <span className="text-gray-900 dark:text-gray-100">{keyStatus.status}</span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p className="text-lg mb-2">No key status available</p>
          <p className="text-sm"><JargonTerm term="envelope encryption">Envelope encryption</JargonTerm> may not be configured yet.</p>
        </div>
      )}
    </div>
  );
};

export default EnvelopeEncryption;
