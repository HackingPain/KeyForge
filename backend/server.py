from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import uuid
from datetime import datetime, timedelta
import re
import json
import random


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# API Detection Patterns
API_PATTERNS = {
    "openai": {
        "name": "OpenAI",
        "category": "AI/ML",
        "patterns": [
            r"import\s+openai",
            r"from\s+openai",
            r"openai\.api_key",
            r"OPENAI_API_KEY",
            r"gpt-3\.5|gpt-4",
            r"text-davinci|text-curie",
            r"OpenAI\("
        ],
        "files": [".py", ".js", ".ts", ".jsx", ".tsx"],
        "auth_type": "api_key",
        "scopes": ["completions", "chat", "embeddings", "fine-tuning"]
    },
    "stripe": {
        "name": "Stripe",
        "category": "Payments",
        "patterns": [
            r"import\s+stripe",
            r"from\s+stripe",
            r"stripe\.api_key",
            r"STRIPE_SECRET_KEY|STRIPE_PUBLISHABLE_KEY",
            r"stripe\.Customer|stripe\.PaymentIntent",
            r"sk_test_|pk_test_|sk_live_|pk_live_"
        ],
        "files": [".py", ".js", ".ts", ".jsx", ".tsx"],
        "auth_type": "api_key",
        "scopes": ["payments", "customers", "subscriptions", "webhooks"]
    },
    "github": {
        "name": "GitHub",
        "category": "Authentication",
        "patterns": [
            r"github\.com/login/oauth",
            r"GITHUB_CLIENT_ID|GITHUB_CLIENT_SECRET",
            r"github\.com/apps",
            r"octokit",
            r"@octokit/rest",
            r"github-api"
        ],
        "files": [".py", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml"],
        "auth_type": "oauth",
        "scopes": ["user", "repo", "admin:org", "notifications"]
    },
    "supabase": {
        "name": "Supabase",
        "category": "Backend",
        "patterns": [
            r"@supabase/supabase-js",
            r"createClient",
            r"SUPABASE_URL|SUPABASE_ANON_KEY",
            r"supabase\.from\("
        ],
        "files": [".js", ".ts", ".jsx", ".tsx"],
        "auth_type": "api_key",
        "scopes": ["database", "auth", "storage", "edge_functions"]
    },
    "firebase": {
        "name": "Firebase",
        "category": "Backend",
        "patterns": [
            r"firebase/app",
            r"firebase/firestore",
            r"FIREBASE_CONFIG",
            r"initializeApp",
            r"getFirestore"
        ],
        "files": [".js", ".ts", ".jsx", ".tsx"],
        "auth_type": "config",
        "scopes": ["firestore", "auth", "storage", "functions"]
    },
    "vercel": {
        "name": "Vercel",
        "category": "Deployment",
        "patterns": [
            r"vercel\.json",
            r"VERCEL_TOKEN",
            r"@vercel/node"
        ],
        "files": [".json", ".js", ".ts"],
        "auth_type": "token",
        "scopes": ["deployments", "projects", "teams"]
    }
}

# Models
class ProjectAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    detected_apis: List[Dict]
    file_count: int
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    recommendations: List[str] = []

class Credential(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    api_name: str
    api_key: str = ""
    status: str = "unknown"  # active, inactive, expired, invalid
    last_tested: Optional[datetime] = None
    environment: str = "development"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ProjectCreate(BaseModel):
    project_name: str

class CredentialCreate(BaseModel):
    api_name: str
    api_key: str
    environment: str = "development"

class CredentialUpdate(BaseModel):
    api_key: Optional[str] = None
    environment: Optional[str] = None

# Mock API validation functions
def mock_validate_credential(api_name: str, api_key: str) -> Dict:
    """Mock validation that simulates real API testing"""
    # Simulate different response scenarios
    scenarios = ["active", "invalid", "expired", "rate_limited"]
    weights = [0.7, 0.1, 0.1, 0.1]  # 70% success rate
    
    status = random.choices(scenarios, weights=weights)[0]
    
    return {
        "status": status,
        "response_time": random.randint(100, 500),
        "message": {
            "active": "Credential validated successfully",
            "invalid": "Invalid API key format or unauthorized",
            "expired": "API key has expired",
            "rate_limited": "Rate limit exceeded"
        }.get(status, "Unknown status")
    }

def analyze_code_content(content: str, filename: str) -> List[Dict]:
    """Analyze file content for API patterns"""
    detected = []
    
    for api_id, api_config in API_PATTERNS.items():
        # Check if file extension matches
        file_ext = Path(filename).suffix
        if file_ext not in api_config["files"]:
            continue
            
        matches = []
        for pattern in api_config["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                matches.append(pattern)
        
        if matches:
            confidence = min(len(matches) * 0.3, 1.0)  # Cap at 100%
            detected.append({
                "api_id": api_id,
                "name": api_config["name"],
                "category": api_config["category"],
                "auth_type": api_config["auth_type"],
                "scopes": api_config["scopes"],
                "confidence": confidence,
                "matched_patterns": matches[:3],  # Show top 3 matches
                "file": filename
            })
    
    return detected

# API Routes
@api_router.get("/")
async def root():
    return {"message": "KeyForge API Infrastructure Assistant"}

@api_router.post("/projects/analyze", response_model=ProjectAnalysis)
async def analyze_project(project: ProjectCreate):
    """Create a new project analysis"""
    # For demo, we'll create mock detected APIs
    mock_detected_apis = [
        {
            "api_id": "openai",
            "name": "OpenAI",
            "category": "AI/ML",
            "auth_type": "api_key",
            "scopes": ["completions", "chat", "embeddings"],
            "confidence": 0.9,
            "matched_patterns": ["import openai", "OPENAI_API_KEY"],
            "file": "app.py"
        },
        {
            "api_id": "stripe",
            "name": "Stripe",
            "category": "Payments",
            "auth_type": "api_key", 
            "scopes": ["payments", "customers"],
            "confidence": 0.8,
            "matched_patterns": ["import stripe", "stripe.api_key"],
            "file": "payment.py"
        }
    ]
    
    recommendations = [
        "Configure OpenAI API key for AI functionality",
        "Set up Stripe webhook endpoints for payment processing",
        "Add environment variables for production deployment",
        "Consider adding rate limiting for API calls"
    ]
    
    analysis = ProjectAnalysis(
        project_name=project.project_name,
        detected_apis=mock_detected_apis,
        file_count=15,
        recommendations=recommendations
    )
    
    # Save to database
    await db.project_analyses.insert_one(analysis.dict())
    return analysis

@api_router.get("/projects/analyses", response_model=List[ProjectAnalysis])
async def get_project_analyses():
    """Get all project analyses"""
    analyses = await db.project_analyses.find().to_list(1000)
    return [ProjectAnalysis(**analysis) for analysis in analyses]

@api_router.post("/projects/{project_id}/upload-files")
async def upload_project_files(project_id: str, files: List[UploadFile] = File(...)):
    """Upload and analyze project files"""
    detected_apis = []
    file_count = len(files)
    
    for file in files:
        try:
            content = await file.read()
            content_str = content.decode('utf-8')
            file_detected = analyze_code_content(content_str, file.filename)
            detected_apis.extend(file_detected)
        except Exception as e:
            logging.warning(f"Could not analyze {file.filename}: {str(e)}")
    
    # Remove duplicates and merge results
    unique_apis = {}
    for api in detected_apis:
        key = api["api_id"]
        if key in unique_apis:
            unique_apis[key]["confidence"] = max(unique_apis[key]["confidence"], api["confidence"])
            unique_apis[key]["matched_patterns"].extend(api["matched_patterns"])
        else:
            unique_apis[key] = api
    
    return {
        "detected_apis": list(unique_apis.values()),
        "file_count": file_count,
        "analysis_complete": True
    }

@api_router.post("/credentials", response_model=Credential)
async def create_credential(credential: CredentialCreate):
    """Add a new API credential"""
    cred_obj = Credential(**credential.dict())
    
    # Mock validate the credential
    validation_result = mock_validate_credential(credential.api_name, credential.api_key)
    cred_obj.status = validation_result["status"]
    cred_obj.last_tested = datetime.utcnow()
    
    await db.credentials.insert_one(cred_obj.dict())
    return cred_obj

@api_router.get("/credentials", response_model=List[Credential])
async def get_credentials():
    """Get all credentials"""
    credentials = await db.credentials.find().to_list(1000)
    return [Credential(**cred) for cred in credentials]

@api_router.get("/credentials/{credential_id}", response_model=Credential)
async def get_credential(credential_id: str):
    """Get a specific credential"""
    credential = await db.credentials.find_one({"id": credential_id})
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return Credential(**credential)

@api_router.put("/credentials/{credential_id}", response_model=Credential)
async def update_credential(credential_id: str, update: CredentialUpdate):
    """Update a credential"""
    credential = await db.credentials.find_one({"id": credential_id})
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    
    if "api_key" in update_data:
        # Re-validate if API key changed
        validation_result = mock_validate_credential(credential["api_name"], update_data["api_key"])
        update_data["status"] = validation_result["status"]
        update_data["last_tested"] = datetime.utcnow()
    
    await db.credentials.update_one(
        {"id": credential_id},
        {"$set": update_data}
    )
    
    updated_credential = await db.credentials.find_one({"id": credential_id})
    return Credential(**updated_credential)

@api_router.post("/credentials/{credential_id}/test")
async def test_credential(credential_id: str):
    """Test a credential against its API"""
    credential = await db.credentials.find_one({"id": credential_id})
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    validation_result = mock_validate_credential(credential["api_name"], credential["api_key"])
    
    # Update the credential with test results
    await db.credentials.update_one(
        {"id": credential_id},
        {"$set": {
            "status": validation_result["status"],
            "last_tested": datetime.utcnow()
        }}
    )
    
    return {
        "credential_id": credential_id,
        "api_name": credential["api_name"],
        "test_result": validation_result
    }

@api_router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str):
    """Delete a credential"""
    result = await db.credentials.delete_one({"id": credential_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"message": "Credential deleted successfully"}

@api_router.get("/dashboard/overview")
async def get_dashboard_overview():
    """Get dashboard overview data"""
    # Get credential stats
    credentials = await db.credentials.find().to_list(1000)
    total_credentials = len(credentials)
    
    status_counts = {}
    for cred in credentials:
        status = cred.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Get recent analyses
    recent_analyses = await db.project_analyses.find().sort("analysis_timestamp", -1).limit(5).to_list(5)
    
    # Calculate health score
    active_count = status_counts.get("active", 0)
    health_score = (active_count / max(total_credentials, 1)) * 100
    
    return {
        "total_credentials": total_credentials,
        "status_breakdown": status_counts,
        "health_score": round(health_score, 1),
        "recent_analyses": [ProjectAnalysis(**analysis) for analysis in recent_analyses],
        "recommendations": [
            "Test inactive credentials",
            "Update expired API keys", 
            "Add missing environment variables",
            "Configure webhook endpoints"
        ]
    }

@api_router.get("/api-catalog")
async def get_api_catalog():
    """Get available API catalog"""
    catalog = []
    for api_id, config in API_PATTERNS.items():
        catalog.append({
            "id": api_id,
            "name": config["name"],
            "category": config["category"],
            "auth_type": config["auth_type"],
            "available_scopes": config["scopes"],
            "description": f"{config['name']} integration for {config['category']}"
        })
    return {"apis": catalog}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()