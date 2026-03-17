import { render } from '@testing-library/react';

// Import all remaining components
import AuditLog from '../components/AuditLog';
import RotationTracker from '../components/RotationTracker';
import TeamManager from '../components/TeamManager';
import CredentialGroups from '../components/CredentialGroups';
import SecretScanner from '../components/SecretScanner';
import ImportExport from '../components/ImportExport';
import WebhookManager from '../components/WebhookManager';
import CostEstimation from '../components/CostEstimation';
import HealthChecks from '../components/HealthChecks';
import MFASetup from '../components/MFASetup';
import SessionManager from '../components/SessionManager';
import IPAllowlist from '../components/IPAllowlist';
import ExpirationTracker from '../components/ExpirationTracker';
import CredentialPermissions from '../components/CredentialPermissions';
import VersionHistory from '../components/VersionHistory';
import AutoRotation from '../components/AutoRotation';
import BreachDetection from '../components/BreachDetection';
import UsageAnalytics from '../components/UsageAnalytics';
import ComplianceCenter from '../components/ComplianceCenter';
import ProjectAnalyzer from '../components/ProjectAnalyzer';
import AnalysisResults from '../components/AnalysisResults';

const mockApi = {
  get: jest.fn().mockResolvedValue({ data: [] }),
  post: jest.fn().mockResolvedValue({ data: {} }),
  put: jest.fn().mockResolvedValue({ data: {} }),
  delete: jest.fn().mockResolvedValue({ data: {} }),
};

const mockAnalysis = {
  project_name: 'test-project',
  total_files_scanned: 10,
  apis_detected: [],
  credentials_found: [],
  recommendations: [],
};

describe('Component smoke tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Security components', () => {
    test('AuditLog renders without crashing', () => {
      render(<AuditLog api={mockApi} />);
    });

    test('SecretScanner renders without crashing', () => {
      render(<SecretScanner api={mockApi} />);
    });

    test('MFASetup renders without crashing', () => {
      render(<MFASetup api={mockApi} />);
    });

    test('SessionManager renders without crashing', () => {
      render(<SessionManager api={mockApi} />);
    });

    test('IPAllowlist renders without crashing', () => {
      render(<IPAllowlist api={mockApi} />);
    });

    test('BreachDetection renders without crashing', () => {
      render(<BreachDetection api={mockApi} />);
    });

    test('CredentialPermissions renders without crashing', () => {
      render(<CredentialPermissions api={mockApi} />);
    });
  });

  describe('Management components', () => {
    test('RotationTracker renders without crashing', () => {
      render(<RotationTracker api={mockApi} />);
    });

    test('TeamManager renders without crashing', () => {
      render(<TeamManager api={mockApi} />);
    });

    test('CredentialGroups renders without crashing', () => {
      render(<CredentialGroups api={mockApi} />);
    });

    test('HealthChecks renders without crashing', () => {
      render(<HealthChecks api={mockApi} />);
    });

    test('VersionHistory renders without crashing', () => {
      render(<VersionHistory api={mockApi} />);
    });

    test('AutoRotation renders without crashing', () => {
      render(<AutoRotation api={mockApi} />);
    });

    test('ExpirationTracker renders without crashing', () => {
      render(<ExpirationTracker api={mockApi} />);
    });
  });

  describe('Analytics components', () => {
    test('UsageAnalytics renders without crashing', () => {
      render(<UsageAnalytics api={mockApi} />);
    });

    test('ComplianceCenter renders without crashing', () => {
      render(<ComplianceCenter api={mockApi} />);
    });

    test('CostEstimation renders without crashing', () => {
      render(<CostEstimation api={mockApi} />);
    });
  });

  describe('Tools components', () => {
    test('ImportExport renders without crashing', () => {
      render(<ImportExport api={mockApi} />);
    });

    test('WebhookManager renders without crashing', () => {
      render(<WebhookManager api={mockApi} />);
    });
  });

  describe('Overview components', () => {
    test('ProjectAnalyzer renders without crashing', () => {
      render(<ProjectAnalyzer api={mockApi} onAnalysisComplete={jest.fn()} />);
    });

    test('AnalysisResults renders without crashing', () => {
      render(<AnalysisResults analysis={mockAnalysis} />);
    });
  });
});
