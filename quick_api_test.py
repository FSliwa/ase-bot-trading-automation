#!/usr/bin/env python3
"""
🚀 QUICK API TEST
Tests critical API endpoints to ensure they're working
"""

import requests
import time
import json
import asyncio
from typing import Dict, Any

def test_server_running(port: int = 8010) -> bool:
    """Test if server is running"""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def test_endpoints(base_url: str = "http://localhost:8010") -> Dict[str, Any]:
    """Test critical endpoints"""
    
    endpoints = [
        ("/health", "Health Check"),
        ("/api/demo/balance", "Demo Balance"),
        ("/api/exchanges/supported", "Supported Exchanges"),
        ("/", "Root Page")
    ]
    
    results = {}
    
    for endpoint, description in endpoints:
        try:
            print(f"Testing {description}: {endpoint}")
            response = requests.get(f"{base_url}{endpoint}", timeout=10)
            
            results[endpoint] = {
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "response_size": len(response.content),
                "content_type": response.headers.get("content-type", "unknown")
            }
            
            if response.status_code == 200:
                print(f"  ✅ Success: {response.status_code}")
            else:
                print(f"  ❌ Failed: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[endpoint] = {
                "success": False,
                "error": str(e)
            }
    
    return results

def test_demo_functionality():
    """Test demo trading functionality"""
    print("\n🎭 Testing Demo Functionality:")
    
    base_url = "http://localhost:8010"
    
    # Test demo connection
    try:
        response = requests.post(f"{base_url}/api/connect-demo")
        if response.status_code == 200:
            print("  ✅ Demo connection works")
            return True
        else:
            print(f"  ❌ Demo connection failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Demo connection error: {e}")
        return False

def main():
    print("🚀 QUICK API TEST")
    print("="*50)
    
    # Test if server is running
    if not test_server_running():
        print("❌ Server is not running!")
        print("\nTo start the server, run:")
        print("python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8010")
        return False
    
    print("✅ Server is running!")
    
    # Test endpoints
    results = test_endpoints()
    
    # Test demo functionality
    demo_works = test_demo_functionality()
    
    # Summary
    print("\n📊 SUMMARY:")
    successful_endpoints = sum(1 for r in results.values() if isinstance(r, dict) and r.get("success", False))
    total_endpoints = len(results)
    
    print(f"API Endpoints: {successful_endpoints}/{total_endpoints} working")
    print(f"Demo Mode: {'✅ Working' if demo_works else '❌ Failed'}")
    
    if successful_endpoints == total_endpoints and demo_works:
        print("\n🎉 ALL TESTS PASSED - Ready for deployment!")
        return True
    else:
        print(f"\n⚠️  Some tests failed. Check the server logs.")
        return False

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
        exit(1)
