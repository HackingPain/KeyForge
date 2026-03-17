import { useState, useEffect } from "react";

const TeamManager = ({ api }) => {
  const [teams, setTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [teamMembers, setTeamMembers] = useState([]);
  const [sharedCredentials, setSharedCredentials] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Forms
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTeam, setNewTeam] = useState({ name: '', description: '' });
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMember, setNewMember] = useState({ username: '', role: 'member' });
  const [showShareCred, setShowShareCred] = useState(false);
  const [selectedCredToShare, setSelectedCredToShare] = useState('');

  useEffect(() => {
    fetchTeams();
    fetchCredentials();
  }, []);

  const fetchTeams = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/teams');
      setTeams(response.data);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to load teams.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const fetchCredentials = async () => {
    try {
      const response = await api.get('/credentials');
      setCredentials(response.data);
    } catch (err) {
      // Non-critical
    }
  };

  const selectTeam = async (team) => {
    setSelectedTeam(team);
    setError('');
    try {
      const [membersRes, sharedRes] = await Promise.all([
        api.get(`/teams/${team.id}/members`),
        api.get(`/teams/${team.id}/credentials`)
      ]);
      setTeamMembers(membersRes.data);
      setSharedCredentials(sharedRes.data);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to load team details.';
      setError(message);
    }
  };

  const handleCreateTeam = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    setError('');
    try {
      await api.post('/teams', newTeam);
      setNewTeam({ name: '', description: '' });
      setShowCreateForm(false);
      await fetchTeams();
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to create team.';
      setError(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!selectedTeam) return;
    setActionLoading(true);
    setError('');
    try {
      await api.post(`/teams/${selectedTeam.id}/members`, newMember);
      setNewMember({ username: '', role: 'member' });
      setShowAddMember(false);
      await selectTeam(selectedTeam);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to add member.';
      setError(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async (memberId) => {
    if (!window.confirm('Remove this member from the team?')) return;
    setError('');
    try {
      await api.delete(`/teams/${selectedTeam.id}/members/${memberId}`);
      await selectTeam(selectedTeam);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to remove member.';
      setError(message);
    }
  };

  const handleShareCredential = async (e) => {
    e.preventDefault();
    if (!selectedTeam || !selectedCredToShare) return;
    setActionLoading(true);
    setError('');
    try {
      await api.post(`/teams/${selectedTeam.id}/credentials`, { credential_id: selectedCredToShare });
      setSelectedCredToShare('');
      setShowShareCred(false);
      await selectTeam(selectedTeam);
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to share credential.';
      setError(message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        <p className="mt-2 text-sm text-gray-500">Loading teams...</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Team List */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900">Teams</h2>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-700 text-sm"
          >
            New Team
          </button>
        </div>

        {error && !selectedTeam && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {showCreateForm && (
          <form onSubmit={handleCreateTeam} className="mb-4 p-3 border border-gray-200 rounded-lg space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Team Name</label>
              <input
                type="text"
                value={newTeam.name}
                onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Engineering"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Description</label>
              <input
                type="text"
                value={newTeam.description}
                onChange={(e) => setNewTeam({ ...newTeam, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Optional description"
              />
            </div>
            <div className="flex space-x-2">
              <button
                type="submit"
                disabled={actionLoading}
                className="bg-green-600 text-white px-3 py-1.5 rounded-md hover:bg-green-700 text-sm disabled:opacity-50"
              >
                {actionLoading ? 'Creating...' : 'Create'}
              </button>
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="bg-gray-300 text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-400 text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          {teams.map((team) => (
            <button
              key={team.id}
              onClick={() => selectTeam(team)}
              className={`w-full text-left p-3 rounded-lg border transition-colors ${
                selectedTeam?.id === team.id
                  ? 'border-indigo-300 bg-indigo-50'
                  : 'border-gray-200 hover:bg-gray-50'
              }`}
            >
              <div className="font-medium text-gray-900">{team.name}</div>
              {team.description && (
                <div className="text-xs text-gray-500 mt-1">{team.description}</div>
              )}
              <div className="text-xs text-gray-400 mt-1">
                {team.member_count ?? '?'} members
              </div>
            </button>
          ))}
          {teams.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-4">No teams yet. Create one to get started.</p>
          )}
        </div>
      </div>

      {/* Team Details */}
      <div className="lg:col-span-2 space-y-6">
        {selectedTeam ? (
          <>
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
                <p className="text-sm text-red-700">{error}</p>
                <button onClick={() => setError('')} className="text-red-500 hover:text-red-700">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* Members */}
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-gray-900">Members - {selectedTeam.name}</h3>
                <button
                  onClick={() => setShowAddMember(!showAddMember)}
                  className="bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-700 text-sm"
                >
                  Add Member
                </button>
              </div>

              {showAddMember && (
                <form onSubmit={handleAddMember} className="mb-4 p-3 border border-gray-200 rounded-lg">
                  <div className="flex items-end space-x-3">
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">Username</label>
                      <input
                        type="text"
                        value={newMember.username}
                        onChange={(e) => setNewMember({ ...newMember, username: e.target.value })}
                        required
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                        placeholder="Username"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Role</label>
                      <select
                        value={newMember.role}
                        onChange={(e) => setNewMember({ ...newMember, role: e.target.value })}
                        className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="bg-green-600 text-white px-3 py-2 rounded-md hover:bg-green-700 text-sm disabled:opacity-50"
                    >
                      Add
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowAddMember(false)}
                      className="bg-gray-300 text-gray-700 px-3 py-2 rounded-md hover:bg-gray-400 text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              <div className="space-y-2">
                {teamMembers.map((member) => (
                  <div key={member.id || member.user_id} className="flex justify-between items-center p-3 border border-gray-200 rounded-lg">
                    <div>
                      <span className="text-sm font-medium text-gray-900">{member.username || member.email}</span>
                      <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600">{member.role}</span>
                    </div>
                    <button
                      onClick={() => handleRemoveMember(member.id || member.user_id)}
                      className="text-red-600 hover:text-red-900 text-sm"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {teamMembers.length === 0 && (
                  <p className="text-sm text-gray-500 text-center py-4">No members in this team yet.</p>
                )}
              </div>
            </div>

            {/* Shared Credentials */}
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-gray-900">Shared Credentials</h3>
                <button
                  onClick={() => setShowShareCred(!showShareCred)}
                  className="bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-700 text-sm"
                >
                  Share Credential
                </button>
              </div>

              {showShareCred && (
                <form onSubmit={handleShareCredential} className="mb-4 p-3 border border-gray-200 rounded-lg">
                  <div className="flex items-end space-x-3">
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">Select Credential</label>
                      <select
                        value={selectedCredToShare}
                        onChange={(e) => setSelectedCredToShare(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      >
                        <option value="">Choose credential...</option>
                        {credentials.map((cred) => (
                          <option key={cred.id} value={cred.id}>{cred.api_name} ({cred.environment})</option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="bg-green-600 text-white px-3 py-2 rounded-md hover:bg-green-700 text-sm disabled:opacity-50"
                    >
                      Share
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowShareCred(false)}
                      className="bg-gray-300 text-gray-700 px-3 py-2 rounded-md hover:bg-gray-400 text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              <div className="space-y-2">
                {sharedCredentials.map((cred) => (
                  <div key={cred.id} className="flex justify-between items-center p-3 border border-gray-200 rounded-lg">
                    <div>
                      <span className="text-sm font-medium text-gray-900 capitalize">{cred.api_name}</span>
                      <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600">{cred.environment}</span>
                    </div>
                  </div>
                ))}
                {sharedCredentials.length === 0 && (
                  <p className="text-sm text-gray-500 text-center py-4">No credentials shared with this team yet.</p>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="bg-white rounded-lg shadow-md p-6 text-center">
            <p className="text-gray-500">Select a team to view details, or create a new one.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TeamManager;
