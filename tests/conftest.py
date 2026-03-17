import pytest
import os

# Set test environment variables before importing backend modules
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleWZvcmtleWZvcmdlMTIzNDU2Nzg5MDEyMzQ1Ng==")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-keyforge-tests")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "keyforge_test")
