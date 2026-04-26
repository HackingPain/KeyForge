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

// Mock every component so the test focuses on the sidebar.
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
jest.mock('../components/Profile', () => () => <div data-testid="profile">Profile</div>);

const BASIC_ITEMS = ['Dashboard', 'Credentials', 'Audit Log', 'MFA Setup', 'Profile'];
const ADVANCED_SAMPLE = [
  'Project Analyzer',
  'Key Rotation',
  'Credential Groups',
  'Teams',
  'KMS Manager',
  'Envelope Encryption',
  'Field Encryption',
  'Audit Integrity',
  'IP Allowlist',
  'Cost Estimation',
];

function getSidebar() {
  // The sidebar is the only <nav> in the rendered tree.
  return document.querySelector('nav');
}

function sidebarItemNames() {
  const nav = getSidebar();
  if (!nav) return [];
  // Each nav item is a <button> with an icon <span> followed by the name text.
  // We strip the icon span and keep the name only.
  return Array.from(nav.querySelectorAll('button')).map((btn) => {
    const clone = btn.cloneNode(true);
    const iconSpan = clone.querySelector('span');
    if (iconSpan) iconSpan.remove();
    return clone.textContent.trim();
  }).filter((t) => t.length > 0);
}

function mockAuthCheckSuccess() {
  api.get.mockResolvedValue({ data: { id: 'u1', username: 'tester' } });
}

describe('Sidebar Basic/Advanced filtering', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.getItem.mockReturnValue(null);
    document.documentElement.classList.remove('dark');
  });

  test('default view shows only the Basic set, no advanced items', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    const items = sidebarItemNames();

    // Every Basic item must be visible.
    for (const name of BASIC_ITEMS) {
      expect(items).toContain(name);
    }

    // No advanced items must be in the sidebar.
    for (const name of ADVANCED_SAMPLE) {
      expect(items).not.toContain(name);
    }

    // Acceptance: fewer than 8 sidebar items.
    expect(items.length).toBeLessThan(8);
    // And the count is exactly the Basic set.
    expect(items.length).toBe(BASIC_ITEMS.length);
  });

  test('clicking the advanced toggle reveals advanced items', async () => {
    mockAuthCheckSuccess();
    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    // Verify advanced items are absent first.
    expect(sidebarItemNames()).not.toContain('KMS Manager');

    const toggle = screen.getByLabelText('Show advanced features');
    await act(async () => { fireEvent.click(toggle); });

    const itemsAfter = sidebarItemNames();
    expect(itemsAfter).toContain('KMS Manager');
    expect(itemsAfter).toContain('Envelope Encryption');
    expect(itemsAfter).toContain('Teams');
    // localStorage should have been updated.
    expect(localStorage.setItem).toHaveBeenCalledWith('keyforge_advanced_enabled', 'true');
  });

  test('localStorage keyforge_advanced_enabled=true shows advanced on initial render', async () => {
    mockAuthCheckSuccess();
    localStorage.getItem.mockImplementation((key) => {
      if (key === 'keyforge_advanced_enabled') return 'true';
      return null;
    });

    await act(async () => { render(<App />); });
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument());

    const items = sidebarItemNames();
    expect(items).toContain('KMS Manager');
    expect(items).toContain('Envelope Encryption');
    expect(items).toContain('Field Encryption');
    expect(items).toContain('Audit Integrity');
    // Basic items still present.
    for (const name of BASIC_ITEMS) {
      expect(items).toContain(name);
    }
  });
});
