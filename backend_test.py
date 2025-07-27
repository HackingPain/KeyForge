#!/usr/bin/env python3
"""
KeyForge Backend API Testing Suite
Tests all API endpoints for the KeyForge application
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class KeyForgeAPITester:
    def __init__(self, base_url="https://530a6f4f-114a-4972-b2c9-39f355dce381.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.created_credentials = []
        self.created_projects = []

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, data: Dict = None, files: Dict = None) -> tuple:
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if not endpoint.startswith('http') else endpoint
        headers = {'Content-Type': 'application/json'} if not files else {}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, timeout=10)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2, default=str)[:200]}...")
                except:
                    print(f"   Response: {response.text[:200]}...")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")

            return success, response.json() if response.text and response.status_code < 500 else {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_dashboard_overview(self):
        """Test dashboard overview endpoint"""
        return self.run_test("Dashboard Overview", "GET", "dashboard/overview", 200)

    def test_api_catalog(self):
        """Test API catalog endpoint"""
        return self.run_test("API Catalog", "GET", "api-catalog", 200)

    def test_create_project_analysis(self):
        """Test creating a project analysis"""
        project_data = {
            "project_name": f"test_project_{datetime.now().strftime('%H%M%S')}"
        }
        success, response = self.run_test("Create Project Analysis", "POST", "projects/analyze", 200, project_data)
        if success and 'id' in response:
            self.created_projects.append(response['id'])
        return success, response

    def test_get_project_analyses(self):
        """Test getting all project analyses"""
        return self.run_test("Get Project Analyses", "GET", "projects/analyses", 200)

    def test_file_upload(self):
        """Test file upload functionality"""
        # Create a mock Python file for testing
        mock_file_content = """
import openai
import stripe
from github import Github

openai.api_key = "sk-test-123"
stripe.api_key = "sk_test_456"
GITHUB_CLIENT_ID = "github_123"
"""
        files = {
            'files': ('test_app.py', mock_file_content, 'text/plain')
        }
        return self.run_test("File Upload Analysis", "POST", "projects/demo-project/upload-files", 200, files=files)

    def test_create_credential(self, api_name="openai", api_key="sk-test-123456"):
        """Test creating a new credential"""
        credential_data = {
            "api_name": api_name,
            "api_key": api_key,
            "environment": "development"
        }
        success, response = self.run_test(f"Create {api_name.title()} Credential", "POST", "credentials", 200, credential_data)
        if success and 'id' in response:
            self.created_credentials.append(response['id'])
        return success, response

    def test_get_credentials(self):
        """Test getting all credentials"""
        return self.run_test("Get All Credentials", "GET", "credentials", 200)

    def test_get_single_credential(self, credential_id):
        """Test getting a single credential"""
        return self.run_test("Get Single Credential", "GET", f"credentials/{credential_id}", 200)

    def test_update_credential(self, credential_id):
        """Test updating a credential"""
        update_data = {
            "api_key": "sk-updated-789",
            "environment": "staging"
        }
        return self.run_test("Update Credential", "PUT", f"credentials/{credential_id}", 200, update_data)

    def test_test_credential(self, credential_id):
        """Test the credential testing endpoint"""
        return self.run_test("Test Credential", "POST", f"credentials/{credential_id}/test", 200)

    def test_delete_credential(self, credential_id):
        """Test deleting a credential"""
        return self.run_test("Delete Credential", "DELETE", f"credentials/{credential_id}", 200)

    def cleanup(self):
        """Clean up created test data"""
        print("\n🧹 Cleaning up test data...")
        for cred_id in self.created_credentials:
            try:
                requests.delete(f"{self.api_url}/credentials/{cred_id}", timeout=5)
                print(f"   Deleted credential: {cred_id}")
            except:
                pass

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting KeyForge Backend API Tests")
        print(f"   Base URL: {self.base_url}")
        print(f"   API URL: {self.api_url}")
        
        # Basic connectivity tests
        print("\n" + "="*50)
        print("BASIC CONNECTIVITY TESTS")
        print("="*50)
        
        self.test_root_endpoint()
        self.test_dashboard_overview()
        self.test_api_catalog()

        # Project analysis tests
        print("\n" + "="*50)
        print("PROJECT ANALYSIS TESTS")
        print("="*50)
        
        self.test_create_project_analysis()
        self.test_get_project_analyses()
        self.test_file_upload()

        # Credential management tests
        print("\n" + "="*50)
        print("CREDENTIAL MANAGEMENT TESTS")
        print("="*50)
        
        # Test multiple API types
        api_types = [
            ("openai", "sk-test-openai-123"),
            ("stripe", "sk_test_stripe_456"),
            ("github", "ghp_github_789")
        ]
        
        for api_name, api_key in api_types:
            success, response = self.test_create_credential(api_name, api_key)
            if success and 'id' in response:
                cred_id = response['id']
                self.test_get_single_credential(cred_id)
                self.test_test_credential(cred_id)
                self.test_update_credential(cred_id)

        self.test_get_credentials()

        # Test dashboard after adding credentials
        print("\n" + "="*50)
        print("DASHBOARD WITH DATA TESTS")
        print("="*50)
        self.test_dashboard_overview()

        # Cleanup (delete some credentials to test delete functionality)
        if self.created_credentials:
            print("\n" + "="*50)
            print("DELETE FUNCTIONALITY TESTS")
            print("="*50)
            for cred_id in self.created_credentials[:2]:  # Delete first 2 credentials
                self.test_delete_credential(cred_id)

        # Final results
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        print(f"📊 Tests Run: {self.tests_run}")
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"📈 Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("\n🎉 All tests passed! Backend API is working correctly.")
            return 0
        else:
            print(f"\n⚠️  {self.tests_run - self.tests_passed} test(s) failed. Check the output above for details.")
            return 1

def main():
    tester = KeyForgeAPITester()
    try:
        return tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        return 1
    finally:
        tester.cleanup()

if __name__ == "__main__":
    sys.exit(main())