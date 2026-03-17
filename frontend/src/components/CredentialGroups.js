import { useState, useEffect } from "react";

const CredentialGroups = ({ api }) => {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newGroup, setNewGroup] = useState({ name: '', description: '' });

  useEffect(() => { fetchGroups(); }, []);

  const fetchGroups = async () => {
    setLoading(true);
    try {
      const response = await api.get('/credential-groups');
      setGroups(response.data?.groups || response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load credential groups.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await api.post('/credential-groups', newGroup);
      setNewGroup({ name: '', description: '' });
      setShowCreate(false);
      fetchGroups();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create group.');
    }
  };

  const handleDelete = async (groupId) => {
    if (!window.confirm('Delete this credential group?')) return;
    try {
      await api.delete('/credential-groups/' + groupId);
      fetchGroups();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete group.');
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Credential Groups</h2>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium"
        >
          {showCreate ? 'Cancel' : 'New Group'}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError('')} className="text-red-500 text-xs mt-1">Dismiss</button>
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Group Name</label>
              <input
                type="text"
                value={newGroup.name}
                onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                type="text"
                value={newGroup.description}
                onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              />
            </div>
          </div>
          <button type="submit" className="mt-3 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm">
            Create Group
          </button>
        </form>
      )}

      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : groups.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No credential groups yet</p>
          <p className="text-sm">Create groups to organize your credentials by project or environment.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {groups.map((group) => (
            <div key={group.id} className="border border-gray-200 rounded-lg p-4 hover:border-indigo-300 transition">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-semibold text-gray-900">{group.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">{group.description || 'No description'}</p>
                </div>
                <button
                  onClick={() => handleDelete(group.id)}
                  className="text-red-400 hover:text-red-600 text-sm"
                >
                  Delete
                </button>
              </div>
              <div className="mt-3 flex items-center text-sm text-gray-500">
                <span>{group.credential_count || group.credentials?.length || 0} credentials</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default CredentialGroups;
