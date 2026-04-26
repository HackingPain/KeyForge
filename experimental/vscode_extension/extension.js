// KeyForge VS Code Extension
// Manage API keys and credentials from VS Code

const vscode = require("vscode");
const http = require("http");
const https = require("https");
const path = require("path");

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Read the extension configuration.
 * @returns {{ apiUrl: string, token: string }}
 */
function getConfig() {
  const config = vscode.workspace.getConfiguration("keyforge");
  return {
    apiUrl: config.get("apiUrl", "http://localhost:8001"),
    token: config.get("token", ""),
  };
}

/**
 * Make an HTTP/HTTPS request to the KeyForge API.
 * @param {string} method - HTTP method
 * @param {string} urlPath - API path (e.g. "/api/credentials")
 * @param {object} [options] - Extra options
 * @param {string} [options.body] - Request body
 * @param {string} [options.contentType] - Content-Type header
 * @returns {Promise<{statusCode: number, headers: object, body: string}>}
 */
function apiRequest(method, urlPath, options = {}) {
  const { apiUrl, token } = getConfig();

  if (!token) {
    vscode.window.showErrorMessage(
      "KeyForge: No auth token configured. Set keyforge.token in settings."
    );
    return Promise.reject(new Error("No auth token"));
  }

  return new Promise((resolve, reject) => {
    const url = new URL(urlPath, apiUrl);
    const isHttps = url.protocol === "https:";
    const transport = isHttps ? https : http;

    const reqOptions = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname + url.search,
      method: method.toUpperCase(),
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    if (options.contentType) {
      reqOptions.headers["Content-Type"] = options.contentType;
    }

    if (options.body) {
      const bodyBuf = Buffer.from(options.body, "utf-8");
      reqOptions.headers["Content-Length"] = bodyBuf.length;
    }

    const req = transport.request(reqOptions, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf-8");
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: body,
        });
      });
    });

    req.on("error", (err) => {
      reject(err);
    });

    if (options.body) {
      req.write(options.body);
    }

    req.end();
  });
}

/**
 * Parse a JSON response body, showing an error if the status is >= 400.
 * @param {{ statusCode: number, body: string }} resp
 * @returns {any}
 */
function parseResponse(resp) {
  if (resp.statusCode >= 400) {
    let detail = resp.body;
    try {
      const parsed = JSON.parse(resp.body);
      detail = parsed.detail || resp.body;
    } catch (_) {
      // keep raw body
    }
    vscode.window.showErrorMessage(`KeyForge API error (${resp.statusCode}): ${detail}`);
    return null;
  }

  try {
    return JSON.parse(resp.body);
  } catch (_) {
    return resp.body;
  }
}

// ── Diagnostics collection for secret scanning ──────────────────────────────

let diagnosticCollection;

// ── Commands ─────────────────────────────────────────────────────────────────

/**
 * List credentials in a QuickPick.
 */
async function listCredentials() {
  try {
    const resp = await apiRequest("GET", "/api/credentials?skip=0&limit=200");
    const data = parseResponse(resp);
    if (!data) return;

    if (!Array.isArray(data) || data.length === 0) {
      vscode.window.showInformationMessage("KeyForge: No credentials found.");
      return;
    }

    const items = data.map((cred) => ({
      label: cred.api_name,
      description: `${cred.environment} | ${cred.status} | ${cred.api_key_preview}`,
      detail: `ID: ${cred.id}`,
      credentialId: cred.id,
    }));

    const selected = await vscode.window.showQuickPick(items, {
      placeHolder: "Select a credential",
      matchOnDescription: true,
    });

    if (selected) {
      vscode.window.showInformationMessage(
        `KeyForge: ${selected.label} (${selected.description})`
      );
    }
  } catch (err) {
    vscode.window.showErrorMessage(`KeyForge: ${err.message}`);
  }
}

/**
 * Pull credentials as .env file into the workspace.
 */
async function pullEnv() {
  try {
    const resp = await apiRequest("GET", "/api/export/env");

    if (resp.statusCode >= 400) {
      parseResponse(resp);
      return;
    }

    const content = resp.body;

    // Determine output path
    const workspaceFolders = vscode.workspace.workspaceFolders;
    let outputPath;

    if (workspaceFolders && workspaceFolders.length > 0) {
      outputPath = path.join(workspaceFolders[0].uri.fsPath, ".env");
    } else {
      const uri = await vscode.window.showSaveDialog({
        defaultUri: vscode.Uri.file(".env"),
        filters: { "Environment files": ["env"] },
      });
      if (!uri) return;
      outputPath = uri.fsPath;
    }

    const edit = new vscode.WorkspaceEdit();
    const fileUri = vscode.Uri.file(outputPath);

    // Write file contents
    const encoder = new TextEncoder();
    await vscode.workspace.fs.writeFile(fileUri, encoder.encode(content));

    vscode.window.showInformationMessage(`KeyForge: Credentials written to ${outputPath}`);
  } catch (err) {
    vscode.window.showErrorMessage(`KeyForge: ${err.message}`);
  }
}

/**
 * Scan the currently open file for secrets.
 */
async function scanSecrets() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("KeyForge: No file is currently open.");
    return;
  }

  const document = editor.document;
  const content = document.getText();
  const fileName = path.basename(document.fileName);

  try {
    // The scan endpoint expects a multipart file upload.
    // Build a simple multipart/form-data request.
    const boundary = "----KeyForgeBoundary" + Date.now().toString(36);
    let body = "";
    body += `--${boundary}\r\n`;
    body += `Content-Disposition: form-data; name="files"; filename="${fileName}"\r\n`;
    body += "Content-Type: text/plain\r\n\r\n";
    body += content;
    body += `\r\n--${boundary}--\r\n`;

    const resp = await apiRequest("POST", "/api/scan/secrets", {
      body: body,
      contentType: `multipart/form-data; boundary=${boundary}`,
    });

    const data = parseResponse(resp);
    if (!data) return;

    const findings = data.findings || [];

    // Clear previous diagnostics for this file
    diagnosticCollection.clear();

    if (findings.length === 0) {
      vscode.window.showInformationMessage("KeyForge: No secrets detected in this file.");
      return;
    }

    // Convert findings to diagnostics
    const diagnostics = findings.map((finding) => {
      const line = Math.max(0, (finding.line || 1) - 1);
      const range = new vscode.Range(line, 0, line, Number.MAX_SAFE_INTEGER);
      const severity =
        finding.severity === "critical"
          ? vscode.DiagnosticSeverity.Error
          : vscode.DiagnosticSeverity.Warning;

      const diagnostic = new vscode.Diagnostic(
        range,
        `${finding.type}: ${finding.suggestion || finding.matched_value || "potential secret detected"}`,
        severity
      );
      diagnostic.source = "KeyForge";
      return diagnostic;
    });

    diagnosticCollection.set(document.uri, diagnostics);

    vscode.window.showWarningMessage(
      `KeyForge: Found ${findings.length} potential secret(s) in ${fileName}.`
    );
  } catch (err) {
    vscode.window.showErrorMessage(`KeyForge: ${err.message}`);
  }
}

/**
 * Test a credential selected from a QuickPick list.
 */
async function testCredential() {
  try {
    // Fetch credentials first
    const resp = await apiRequest("GET", "/api/credentials?skip=0&limit=200");
    const data = parseResponse(resp);
    if (!data) return;

    if (!Array.isArray(data) || data.length === 0) {
      vscode.window.showInformationMessage("KeyForge: No credentials to test.");
      return;
    }

    const items = data.map((cred) => ({
      label: cred.api_name,
      description: `${cred.environment} | ${cred.status}`,
      detail: `ID: ${cred.id}`,
      credentialId: cred.id,
    }));

    const selected = await vscode.window.showQuickPick(items, {
      placeHolder: "Select a credential to test",
      matchOnDescription: true,
    });

    if (!selected) return;

    // Run the test
    vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `KeyForge: Testing ${selected.label}...`,
        cancellable: false,
      },
      async () => {
        const testResp = await apiRequest(
          "POST",
          `/api/credentials/${selected.credentialId}/test`
        );
        const testData = parseResponse(testResp);
        if (!testData) return;

        const result = testData.test_result || {};
        const status = result.status || "unknown";

        if (status === "active") {
          vscode.window.showInformationMessage(
            `KeyForge: ${selected.label} is ACTIVE and working.`
          );
        } else if (status === "expired" || status === "invalid") {
          vscode.window.showWarningMessage(
            `KeyForge: ${selected.label} is ${status.toUpperCase()}.`
          );
        } else {
          vscode.window.showInformationMessage(
            `KeyForge: ${selected.label} status: ${status}.`
          );
        }
      }
    );
  } catch (err) {
    vscode.window.showErrorMessage(`KeyForge: ${err.message}`);
  }
}

// ── Extension lifecycle ──────────────────────────────────────────────────────

/**
 * Called when the extension is activated.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  diagnosticCollection = vscode.languages.createDiagnosticCollection("keyforge");
  context.subscriptions.push(diagnosticCollection);

  context.subscriptions.push(
    vscode.commands.registerCommand("keyforge.listCredentials", listCredentials)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("keyforge.pullEnv", pullEnv)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("keyforge.scanSecrets", scanSecrets)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("keyforge.testCredential", testCredential)
  );
}

/**
 * Called when the extension is deactivated.
 */
function deactivate() {
  if (diagnosticCollection) {
    diagnosticCollection.dispose();
  }
}

module.exports = { activate, deactivate };
