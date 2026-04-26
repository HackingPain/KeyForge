import { useEffect, useState } from "react";

/**
 * CredentialWalkthrough renders a JSON-driven, multi-step guided flow that
 * helps a non-technical user obtain an API credential from a third-party
 * dashboard (Stripe, OpenAI, ...) and paste it into KeyForge.
 *
 * The walkthrough definition is fetched from
 * GET /api/walkthroughs/{provider} and contains an ordered list of steps,
 * a validation regex, and a list of suggested scopes. The component drives
 * the user from step 1 to the terminal "paste credential" step, validates
 * the pasted value against POST /api/walkthroughs/{provider}/validate,
 * and then saves it via the same POST /credentials endpoint the bare
 * paste-key form uses.
 *
 * Props:
 *   - api: shared axios instance (must already point at /api).
 *   - provider: the provider slug (e.g. "stripe", "openai").
 *   - onComplete(credential): invoked after a successful save so the parent
 *     can refresh its credential list and close the form.
 *   - onCancel(): invoked if the user backs out before saving.
 */
const CredentialWalkthrough = ({ api, provider, onComplete, onCancel }) => {
  const [walkthrough, setWalkthrough] = useState(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [credential, setCredential] = useState("");
  const [scope, setScope] = useState("");
  const [environment, setEnvironment] = useState("development");
  const [validateState, setValidateState] = useState({
    status: "idle",
    message: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const fetchWalkthrough = async () => {
      setLoadError("");
      setWalkthrough(null);
      setStepIndex(0);
      setCredential("");
      setValidateState({ status: "idle", message: "" });
      setSaveError("");
      try {
        const response = await api.get(`/walkthroughs/${provider}`);
        if (cancelled) return;
        setWalkthrough(response.data);
        const firstScope =
          response.data.suggested_scopes &&
          response.data.suggested_scopes.length > 0
            ? response.data.suggested_scopes[0].value
            : "";
        setScope(firstScope);
      } catch (err) {
        if (cancelled) return;
        const detail =
          err.response?.data?.detail ||
          err.message ||
          "Failed to load walkthrough.";
        setLoadError(detail);
      }
    };
    if (provider) {
      fetchWalkthrough();
    }
    return () => {
      cancelled = true;
    };
  }, [api, provider]);

  if (loadError) {
    return (
      <div className="p-4 border border-red-200 bg-red-50 rounded-lg">
        <p className="text-sm text-red-700">{loadError}</p>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="mt-3 text-sm text-red-700 underline hover:text-red-900"
          >
            Cancel
          </button>
        )}
      </div>
    );
  }

  if (!walkthrough) {
    return (
      <div className="p-4 text-sm text-gray-600">Loading walkthrough...</div>
    );
  }

  const totalSteps = walkthrough.steps.length;
  const step = walkthrough.steps[stepIndex];
  const isFirstStep = stepIndex === 0;
  const isLastStep = stepIndex === totalSteps - 1;
  const progressPct = ((stepIndex + 1) / totalSteps) * 100;

  const goNext = () => {
    if (stepIndex < totalSteps - 1) {
      setStepIndex(stepIndex + 1);
    }
  };

  const goBack = () => {
    if (stepIndex > 0) {
      setStepIndex(stepIndex - 1);
    }
  };

  const handleExternalLink = () => {
    if (step.action?.url) {
      window.open(step.action.url, "_blank", "noopener,noreferrer");
    }
    goNext();
  };

  const handleValidate = async () => {
    setValidateState({ status: "checking", message: "" });
    try {
      const response = await api.post(
        `/walkthroughs/${provider}/validate`,
        { credential }
      );
      const { valid, reason } = response.data;
      setValidateState({
        status: valid ? "valid" : "invalid",
        message: valid
          ? `Looks good. This is the right format for ${walkthrough.display_name}.`
          : reason || "That does not look like a valid credential.",
      });
    } catch (err) {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        "Validation request failed.";
      setValidateState({ status: "error", message: detail });
    }
  };

  const handleSave = async (event) => {
    if (event && event.preventDefault) {
      event.preventDefault();
    }
    setSaveError("");
    setSaving(true);
    try {
      const response = await api.post("/credentials", {
        api_name: provider,
        api_key: credential,
        environment,
      });
      if (onComplete) {
        onComplete(response.data);
      }
    } catch (err) {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        "Failed to save credential.";
      setSaveError(detail);
    } finally {
      setSaving(false);
    }
  };

  const renderActionButton = () => {
    if (!step.action) {
      return (
        <button
          type="button"
          onClick={goNext}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700"
        >
          Next
        </button>
      );
    }
    if (step.action.type === "external_link") {
      return (
        <button
          type="button"
          onClick={handleExternalLink}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700"
        >
          {step.action.label || "Open link"}
        </button>
      );
    }
    return null;
  };

  const renderPasteStep = () => {
    const validateClasses =
      validateState.status === "valid"
        ? "bg-green-50 text-green-700 border border-green-200"
        : validateState.status === "invalid" ||
          validateState.status === "error"
        ? "bg-red-50 text-red-700 border border-red-200"
        : "bg-gray-50 text-gray-700 border border-gray-200";

    const showValidateBanner =
      validateState.status === "valid" ||
      validateState.status === "invalid" ||
      validateState.status === "error";

    const canSave =
      validateState.status === "valid" && credential.length > 0 && !saving;

    return (
      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label
            htmlFor="walkthrough-credential"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            {walkthrough.credential_label}
          </label>
          <textarea
            id="walkthrough-credential"
            value={credential}
            onChange={(event) => {
              setCredential(event.target.value);
              setValidateState({ status: "idle", message: "" });
            }}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder={`Paste your ${walkthrough.display_name} credential here`}
            spellCheck={false}
            autoComplete="off"
          />
        </div>

        {walkthrough.suggested_scopes &&
          walkthrough.suggested_scopes.length > 0 && (
            <div>
              <label
                htmlFor="walkthrough-scope"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Permissions
              </label>
              <select
                id="walkthrough-scope"
                value={scope}
                onChange={(event) => setScope(event.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {walkthrough.suggested_scopes.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          )}

        <div>
          <label
            htmlFor="walkthrough-environment"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Environment
          </label>
          <select
            id="walkthrough-environment"
            value={environment}
            onChange={(event) => setEnvironment(event.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleValidate}
            disabled={!credential || validateState.status === "checking"}
            className="bg-gray-200 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-300 disabled:opacity-50"
          >
            {validateState.status === "checking" ? "Checking..." : "Validate"}
          </button>
          <button
            type="submit"
            disabled={!canSave}
            className="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save credential"}
          </button>
        </div>

        {showValidateBanner && (
          <div className={`text-sm p-3 rounded-md ${validateClasses}`}>
            {validateState.message}
          </div>
        )}

        {saveError && (
          <div className="text-sm p-3 rounded-md bg-red-50 text-red-700 border border-red-200">
            {saveError}
          </div>
        )}
      </form>
    );
  };

  const isPasteStep =
    step.action && step.action.type === "paste_credential";

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium text-gray-700">
            Step {stepIndex + 1} of {totalSteps}
          </p>
          <p className="text-sm text-gray-500">{walkthrough.display_name}</p>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className="bg-indigo-600 h-1.5 rounded-full transition-all"
            style={{ width: `${progressPct}%` }}
            data-testid="walkthrough-progress"
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 mb-1">{step.title}</h3>
      <p className="text-sm text-gray-700 mb-4 whitespace-pre-line">
        {step.description}
      </p>

      {isPasteStep ? renderPasteStep() : renderActionButton()}

      <div className="flex justify-between items-center mt-6">
        <div className="flex space-x-2">
          {!isFirstStep && (
            <button
              type="button"
              onClick={goBack}
              className="text-sm text-gray-700 hover:text-gray-900 underline"
            >
              Back
            </button>
          )}
        </div>
        <div className="flex space-x-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Cancel walkthrough
            </button>
          )}
          {!isPasteStep && !isLastStep && !step.action && (
            <button
              type="button"
              onClick={goNext}
              className="text-sm text-indigo-600 hover:text-indigo-800"
            >
              Skip
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default CredentialWalkthrough;
