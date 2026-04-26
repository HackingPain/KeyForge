import { useCallback, useEffect, useState } from "react";

/**
 * GitHubConnect renders the install + per-repo mint flow for the GitHub
 * credential issuer. The component is deliberately small: heavy lifting
 * (App JWTs, signed state, encryption) lives on the backend; this is the
 * minimum UI that makes "click a button, get a credential" work for a
 * non-technical user.
 *
 * Props:
 *   - api: shared axios instance (must already point at /api).
 *   - onCredentialMinted(credential): optional, invoked after a successful
 *     mint so the parent can refresh its credential list.
 */
const PERMISSION_PRESETS = [
  {
    id: "read_only",
    label: "Read only (recommended)",
    permissions: { contents: "read", metadata: "read" },
  },
  {
    id: "read_write",
    label: "Read and write",
    permissions: { contents: "write", metadata: "read", pull_requests: "write" },
  },
];

const GitHubConnect = ({ api, onCredentialMinted }) => {
  const [installations, setInstallations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const [repo, setRepo] = useState("");
  const [presetId, setPresetId] = useState(PERMISSION_PRESETS[0].id);
  const [minting, setMinting] = useState(false);
  const [mintError, setMintError] = useState("");
  const [toast, setToast] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await api.get("/issuers/github/installations");
      setInstallations(response.data?.installations || []);
    } catch (err) {
      const detail =
        err.response?.data?.detail || err.message || "Failed to load installations.";
      setLoadError(detail);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // If we came back from the GitHub install round-trip, refresh and
  // strip the query parameter so a reload doesn't keep re-firing it.
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("github");
    if (flag === "connected") {
      setToast("GitHub connected. You can now generate a credential below.");
      params.delete("github");
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname + (newSearch ? `?${newSearch}` : "") + window.location.hash;
      window.history.replaceState({}, "", newUrl);
      refresh();
    } else if (flag === "error") {
      const reason = params.get("reason") || "unknown_error";
      setToast(`GitHub connection failed: ${reason}.`);
      params.delete("github");
      params.delete("reason");
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname + (newSearch ? `?${newSearch}` : "") + window.location.hash;
      window.history.replaceState({}, "", newUrl);
    }
  }, [refresh]);

  const handleConnect = async () => {
    setStarting(true);
    setStartError("");
    try {
      const response = await api.post("/issuers/github/start");
      const installUrl = response.data?.install_url;
      if (!installUrl) {
        throw new Error("Backend did not return an install URL.");
      }
      window.open(installUrl, "_blank", "noopener,noreferrer");
    } catch (err) {
      const detail =
        err.response?.data?.detail || err.message || "Failed to start install.";
      setStartError(detail);
    } finally {
      setStarting(false);
    }
  };

  const handleMint = async (event) => {
    event.preventDefault();
    setMintError("");
    if (!repo || !repo.includes("/")) {
      setMintError("Repository must be in 'owner/name' form.");
      return;
    }
    const preset = PERMISSION_PRESETS.find((p) => p.id === presetId);
    if (!preset) {
      setMintError("Pick a permission level.");
      return;
    }
    setMinting(true);
    try {
      const response = await api.post("/issuers/github/mint", {
        repo,
        permissions: preset.permissions,
      });
      setToast("Credential minted. It is now in your Credentials list.");
      setRepo("");
      if (onCredentialMinted) {
        onCredentialMinted(response.data);
      }
    } catch (err) {
      const detail =
        err.response?.data?.detail || err.message || "Failed to mint credential.";
      setMintError(detail);
    } finally {
      setMinting(false);
    }
  };

  if (loading) {
    return <div className="p-4 text-sm text-gray-600">Loading GitHub status...</div>;
  }

  return (
    <div className="p-4 border border-gray-200 rounded-lg bg-white space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">GitHub</h3>
        {installations.length > 0 && (
          <span className="text-xs text-green-700 bg-green-100 px-2 py-1 rounded">
            {installations.length} installation{installations.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {loadError && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {loadError}
        </p>
      )}

      {toast && (
        <p
          role="status"
          className="text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded p-2"
        >
          {toast}
        </p>
      )}

      {installations.length === 0 ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-700">
            Connect GitHub to let KeyForge issue scoped credentials for your
            repositories. You will install the KeyForge GitHub App and choose
            which repos it can see.
          </p>
          <button
            type="button"
            onClick={handleConnect}
            disabled={starting}
            className="px-4 py-2 bg-gray-900 text-white text-sm rounded hover:bg-gray-700 disabled:opacity-50"
          >
            {starting ? "Opening GitHub..." : "Connect GitHub"}
          </button>
          {startError && (
            <p className="text-sm text-red-700">{startError}</p>
          )}
        </div>
      ) : (
        <form className="space-y-3" onSubmit={handleMint}>
          <p className="text-sm text-gray-700">
            Generate a credential scoped to a single repository. The
            credential is encrypted at rest; you will not see the raw token.
          </p>

          <label className="block text-sm">
            <span className="text-gray-700">Repository (owner/name)</span>
            <input
              type="text"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="acme/widgets"
              className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring focus:ring-gray-200"
              required
            />
          </label>

          <fieldset className="space-y-1">
            <legend className="text-sm text-gray-700">Permission level</legend>
            {PERMISSION_PRESETS.map((preset) => (
              <label key={preset.id} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="github-permission-preset"
                  value={preset.id}
                  checked={presetId === preset.id}
                  onChange={() => setPresetId(preset.id)}
                />
                <span>{preset.label}</span>
              </label>
            ))}
          </fieldset>

          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={minting}
              className="px-4 py-2 bg-gray-900 text-white text-sm rounded hover:bg-gray-700 disabled:opacity-50"
            >
              {minting ? "Generating..." : "Generate credential"}
            </button>
            <button
              type="button"
              onClick={handleConnect}
              disabled={starting}
              className="px-3 py-2 text-sm text-gray-700 border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50"
            >
              Connect another account
            </button>
          </div>

          {mintError && <p className="text-sm text-red-700">{mintError}</p>}
        </form>
      )}
    </div>
  );
};

export default GitHubConnect;
