#!/usr/bin/env python3
"""
Simple Authentication System Test
Test kompletnego systemu autentykacji ASE-Bot
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:4000"

def test_health():
    """Test health endpoint"""
    print("🔍 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"✅ Health check: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_registration():
    """Test user registration"""
    print("\n📝 Testing user registration...")
    
    # Generate unique test data
    timestamp = int(time.time())
    test_data = {
        "username": f"testuser{timestamp}",
        "email": f"test{timestamp}@example.com",
        "password": "TestPassword123!"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            headers={"Content-Type": "application/json"},
            json=test_data
        )
        
        print(f"Registration response: {response.status_code}")
        result = response.json()
        print(f"Response data: {json.dumps(result, indent=2)}")
        
        if result.get('success'):
            print("✅ Registration successful!")
            return test_data, result
        else:
            print(f"❌ Registration failed: {result.get('error')}")
            return None, None
            
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return None, None

def test_login(email, password):
    """Test user login"""
    print("\n🔑 Testing user login...")
    
    login_data = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers={"Content-Type": "application/json"},
            json=login_data
        )
        
        print(f"Login response: {response.status_code}")
        result = response.json()
        print(f"Response data: {json.dumps(result, indent=2)}")
        
        if result.get('success'):
            print("✅ Login successful!")
            return result.get('session_token')
        else:
            print(f"❌ Login failed: {result.get('error')}")
            return None
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def test_session(session_token):
    """Test session validation"""
    print("\n👤 Testing session validation...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/auth/session",
            headers={"Authorization": f"Bearer {session_token}"}
        )
        
        print(f"Session response: {response.status_code}")
        result = response.json()
        print(f"Response data: {json.dumps(result, indent=2)}")
        
        if result.get('success'):
            print("✅ Session valid!")
            return True
        else:
            print(f"❌ Session invalid: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Session error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 ASE-Bot Authentication System Test Suite")
    print("=" * 60)
    print(f"🕐 Test started at: {datetime.now()}")
    print(f"🌐 Base URL: {BASE_URL}")
    print("=" * 60)
    
    # Test 1: Health check
    if not test_health():
        print("❌ Server not accessible. Make sure it's running on port 4000")
        return
    
    # Test 2: Registration
    user_data, reg_result = test_registration()
    if not user_data:
        print("❌ Registration test failed")
        return
    
    # Test 3: Login (should fail before email verification)
    session_token = test_login(user_data['email'], user_data['password'])
    if session_token:
        print("⚠️ Login succeeded without email verification - this might be expected in test mode")
        
        # Test 4: Session validation
        test_session(session_token)
    else:
        print("ℹ️ Login failed - email verification likely required")
    
    print("\n" + "=" * 60)
    print("🏁 Test Suite Complete")
    print("=" * 60)
    print("\n📋 Manual verification steps:")
    print("1. Check for email file: ls -la email_*.html")
    print("2. Open email file to get verification link")
    print("3. Visit verification URL in browser")
    print("4. Try login again after email verification")
    print("\n🌐 Available URLs:")
    print(f"   Main App: {BASE_URL}")
    print(f"   Admin Panel: {BASE_URL}/admin/")
    print(f"   Auth Test: {BASE_URL}/auth-test")

if __name__ == "__main__":
    main()
