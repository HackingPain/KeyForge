import { useState, useEffect } from "react";

const VALID_EVENTS = [
  'credential.expired',
  'credential.test_failed',
  'rotation.overdue',
  'health_check.failed',
];

const WebhookManager = ({ api }) => {
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newWebhook, setNewWebhook] = useState({ url: '', events: [], enabled: true });
  const [testResult, setTestResult] = useState(null);

  useEffect(() => { fetchWebhooks(); }, []);

  const fetchWebhooks = async () => {
    setLoading(true);
    try {
      const response = await api.get('/webhooks');
      setWebhooks(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load webhooks.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (newWebhook.events.length === 0) {
      setError('Select at least one event.');
      return;
    }
    try {
      await api.post('/webhooks', newWebhook);
      setNewWebhook({ url: '', events: [], enabled: true });
      setShowCreate(false);
      fetchWebhooks();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create webhook.');
    }
  };

  const toggleEvent = (event) => {
    setNewWebhook(prev => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter(e => e !== event)
        : [...prev.events, event],
    }));
  };

  const handleToggle = async (webhook) => {
    try {
      await api.put(`/webhooks/${webhook.id}`, { enabled: !webhook.enabled });
      fetchWebhooks();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update webhook.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this webhook?')) return;
    try {
      await api.delete(`/webhooks/${id}`);
      fetchWebhooks();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete webhook.');
    }
  };

  const handleTest = async (id) => {
    setTestResult(null);
    try {
      const response = await api.post(`/webhooks/${id}/test`);
      setTestResult(response.data);
    } catch (err) {
      setTestResult({ error: err.response?.data?.detail || 'Test failed.' });
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Webhooks</h2>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium"
        >
          {showCreate ? 'Cancel' : 'Add Webhook'}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs mt-1">Dismiss</button>
        </div>
      )}

      {testResult && (
        <div className={`mb-4 rounded-lg p-4 ${testResult.error ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
          <p className="text-sm font-medium">{testResult.message || testResult.error}</p>
          {testResult.response_status && <p className="text-xs mt-1">Status: {testResult.response_status}</p>}
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-gray-50 rounded-lg">
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">Webhook URL</label>
            <input
              type="url"
              value={newWebhook.url}
              onChange={(e) => setNewWebhook({ ...newWebhook, url: e.target.value })}
              placeholder="https://example.com/webhook"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              required
            />
          </div>
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-2">Events</label>
            <div className="flex flex-wrap gap-2">
              {VALID_EVENTS.map(event => (
                <button
                  key={event}
                  type="button"
                  onClick={() => toggleEvent(event)}
                  className={`px-3 py-1 text-xs rounded-full ${
                    newWebhook.events.includes(event) ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {event}
                </button>
              ))}
            </div>
          </div>
          <button type="submit" className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm">
            Create Webhook
          </button>
        </form>
      )}

      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : webhooks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No webhooks configured</p>
          <p className="text-sm">Add webhooks to get notified when credentials expire or health checks fail.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map((wh) => (
            <div key={wh.id} className="border border-gray-200 rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${wh.enabled ? 'bg-green-500' : 'bg-gray-400'}`}></span>
                    <p className="font-medium text-sm text-gray-900 truncate">{wh.url}</p>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {wh.events.map(ev => (
                      <span key={ev} className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">{ev}</span>
                    ))}
                  </div>
                  {wh.last_triggered && (
                    <p className="text-xs text-gray-400 mt-2">Last triggered: {new Date(wh.last_triggered).toLocaleString()}</p>
                  )}
                </div>
                <div className="flex gap-2 ml-4">
                  <button onClick={() => handleTest(wh.id)} className="text-xs text-indigo-600 hover:text-indigo-800">Test</button>
                  <button onClick={() => handleToggle(wh)} className="text-xs text-gray-500 hover:text-gray-700">
                    {wh.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button onClick={() => handleDelete(wh.id)} className="text-xs text-red-500 hover:text-red-700">Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WebhookManager;
