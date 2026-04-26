import { useState, useEffect } from "react";
import JargonTerm from "./JargonTerm";

const MFASetup = ({ api }) => {
  const [status, setStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [backupCodes, setBackupCodes] = useState([]);
  const [verifyCode, setVerifyCode] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showDisable, setShowDisable] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await api.get('/mfa/status');
      setStatus(response.data);
      if (response.data.backup_codes) {
        setBackupCodes(response.data.backup_codes);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load MFA status.');
    } finally {
      setLoading(false);
    }
  };

  const handleEnableMFA = async () => {
    setActionLoading(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/mfa/setup');
      setSetupData(response.data);
      if (response.data.backup_codes) {
        setBackupCodes(response.data.backup_codes);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize MFA setup.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!verifyCode || verifyCode.length !== 6) return;
    setActionLoading(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/mfa/verify', { code: verifyCode });
      setSuccess(response.data.message || 'MFA verified and enabled successfully.');
      setVerifyCode('');
      setSetupData(null);
      fetchStatus();
    } catch (err) {
      setError(err.response?.data?.detail || 'Verification failed. Check your code.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisableMFA = async () => {
    if (!disableCode || disableCode.length !== 6) return;
    setActionLoading(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/mfa/disable', { code: disableCode });
      setSuccess(response.data.message || 'MFA has been disabled.');
      setDisableCode('');
      setShowDisable(false);
      setSetupData(null);
      setBackupCodes([]);
      fetchStatus();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to disable MFA.');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6"><JargonTerm term="MFA">MFA</JargonTerm> Setup</h2>

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

      {/* Current Status */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Current Status</h3>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 text-sm font-medium rounded-full ${status?.enabled ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
            {status?.enabled ? (<><JargonTerm term="MFA">MFA</JargonTerm> Enabled</>) : (<><JargonTerm term="MFA">MFA</JargonTerm> Disabled</>)}
          </span>
          {status?.enabled && status?.verified_at && (
            <span className="text-xs text-gray-500">Verified: {new Date(status.verified_at).toLocaleString()}</span>
          )}
        </div>
      </div>

      {/* Enable MFA */}
      {!status?.enabled && !setupData && (
        <div className="mb-6">
          <button
            onClick={handleEnableMFA}
            disabled={actionLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
          >
            {actionLoading ? 'Setting up...' : (<>Enable <JargonTerm term="MFA">MFA</JargonTerm></>)}
          </button>
          <p className="text-xs text-gray-500 mt-2">Set up two-factor authentication using a <JargonTerm term="TOTP">TOTP</JargonTerm> authenticator app.</p>
        </div>
      )}

      {/* Setup Data */}
      {setupData && (
        <div className="mb-6 p-4 border border-indigo-200 rounded-lg bg-indigo-50">
          <h3 className="text-sm font-semibold text-indigo-800 mb-3">Setup Your Authenticator</h3>
          <p className="text-sm text-indigo-700 mb-3">Add this account to your authenticator app (Google Authenticator, Authy, etc.):</p>

          {setupData.provisioning_uri && (
            <div className="mb-3">
              <label className="block text-xs text-indigo-600 mb-1">Provisioning URI</label>
              <div className="bg-white border border-indigo-200 rounded p-2 text-xs font-mono break-all select-all">
                {setupData.provisioning_uri}
              </div>
            </div>
          )}

          {setupData.secret && (
            <div className="mb-3">
              <label className="block text-xs text-indigo-600 mb-1">Secret Key (manual entry)</label>
              <div className="bg-white border border-indigo-200 rounded p-2 text-sm font-mono tracking-wider select-all">
                {setupData.secret}
              </div>
            </div>
          )}

          {/* Backup Codes */}
          {backupCodes.length > 0 && (
            <div className="mt-4">
              <label className="block text-xs text-indigo-600 mb-1">Backup Codes (save these securely)</label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {backupCodes.map((code, i) => (
                  <div key={i} className="bg-white border border-indigo-200 rounded px-2 py-1 text-sm font-mono text-center">
                    {code}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verification */}
          <div className="mt-4 pt-4 border-t border-indigo-200">
            <label className="block text-xs text-indigo-600 mb-1">Enter 6-digit code from your authenticator</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                className="w-32 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono text-center tracking-widest"
              />
              <button
                onClick={handleVerify}
                disabled={actionLoading || verifyCode.length !== 6}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50"
              >
                {actionLoading ? 'Verifying...' : 'Verify'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Disable MFA */}
      {status?.enabled && (
        <div className="mt-6">
          {!showDisable ? (
            <button
              onClick={() => setShowDisable(true)}
              className="px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded-md hover:bg-red-100 text-sm font-medium"
            >
              Disable <JargonTerm term="MFA">MFA</JargonTerm>
            </button>
          ) : (
            <div className="p-4 border border-red-200 rounded-lg bg-red-50">
              <h3 className="text-sm font-semibold text-red-800 mb-2">Confirm <JargonTerm term="MFA">MFA</JargonTerm> Disable</h3>
              <p className="text-xs text-red-600 mb-3">Enter your current 6-digit code to disable MFA.</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  className="w-32 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono text-center tracking-widest"
                />
                <button
                  onClick={handleDisableMFA}
                  disabled={actionLoading || disableCode.length !== 6}
                  className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm font-medium disabled:opacity-50"
                >
                  {actionLoading ? 'Disabling...' : 'Confirm Disable'}
                </button>
                <button
                  onClick={() => { setShowDisable(false); setDisableCode(''); }}
                  className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MFASetup;
