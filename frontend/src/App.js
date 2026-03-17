import { useState, useEffect } from "react";
import "./App.css";
import api from "./api";
import Dashboard from "./components/Dashboard";
import ProjectAnalyzer from "./components/ProjectAnalyzer";
import AnalysisResults from "./components/AnalysisResults";
import CredentialManager from "./components/CredentialManager";
import AuthScreen from "./components/AuthScreen";
import RotationTracker from "./components/RotationTracker";
import AuditLog from "./components/AuditLog";
import TeamManager from "./components/TeamManager";
import CredentialGroups from "./components/CredentialGroups";
import SecretScanner from "./components/SecretScanner";
import ImportExport from "./components/ImportExport";
import WebhookManager from "./components/WebhookManager";
import CostEstimation from "./components/CostEstimation";
import HealthChecks from "./components/HealthChecks";

function App() {
  const [token, setToken] = useState(null);
  const [currentView, setCurrentView] = useState('dashboard');
  const [analysis, setAnalysis] = useState(null);
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const storedToken = localStorage.getItem('keyforge_token');
    if (storedToken) setToken(storedToken);
    const storedDark = localStorage.getItem('keyforge_dark_mode');
    if (storedDark === 'true') setDarkMode(true);
  }, []);

  useEffect(() => {
    localStorage.setItem('keyforge_dark_mode', darkMode);
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  const handleAuth = (newToken) => {
    localStorage.setItem('keyforge_token', newToken);
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('keyforge_token');
    setToken(null);
  };

  if (!token) {
    return <AuthScreen api={api} onAuth={handleAuth} />;
  }

  const navGroups = [
    {
      label: 'Overview',
      items: [
        { id: 'dashboard', name: 'Dashboard', icon: '\uD83D\uDCCA' },
        { id: 'analyzer', name: 'Project Analyzer', icon: '\uD83D\uDD0D' },
        { id: 'credentials', name: 'Credentials', icon: '\uD83D\uDD10' },
      ],
    },
    {
      label: 'Management',
      items: [
        { id: 'rotation', name: 'Key Rotation', icon: '\uD83D\uDD04' },
        { id: 'groups', name: 'Credential Groups', icon: '\uD83D\uDCC1' },
        { id: 'teams', name: 'Teams', icon: '\uD83D\uDC65' },
        { id: 'health', name: 'Health Checks', icon: '\uD83C\uDFE5' },
      ],
    },
    {
      label: 'Security',
      items: [
        { id: 'scanner', name: 'Secret Scanner', icon: '\uD83D\uDEE1\uFE0F' },
        { id: 'audit', name: 'Audit Log', icon: '\uD83D\uDCDD' },
      ],
    },
    {
      label: 'Tools',
      items: [
        { id: 'import-export', name: 'Import / Export', icon: '\uD83D\uDCE6' },
        { id: 'webhooks', name: 'Webhooks', icon: '\uD83D\uDD14' },
        { id: 'costs', name: 'Cost Estimation', icon: '\uD83D\uDCB0' },
      ],
    },
  ];

  return (
    <div className={`min-h-screen bg-gray-50 ${darkMode ? 'dark' : ''}`}>
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <img
                src="https://customer-assets.emergentagent.com/job_apiforge-2/artifacts/r0co6pp1_1000006696-removebg-preview.png"
                alt="KeyForge Logo"
                className="h-10 w-10 mr-3"
              />
              <div>
                <h1 className="text-2xl font-bold text-indigo-600">KeyForge</h1>
                <p className="text-xs text-gray-500 -mt-1">Universal API Infrastructure Assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setDarkMode(!darkMode)}
                className="p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 focus:outline-none"
                title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                {darkMode ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                )}
              </button>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-500 hover:text-gray-700 font-medium px-3 py-1.5 rounded-md hover:bg-gray-100"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex gap-6">
          {/* Sidebar Navigation */}
          <nav className="w-56 flex-shrink-0">
            {navGroups.map((group) => (
              <div key={group.label} className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-wider mb-2 px-3 text-gray-400">
                  {group.label}
                </p>
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setCurrentView(item.id)}
                    className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium mb-0.5 ${
                      currentView === item.id
                        ? 'bg-indigo-100 text-indigo-700'
                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                    }`}
                  >
                    <span className="mr-2 text-base">{item.icon}</span>
                    {item.name}
                  </button>
                ))}
              </div>
            ))}
          </nav>

          {/* Main Content */}
          <main className="flex-1 min-w-0">
            {currentView === 'dashboard' && (
              <div>
                <Dashboard api={api} />
                {analysis && <AnalysisResults analysis={analysis} />}
              </div>
            )}
            {currentView === 'analyzer' && (
              <div>
                <ProjectAnalyzer api={api} onAnalysisComplete={setAnalysis} />
                {analysis && <AnalysisResults analysis={analysis} />}
              </div>
            )}
            {currentView === 'credentials' && <CredentialManager api={api} />}
            {currentView === 'rotation' && <RotationTracker api={api} />}
            {currentView === 'groups' && <CredentialGroups api={api} />}
            {currentView === 'teams' && <TeamManager api={api} />}
            {currentView === 'health' && <HealthChecks api={api} />}
            {currentView === 'scanner' && <SecretScanner api={api} />}
            {currentView === 'audit' && <AuditLog api={api} />}
            {currentView === 'import-export' && <ImportExport api={api} />}
            {currentView === 'webhooks' && <WebhookManager api={api} />}
            {currentView === 'costs' && <CostEstimation api={api} />}
          </main>
        </div>
      </div>
    </div>
  );
}

export default App;
