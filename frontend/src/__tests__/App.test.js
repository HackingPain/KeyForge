import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';

// Mock api module
jest.mock('../api', () => ({
  get: jest.fn().mockResolvedValue({ data: {} }),
  post: jest.fn().mockResolvedValue({ data: {} }),
  delete: jest.fn().mockResolvedValue({ data: {} }),
  interceptors: {
    request: { use: jest.fn() },
    response: { use: jest.fn() },
  },
}));

// Mock all child components to isolate App testing
jest.mock('../components/Dashboard', () => () => <div data-testid="dashboard">Dashboard Component</div>);
jest.mock('../components/AuthScreen', () => ({ onAuth }) => (
  <div data-testid="auth-screen">
    <button onClick={() => onAuth('test-token')}>Login</button>
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

describe('App', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.getItem.mockReturnValue(null);
    document.documentElement.classList.remove('dark');
  });

  test('renders AuthScreen when no token is stored', () => {
    localStorage.getItem.mockReturnValue(null);
    render(<App />);
    expect(screen.getByTestId('auth-screen')).toBeInTheDocument();
  });

  test('renders Dashboard when token exists in localStorage', () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();
  });

  test('navigates from AuthScreen to Dashboard after login', async () => {
    localStorage.getItem.mockReturnValue(null);
    render(<App />);
    expect(screen.getByTestId('auth-screen')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Login'));

    await waitFor(() => {
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });
    expect(localStorage.setItem).toHaveBeenCalledWith('keyforge_token', 'test-token');
  });

  test('navigation works - clicking nav items changes view', () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);

    // Click on Credentials nav item
    fireEvent.click(screen.getByText('Credentials'));
    expect(screen.getByTestId('credentials')).toBeInTheDocument();

    // Click on Audit Log nav item
    fireEvent.click(screen.getByText('Audit Log'));
    expect(screen.getByTestId('audit')).toBeInTheDocument();

    // Click back to Dashboard
    fireEvent.click(screen.getByText('Dashboard'));
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();
  });

  test('logout clears token and shows AuthScreen', async () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Logout'));

    await waitFor(() => {
      expect(screen.getByTestId('auth-screen')).toBeInTheDocument();
    });
    expect(localStorage.removeItem).toHaveBeenCalledWith('keyforge_token');
  });

  test('dark mode toggle works', () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);

    // Find the dark mode toggle button by its title
    const toggleButton = screen.getByTitle('Switch to dark mode');
    fireEvent.click(toggleButton);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(localStorage.setItem).toHaveBeenCalledWith('keyforge_dark_mode', true);
  });

  test('renders KeyForge header branding when authenticated', () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);
    expect(screen.getByText('KeyForge')).toBeInTheDocument();
    expect(screen.getByText('Universal API Infrastructure Assistant')).toBeInTheDocument();
  });

  test('navigating to Teams view renders TeamManager', () => {
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_token') return 'stored-token';
      return null;
    });
    render(<App />);

    fireEvent.click(screen.getByText('Teams'));
    expect(screen.getByTestId('teams')).toBeInTheDocument();
  });
});
