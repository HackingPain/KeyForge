# KeyForge - Universal API Infrastructure Assistant

<div align="center">
  <img src="https://customer-assets.emergentagent.com/job_apiforge-2/artifacts/r0co6pp1_1000006696-removebg-preview.png" alt="KeyForge Logo" width="100" height="100">
  
  **A powerful tool for discovering, managing, and monitoring API integrations across your development projects**
  
  [![React](https://img.shields.io/badge/React-19.0.0-blue?logo=react)](https://reactjs.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110.1-green?logo=fastapi)](https://fastapi.tiangolo.com/)
  [![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green?logo=mongodb)](https://www.mongodb.com/)
  [![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org/)
</div>

## 🚀 Overview

KeyForge is an intelligent API infrastructure assistant that helps developers discover, manage, and monitor API integrations across their projects. It automatically scans codebases to detect API usage patterns, manages API credentials securely, and provides real-time insights into your API ecosystem's health.

### ✨ Key Features

- 🔍 **Smart API Detection** - Automatically discover API integrations in your codebase using advanced pattern matching
- 🔐 **Secure Credential Management** - Store and manage API keys across multiple environments
- 📊 **Real-time Dashboard** - Monitor API health, credential status, and system metrics
- 📁 **Project Analysis** - Upload and analyze project files to identify API dependencies
- 🧪 **Credential Testing** - Validate API keys and monitor their status
- 🌍 **Multi-Environment Support** - Manage credentials for development, staging, and production

### 🎯 Supported API Providers

- **AI/ML**: OpenAI, GPT models
- **Payments**: Stripe
- **Authentication**: GitHub OAuth
- **Backend Services**: Supabase, Firebase
- **Deployment**: Vercel
- **And many more...**

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [API Documentation](#api-documentation)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 16+
- MongoDB
- Yarn package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repository>
   cd keyforge
   ```

2. **Backend Setup**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd frontend
   yarn install
   ```

4. **Environment Configuration**
   
   Backend (`.env` in `/backend`):
   ```env
   MONGO_URL="mongodb://localhost:27017"
   DB_NAME="keyforge_database"
   ```
   
   Frontend (`.env` in `/frontend`):
   ```env
   REACT_APP_BACKEND_URL=http://localhost:8001
   ```

5. **Start Services**
   ```bash
   # Using supervisor (recommended)
   sudo supervisorctl start all
   
   # Or manually
   # Terminal 1: Backend
   cd backend && uvicorn server:app --host 0.0.0.0 --port 8001
   
   # Terminal 2: Frontend  
   cd frontend && yarn start
   ```

6. **Access the Application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8001/docs

## 📖 Usage Guide

### 1. Dashboard Overview

The main dashboard provides:
- **Total Credentials**: Number of stored API keys
- **Active APIs**: Currently working integrations
- **Health Score**: Overall system health percentage
- **Issues**: Count of invalid or expired credentials

### 2. Project Analysis

**Analyze Your Codebase:**
1. Navigate to "Project Analyzer" tab
2. Enter your project name
3. (Optional) Upload project files (.py, .js, .ts, etc.)
4. Click "Analyze Project"

**What Gets Detected:**
- Import statements and API calls
- Environment variable patterns
- Authentication configurations
- Framework-specific patterns

### 3. Credential Management

**Adding Credentials:**
1. Go to "Credentials" tab
2. Click "Add Credential"
3. Select API provider
4. Enter API key
5. Choose environment (dev/staging/prod)

**Testing Credentials:**
- Click "Test" next to any credential
- System validates the key and updates status
- Status indicators: Active, Invalid, Expired, Rate Limited

### 4. API Integration Patterns

KeyForge detects these patterns in your code:

**OpenAI:**
```python
import openai
openai.api_key = "sk-..."
OPENAI_API_KEY = "..."
```

**Stripe:**
```python
import stripe
stripe.api_key = "sk_test_..."
stripe.Customer.create(...)
```

**GitHub:**
```javascript
const { Octokit } = require("@octokit/rest");
GITHUB_CLIENT_ID = "..."
```

## 🔧 API Documentation

### Authentication
All API endpoints are prefixed with `/api` and currently don't require authentication.

### Core Endpoints

#### Projects
```http
POST /api/projects/analyze
Content-Type: application/json

{
  "project_name": "my-awesome-project"
}
```

#### Credentials
```http
GET /api/credentials
POST /api/credentials
PUT /api/credentials/{id}
DELETE /api/credentials/{id}
POST /api/credentials/{id}/test
```

#### Dashboard
```http
GET /api/dashboard/overview
```

#### File Upload
```http
POST /api/projects/{project_id}/upload-files
Content-Type: multipart/form-data
```

### Response Examples

**Project Analysis Response:**
```json
{
  "id": "uuid",
  "project_name": "my-project",
  "detected_apis": [
    {
      "api_id": "openai",
      "name": "OpenAI",
      "category": "AI/ML",
      "confidence": 0.9,
      "matched_patterns": ["import openai", "OPENAI_API_KEY"]
    }
  ],
  "file_count": 15,
  "recommendations": [
    "Configure OpenAI API key for AI functionality"
  ]
}
```

## 🏗️ Architecture

### System Architecture
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Frontend  │    │   Backend   │    │  MongoDB    │
│  (React)    │◄──►│  (FastAPI)  │◄──►│ (Database)  │
│ Port: 3000  │    │ Port: 8001  │    │ Port: 27017 │
└─────────────┘    └─────────────┘    └─────────────┘
```

### Directory Structure
```
keyforge/
├── backend/                 # FastAPI backend application
│   ├── server.py           # Main FastAPI application
│   ├── requirements.txt    # Python dependencies
│   └── .env               # Backend environment variables
├── frontend/               # React frontend application
│   ├── src/
│   │   ├── App.js         # Main React component
│   │   └── ...
│   ├── package.json       # Node.js dependencies
│   └── .env              # Frontend environment variables
├── tests/                 # Test files
└── README.md             # This file
```

### Data Models

**Project Analysis:**
```python
class ProjectAnalysis(BaseModel):
    id: str
    project_name: str
    detected_apis: List[Dict]
    file_count: int
    analysis_timestamp: datetime
    recommendations: List[str]
```

**Credential:**
```python
class Credential(BaseModel):
    id: str
    api_name: str
    api_key: str
    status: str  # active, inactive, expired, invalid
    environment: str  # development, staging, production
    last_tested: Optional[datetime]
```

## 🛠️ Development

### Code Organization

**Backend (`/backend`):**
- `server.py` - Main FastAPI application with all endpoints
- Pattern-based API detection using regex
- MongoDB integration with Motor (async driver)
- CORS middleware for frontend communication

**Frontend (`/frontend`):**
- React functional components with hooks
- Tailwind CSS for styling
- Axios for API communication
- Component-based architecture

### Development Guidelines

1. **Adding New API Providers:**
   ```python
   # Add to API_PATTERNS in server.py
   "new_api": {
       "name": "New API",
       "category": "Category",
       "patterns": [r"import new_api", r"NEW_API_KEY"],
       "files": [".py", ".js"],
       "auth_type": "api_key",
       "scopes": ["read", "write"]
   }
   ```

2. **Frontend Components:**
   - Follow React functional component pattern
   - Use Tailwind for consistent styling
   - Implement proper error handling
   - Add loading states for better UX

3. **API Endpoints:**
   - Use FastAPI's automatic validation
   - Include proper error responses
   - Follow RESTful conventions
   - Document with OpenAPI/Swagger

### Testing

**Backend Testing:**
```bash
cd backend
pytest
```

**Manual Testing:**
- Use FastAPI's automatic Swagger UI at `/docs`
- Test credential validation flows
- Verify file upload functionality

## 🔄 Service Management

KeyForge uses supervisor for process management:

```bash
# Check service status
sudo supervisorctl status

# Restart services
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl restart all
```

## 🐛 Troubleshooting

### Common Issues

1. **Services not starting:**
   ```bash
   # Check logs
   tail -n 50 /var/log/supervisor/backend.err.log
   tail -n 50 /var/log/supervisor/frontend.err.log
   ```

2. **Database connection issues:**
   - Ensure MongoDB is running
   - Check MONGO_URL in backend/.env
   - Verify database permissions

3. **Frontend API calls failing:**
   - Confirm REACT_APP_BACKEND_URL is correct
   - Check CORS configuration
   - Verify backend is running on correct port

### Environment Variables

Ensure all required environment variables are set:
- Backend: `MONGO_URL`, `DB_NAME`
- Frontend: `REACT_APP_BACKEND_URL`

## 🚀 Deployment

### Production Considerations

1. **Security:**
   - Use environment variables for sensitive data
   - Implement proper authentication
   - Enable HTTPS
   - Secure MongoDB connection

2. **Performance:**
   - Set up MongoDB indexing
   - Implement caching for frequent queries
   - Optimize bundle size
   - Use CDN for static assets

3. **Monitoring:**
   - Add health check endpoints
   - Implement logging
   - Monitor credential validation rates
   - Set up alerts for failures

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup
```bash
# Install development dependencies
cd backend && pip install -r requirements.txt
cd frontend && yarn install

# Run in development mode
sudo supervisorctl restart all
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation**: Check this README and API docs at `/docs`
- **Issues**: Create an issue in the repository
- **Feature Requests**: Open a feature request with detailed description

---

<div align="center">
  <strong>Built with ❤️ by the KeyForge Team</strong>
  <br>
  <em>Making API management simple and intelligent</em>
</div>
