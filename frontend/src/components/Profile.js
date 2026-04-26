import { useState, useEffect } from "react";

const Profile = ({ api, advancedEnabled, onToggleAdvanced, onLogout }) => {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get("/auth/me")
      .then((response) => {
        if (cancelled) return;
        setUsername(response.data?.username || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.data?.detail || err.message || "Failed to load profile.");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const handleLogout = async () => {
    if (typeof onLogout === "function") {
      await onLogout();
      return;
    }
    try {
      await api.post("/auth/logout");
    } catch (e) {
      // ignore
    }
    window.location.reload();
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 max-w-2xl">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Profile</h2>
        <p className="text-sm text-gray-500 mt-1">
          Your account and display preferences.
        </p>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 flex items-center">
          <svg
            className="w-5 h-5 text-red-600 mr-2 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Account section */}
      <div className="mb-6 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
          Account
        </h3>
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600">Username</span>
          {loading ? (
            <span
              data-testid="profile-username-loading"
              className="text-sm text-gray-400"
            >
              Loading...
            </span>
          ) : (
            <span
              data-testid="profile-username"
              className="text-sm font-medium text-gray-900"
            >
              {username || "Unknown"}
            </span>
          )}
        </div>
      </div>

      {/* Preferences section */}
      <div className="mb-6 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
          Preferences
        </h3>
        <label className="flex items-center justify-between cursor-pointer">
          <span>
            <span className="block text-sm font-medium text-gray-900">
              Show advanced features
            </span>
            <span className="block text-xs text-gray-500 mt-0.5">
              Reveals KMS, encryption, audit integrity, and other power-user tools in the sidebar.
            </span>
          </span>
          <span className="relative inline-flex items-center ml-4 flex-shrink-0">
            <input
              type="checkbox"
              role="switch"
              aria-label="Show advanced features"
              checked={!!advancedEnabled}
              onChange={onToggleAdvanced}
              className="sr-only peer"
            />
            <span className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-indigo-600 transition-colors"></span>
            <span className="absolute left-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform peer-checked:translate-x-5"></span>
          </span>
        </label>
      </div>

      {/* Session section */}
      <div className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
          Session
        </h3>
        <button
          type="button"
          onClick={handleLogout}
          className="w-full sm:w-auto bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
        >
          Logout
        </button>
      </div>
    </div>
  );
};

export default Profile;
