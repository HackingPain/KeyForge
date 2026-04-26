import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import App from '../App';
import api from '../api';

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  },
}));

jest.mock('../components/Dashboard', () => () => <div data-testid="dashboard">Dashboard</div>);
jest.mock('../components/AuthScreen', () => ({ onAuth }) => (
  <div data-testid="auth-screen">
    <button onClick={() => onAuth()}>Login</button>
  </div>
));
jest.mock('../components/CredentialManager', () => () => <div data-testid="credentials">Credentials</div>);
jest.mock('../components/ProjectAnalyzer', () => () => <div data-testid="analyzer">Analyzer</div>);
jest.mock('../components/AnalysisResults', () => () => <div data-testid="results">Results</div>);
jest.mock('../components/RotationTracker', () => () => <div data-testid="rotation">Rotation</div>);
jest.mock('../components/AuditLog', () => () => <div data-testid="audit">Audit</div>);
jest.mock('../components/TeamManager', () => () => <div data-testid="teams">Teams</div>);
jest.mock('../components/CredentialGroups', () => () => <div data-testid="groups">Groups</div>);
jest.mock('../components/SecretScanner', () => () => <div data-testid="scanner">Scanner</div>);
jest.mock('../components/ImportExport', () => () => <div data-testid="import-export">ImportExport</div>);
jest.mock('../components/WebhookManager', () => () => <div data-testid="webhooks">Webhooks</div>);
jest.mock('../components/CostEstimation', () => () => <div data-testid="costs">Costs</div>);
jest.mock('../components/HealthChecks', () => () => <div data-testid="health">Health</div>);
jest.mock('../components/MFASetup', () => () => <div data-testid="mfa">MFA</div>);
jest.mock('../components/SessionManager', () => () => <div data-testid="sessions">Sessions</div>);
jest.mock('../components/IPAllowlist', () => () => <div data-testid="ip-allowlist">IPAllowlist</div>);
jest.mock('../components/ExpirationTracker', () => () => <div data-testid="expirations">Expirations</div>);
jest.mock('../components/CredentialPermissions', () => () => <div data-testid="permissions">Permissions</div>);
jest.mock('../components/VersionHistory', () => () => <div data-testid="versions">Versions</div>);
jest.mock('../components/AutoRotation', () => () => <div data-testid="auto-rotation">AutoRotation</div>);
jest.mock('../components/BreachDetection', () => () => <div data-testid="breach-detection">BreachDetection</div>);
jest.mock('../components/UsageAnalytics', () => () => <div data-testid="usage-analytics">UsageAnalytics</div>);
jest.mock('../components/ComplianceCenter', () => () => <div data-testid="compliance">Compliance</div>);
jest.mock('../components/EnvelopeEncryption', () => () => <div data-testid="envelope">Envelope</div>);
jest.mock('../components/KMSManager', () => () => <div data-testid="kms">KMS</div>);
jest.mock('../components/AuditIntegrity', () => () => <div data-testid="audit-integrity">AuditIntegrity</div>);
jest.mock('../components/CredentialProxy', () => () => <div data-testid="proxy">Proxy</div>);
jest.mock('../components/BackupManager', () => () => <div data-testid="backups">Backups</div>);
jest.mock('../components/ExpirationPolicy', () => () => <div data-testid="exp-policy">ExpPolicy</div>);
jest.mock('../components/FieldEncryption', () => () => <div data-testid="field-encryption">FieldEnc</div>);

function mockAuthCheckSuccess() {
  api.get.mockResolvedValue({ data: { id: 'u1', username: 'tester' } });
}

function mockAuthCheckUnauthenticated() {
  api.get.mockRejectedValue({ response: { status: 401 } });
}

describe('App', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.getItem.mockReturnValue(null);
    document.documentElement.classList.remove('dark');
  });

  test('renders AuthScreen when /auth/me returns 401', async () => {
    mockAuthCheckUnauthenticated();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('auth-screen')).toBeInTheDocument());
  });

  test('renders Dashboard when /auth/me succeeds (cookie session)', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());
  });

  test('navigates from AuthScreen to Dashboard after login', async () => {
    mockAuthCheckUnauthenticated();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('auth-screen')).toBeInTheDocument());

    await act(async () => { fireEvent.click(screen.getByText('Login')); });

    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());
  });

  test('navigation works - clicking nav items changes view', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Credentials'));
    expect(screen.getByTestId('credentials')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Audit Log'));
    expect(screen.getByTestId('audit')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Dashboard'));
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();
  });

  test('logout calls /auth/logout and shows AuthScreen', async () => {
    mockAuthCheckSuccess();
    api.post.mockResolvedValue({ data: { status: 'ok' } });
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    await act(async () => { fireEvent.click(screen.getByText('Logout')); });

    await waitFor(() => expect(screen.getByTestId('auth-screen')).toBeInTheDocument());
    expect(api.post).toHaveBeenCalledWith('/auth/logout');
  });

  test('dark mode toggle works', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    const toggleButton = screen.getByTitle('Switch to dark mode');
    fireEvent.click(toggleButton);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(localStorage.setItem).toHaveBeenCalledWith('keyforge_dark_mode', true);
  });

  test('renders KeyForge header branding when authenticated', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());
    expect(screen.getByText('KeyForge')).toBeInTheDocument();
    expect(screen.getByText('Universal API Infrastructure Assistant')).toBeInTheDocument();
  });

  test('navigating to Teams view renders TeamManager', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Teams'));
    expect(screen.getByTestId('teams')).toBeInTheDocument();
  });
});
