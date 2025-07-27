import { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Dashboard Overview Component
const Dashboard = () => {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOverview();
  }, []);

  const fetchOverview = async () => {
    try {
      const response = await axios.get(`${API}/dashboard/overview`);
      setOverview(response.data);
    } catch (error) {
      console.error('Error fetching overview:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center h-64">
        <img 
          src="https://customer-assets.emergentagent.com/job_apiforge-2/artifacts/r0co6pp1_1000006696-removebg-preview.png" 
          alt="KeyForge Logo" 
          className="h-16 w-16 mb-4 animate-pulse"
        />
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        <p className="mt-2 text-sm text-gray-500">Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center">
          <div className="p-3 rounded-full bg-indigo-100 text-indigo-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-600">Total Credentials</p>
            <p className="text-2xl font-semibold text-gray-900">{overview?.total_credentials || 0}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center">
          <div className="p-3 rounded-full bg-green-100 text-green-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-600">Active APIs</p>
            <p className="text-2xl font-semibold text-gray-900">{overview?.status_breakdown?.active || 0}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center">
          <div className="p-3 rounded-full bg-blue-100 text-blue-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-600">Health Score</p>
            <p className="text-2xl font-semibold text-gray-900">{overview?.health_score || 0}%</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center">
          <div className="p-3 rounded-full bg-yellow-100 text-yellow-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-600">Issues</p>
            <p className="text-2xl font-semibold text-gray-900">{(overview?.status_breakdown?.invalid || 0) + (overview?.status_breakdown?.expired || 0)}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

// Project Analyzer Component
const ProjectAnalyzer = ({ onAnalysisComplete }) => {
  const [projectName, setProjectName] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [files, setFiles] = useState([]);

  const handleAnalyze = async () => {
    if (!projectName.trim()) return;
    
    setAnalyzing(true);
    try {
      const response = await axios.post(`${API}/projects/analyze`, {
        project_name: projectName
      });
      onAnalysisComplete(response.data);
    } catch (error) {
      console.error('Error analyzing project:', error);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleFileUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files);
    setFiles(selectedFiles);

    if (selectedFiles.length > 0 && projectName) {
      const formData = new FormData();
      selectedFiles.forEach(file => formData.append('files', file));
      
      try {
        const response = await axios.post(`${API}/projects/demo-project/upload-files`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        
        // Create analysis based on uploaded files
        const analysisResponse = await axios.post(`${API}/projects/analyze`, {
          project_name: projectName
        });
        
        // Merge uploaded file analysis with project analysis
        const mergedAnalysis = {
          ...analysisResponse.data,
          detected_apis: response.data.detected_apis || analysisResponse.data.detected_apis,
          file_count: response.data.file_count || analysisResponse.data.file_count
        };
        
        onAnalysisComplete(mergedAnalysis);
      } catch (error) {
        console.error('Error uploading files:', error);
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Project Analysis</h2>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Project Name
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Enter your project name"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Upload Project Files (Optional)
          </label>
          <input
            type="file"
            multiple
            accept=".py,.js,.ts,.jsx,.tsx,.json,.yml,.yaml"
            onChange={handleFileUpload}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {files.length > 0 && (
            <p className="text-sm text-gray-600 mt-2">{files.length} files selected</p>
          )}
        </div>

        <button
          onClick={handleAnalyze}
          disabled={!projectName.trim() || analyzing}
          className="w-full bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {analyzing ? (
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
              Analyzing Project...
            </div>
          ) : (
            'Analyze Project'
          )}
        </button>
      </div>
    </div>
  );
};

// Analysis Results Component
const AnalysisResults = ({ analysis }) => {
  if (!analysis) return null;

  const getStatusColor = (confidence) => {
    if (confidence >= 0.8) return 'bg-green-100 text-green-800';
    if (confidence >= 0.5) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Analysis Results</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Detected APIs</h3>
          <div className="space-y-3">
            {analysis.detected_apis.map((api, index) => (
              <div key={index} className="border border-gray-200 rounded-lg p-4">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="font-semibold text-gray-900">{api.name}</h4>
                    <p className="text-sm text-gray-600">{api.category}</p>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(api.confidence)}`}>
                    {Math.round(api.confidence * 100)}% confidence
                  </span>
                </div>
                <div className="text-sm text-gray-600">
                  <p><strong>Auth Type:</strong> {api.auth_type}</p>
                  <p><strong>Scopes:</strong> {api.scopes.join(', ')}</p>
                  {api.file && <p><strong>Found in:</strong> {api.file}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Recommendations</h3>
          <div className="space-y-2">
            {analysis.recommendations.map((rec, index) => (
              <div key={index} className="flex items-start">
                <div className="flex-shrink-0 w-2 h-2 mt-2 bg-indigo-600 rounded-full"></div>
                <p className="ml-3 text-sm text-gray-700">{rec}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-800 mb-2">Project Stats</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-600">Files Analyzed</p>
                <p className="font-semibold">{analysis.file_count}</p>
              </div>
              <div>
                <p className="text-gray-600">APIs Detected</p>
                <p className="font-semibold">{analysis.detected_apis.length}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Credential Manager Component
const CredentialManager = () => {
  const [credentials, setCredentials] = useState([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCredential, setNewCredential] = useState({ api_name: '', api_key: '', environment: 'development' });

  useEffect(() => {
    fetchCredentials();
  }, []);

  const fetchCredentials = async () => {
    try {
      const response = await axios.get(`${API}/credentials`);
      setCredentials(response.data);
    } catch (error) {
      console.error('Error fetching credentials:', error);
    }
  };

  const handleAddCredential = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/credentials`, newCredential);
      setNewCredential({ api_name: '', api_key: '', environment: 'development' });
      setShowAddForm(false);
      fetchCredentials();
    } catch (error) {
      console.error('Error adding credential:', error);
    }
  };

  const testCredential = async (credentialId) => {
    try {
      const response = await axios.post(`${API}/credentials/${credentialId}/test`);
      console.log('Test result:', response.data);
      fetchCredentials(); // Refresh to get updated status
    } catch (error) {
      console.error('Error testing credential:', error);
    }
  };

  const deleteCredential = async (credentialId) => {
    if (!window.confirm('Are you sure you want to delete this credential?')) return;
    
    try {
      await axios.delete(`${API}/credentials/${credentialId}`);
      fetchCredentials();
    } catch (error) {
      console.error('Error deleting credential:', error);
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      active: 'bg-green-100 text-green-800',
      invalid: 'bg-red-100 text-red-800',
      expired: 'bg-yellow-100 text-yellow-800',
      rate_limited: 'bg-orange-100 text-orange-800',
      unknown: 'bg-gray-100 text-gray-800'
    };
    return colors[status] || colors.unknown;
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Credential Management</h2>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700"
        >
          Add Credential
        </button>
      </div>

      {showAddForm && (
        <div className="mb-6 p-4 border border-gray-200 rounded-lg">
          <form onSubmit={handleAddCredential} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">API Name</label>
              <select
                value={newCredential.api_name}
                onChange={(e) => setNewCredential({...newCredential, api_name: e.target.value})}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select API</option>
                <option value="openai">OpenAI</option>
                <option value="stripe">Stripe</option>
                <option value="github">GitHub</option>
                <option value="supabase">Supabase</option>
                <option value="firebase">Firebase</option>
                <option value="vercel">Vercel</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
              <input
                type="password"
                value={newCredential.api_key}
                onChange={(e) => setNewCredential({...newCredential, api_key: e.target.value})}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Enter API key"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Environment</label>
              <select
                value={newCredential.environment}
                onChange={(e) => setNewCredential({...newCredential, environment: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="development">Development</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </div>
            <div className="flex space-x-2">
              <button
                type="submit"
                className="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700"
              >
                Add Credential
              </button>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="space-y-4">
        {credentials.map((cred) => (
          <div key={cred.id} className="border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center space-x-2 mb-2">
                  <h3 className="font-semibold text-gray-900 capitalize">{cred.api_name}</h3>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusBadge(cred.status)}`}>
                    {cred.status}
                  </span>
                  <span className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">
                    {cred.environment}
                  </span>
                </div>
                <p className="text-sm text-gray-600">
                  Last tested: {cred.last_tested ? new Date(cred.last_tested).toLocaleDateString() : 'Never'}
                </p>
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => testCredential(cred.id)}
                  className="text-indigo-600 hover:text-indigo-900 text-sm font-medium"
                >
                  Test
                </button>
                <button
                  onClick={() => deleteCredential(cred.id)}
                  className="text-red-600 hover:text-red-900 text-sm font-medium"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}

        {credentials.length === 0 && (
          <div className="text-center py-8">
            <p className="text-gray-500">No credentials added yet. Click "Add Credential" to get started.</p>
          </div>
        )}
      </div>
    </div>
  );
};

// Main App Component
function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [analysis, setAnalysis] = useState(null);

  const navigation = [
    { id: 'dashboard', name: 'Dashboard', icon: '📊' },
    { id: 'analyzer', name: 'Project Analyzer', icon: '🔍' },
    { id: 'credentials', name: 'Credentials', icon: '🔐' }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
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
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Navigation */}
        <nav className="flex space-x-8 mb-8">
          {navigation.map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                currentView === item.id
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <span className="mr-2">{item.icon}</span>
              {item.name}
            </button>
          ))}
        </nav>

        {/* Main Content */}
        <main>
          {currentView === 'dashboard' && (
            <div>
              <Dashboard />
              {analysis && <AnalysisResults analysis={analysis} />}
            </div>
          )}
          
          {currentView === 'analyzer' && (
            <div>
              <ProjectAnalyzer onAnalysisComplete={setAnalysis} />
              {analysis && <AnalysisResults analysis={analysis} />}
            </div>
          )}
          
          {currentView === 'credentials' && <CredentialManager />}
        </main>
      </div>
    </div>
  );
}

export default App;