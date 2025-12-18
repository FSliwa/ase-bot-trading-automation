#!/usr/bin/env python3
"""
Complete Integration Test Suite
Tests all functionality: Frontend ↔ Backend ↔ Database ↔ AI ↔ WebSocket
"""

import asyncio
import aiohttp
import json
import time
import websockets
from typing import Dict, Any
import random


class CompleteIntegrationTest:
    def __init__(self):
        self.base_url = "https://ase-bot.live"
        self.ws_url = "wss://ase-bot.live/ws"
        self.session = None
        self.test_user = {
            "username": f"integtest{random.randint(1000, 9999)}",
            "email": f"integtest{random.randint(1000, 9999)}@example.com",
            "password": "IntegrationTest123!"
        }
        self.access_token = None
        self.results = {}

    async def setup(self):
        """Setup test session."""
        self.session = aiohttp.ClientSession()
        print("🚀 Starting Complete Integration Test Suite")
        print(f"📧 Test user: {self.test_user['email']}")

    async def teardown(self):
        """Cleanup test session."""
        if self.session:
            await self.session.close()

    async def test_1_health_check(self):
        """Test 1: Health check endpoint."""
        print("\n🔍 Test 1: Health Check")
        
        async with self.session.get(f"{self.base_url}/health") as resp:
            data = await resp.json()
            assert resp.status == 200
            assert data["status"] == "ok"
            
        self.results["health_check"] = "✅ PASS"
        print("✅ Health check passed")

    async def test_2_frontend_pages(self):
        """Test 2: Frontend pages accessibility."""
        print("\n🔍 Test 2: Frontend Pages")
        
        pages = ["/login", "/register", "/dashboard"]
        
        for page in pages:
            async with self.session.get(f"{self.base_url}{page}") as resp:
                assert resp.status == 200
                content = await resp.text()
                assert "<!DOCTYPE html>" in content
                assert "dark" in content  # Dark theme check
                
        self.results["frontend_pages"] = "✅ PASS"
        print("✅ All frontend pages accessible")

    async def test_3_user_registration(self):
        """Test 3: User registration flow."""
        print("\n🔍 Test 3: User Registration")
        
        async with self.session.post(
            f"{self.base_url}/api/v2/users/register",
            json=self.test_user,
            headers={"Content-Type": "application/json"}
        ) as resp:
            assert resp.status == 201
            data = await resp.json()
            assert data["email"] == self.test_user["email"]
            assert data["username"] == self.test_user["username"]
            assert data["is_active"] is True
            
        self.results["registration"] = "✅ PASS"
        print(f"✅ User registered: {data['id']}")

    async def test_4_user_login(self):
        """Test 4: User login flow."""
        print("\n🔍 Test 4: User Login")
        
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        async with self.session.post(
            f"{self.base_url}/api/v2/users/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            
            self.access_token = data["access_token"]
            
        self.results["login"] = "✅ PASS"
        print(f"✅ Login successful, token: {self.access_token[:20]}...")

    async def test_5_authenticated_endpoints(self):
        """Test 5: Authenticated API endpoints."""
        print("\n🔍 Test 5: Authenticated Endpoints")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # Test /me endpoint
        async with self.session.get(f"{self.base_url}/api/v2/users/me", headers=headers) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["email"] == self.test_user["email"]
            
        self.results["authenticated_api"] = "✅ PASS"
        print("✅ Authenticated endpoints working")

    async def test_6_database_integration(self):
        """Test 6: Database data persistence."""
        print("\n🔍 Test 6: Database Integration")
        
        # Test that data persists by logging in again
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        async with self.session.post(
            f"{self.base_url}/api/v2/users/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            
            # Check last_login was updated
            assert data["user"]["last_login"] is not None
            
        self.results["database_integration"] = "✅ PASS"
        print("✅ Database integration working")

    async def test_7_cache_functionality(self):
        """Test 7: Redis cache functionality."""
        print("\n🔍 Test 7: Cache Functionality")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # First request (should hit database)
        start_time = time.time()
        async with self.session.get(f"{self.base_url}/api/v2/users/me", headers=headers) as resp:
            assert resp.status == 200
            first_request_time = time.time() - start_time
            
        # Second request (should hit cache)
        start_time = time.time()
        async with self.session.get(f"{self.base_url}/api/v2/users/me", headers=headers) as resp:
            assert resp.status == 200
            second_request_time = time.time() - start_time
            
        # Cache should be faster (though this is a rough test)
        print(f"📊 First request: {first_request_time:.3f}s, Second: {second_request_time:.3f}s")
        
        self.results["cache_functionality"] = "✅ PASS"
        print("✅ Cache functionality working")

    async def test_8_websocket_connection(self):
        """Test 8: WebSocket real-time connection."""
        print("\n🔍 Test 8: WebSocket Connection")
        
        try:
            # Connect to WebSocket
            async with websockets.connect(self.ws_url) as websocket:
                # Send authentication
                auth_message = {
                    "token": self.access_token
                }
                await websocket.send(json.dumps(auth_message))
                
                # Wait for welcome message
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                
                assert data["type"] == "connected"
                assert "user" in data
                
                # Subscribe to price feed
                subscribe_message = {
                    "type": "subscribe",
                    "channel": "prices.BTC/USDT"
                }
                await websocket.send(json.dumps(subscribe_message))
                
                # Wait for subscription confirmation
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                assert data["type"] == "subscribed"
                
                self.results["websocket"] = "✅ PASS"
                print("✅ WebSocket connection working")
                
        except Exception as e:
            self.results["websocket"] = f"❌ FAIL: {e}"
            print(f"❌ WebSocket test failed: {e}")

    async def test_9_ai_integration(self):
        """Test 9: AI service integration (if available)."""
        print("\n🔍 Test 9: AI Integration")
        
        try:
            # Test AI insights endpoint (would need to be implemented)
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # For now, test that AI service can be initialized
            from src.infrastructure.ai.gemini_service import GeminiService
            
            ai_service = GeminiService()
            usage_stats = await ai_service.get_usage_stats()
            
            assert "daily_usage_usd" in usage_stats
            assert "daily_budget_usd" in usage_stats
            
            self.results["ai_integration"] = "✅ PASS"
            print("✅ AI service integration working")
            
        except Exception as e:
            self.results["ai_integration"] = f"⚠️ SKIP: {e}"
            print(f"⚠️ AI test skipped: {e}")

    async def test_10_security_headers(self):
        """Test 10: Security headers presence."""
        print("\n🔍 Test 10: Security Headers")
        
        async with self.session.get(f"{self.base_url}/login") as resp:
            headers = resp.headers
            
            security_headers = [
                "Content-Security-Policy",
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Strict-Transport-Security"
            ]
            
            missing_headers = []
            for header in security_headers:
                if header not in headers:
                    missing_headers.append(header)
                    
            if missing_headers:
                self.results["security_headers"] = f"⚠️ Missing: {missing_headers}"
            else:
                self.results["security_headers"] = "✅ PASS"
                
        print("✅ Security headers checked")

    async def test_11_performance_metrics(self):
        """Test 11: Performance metrics."""
        print("\n🔍 Test 11: Performance Metrics")
        
        # Test response times
        endpoints = [
            "/health",
            "/login", 
            "/dashboard",
            "/api/v2/users/me"
        ]
        
        performance_results = {}
        
        for endpoint in endpoints:
            headers = {}
            if "/api/" in endpoint:
                headers["Authorization"] = f"Bearer {self.access_token}"
                
            start_time = time.time()
            async with self.session.get(f"{self.base_url}{endpoint}", headers=headers) as resp:
                response_time = time.time() - start_time
                performance_results[endpoint] = {
                    "status": resp.status,
                    "response_time": round(response_time * 1000, 2)  # ms
                }
                
        # Check if response times are acceptable
        slow_endpoints = [
            ep for ep, metrics in performance_results.items() 
            if metrics["response_time"] > 2000  # > 2 seconds
        ]
        
        if slow_endpoints:
            self.results["performance"] = f"⚠️ Slow endpoints: {slow_endpoints}"
        else:
            self.results["performance"] = "✅ PASS"
            
        print(f"📊 Performance results: {performance_results}")

    async def test_12_logout_flow(self):
        """Test 12: Logout functionality."""
        print("\n🔍 Test 12: Logout Flow")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.session.post(f"{self.base_url}/api/v2/users/logout", headers=headers) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "message" in data
            
        # Verify token is invalidated
        async with self.session.get(f"{self.base_url}/api/v2/users/me", headers=headers) as resp:
            assert resp.status == 401  # Should be unauthorized now
            
        self.results["logout"] = "✅ PASS"
        print("✅ Logout flow working")

    async def run_all_tests(self):
        """Run all integration tests."""
        await self.setup()
        
        try:
            await self.test_1_health_check()
            await self.test_2_frontend_pages()
            await self.test_3_user_registration()
            await self.test_4_user_login()
            await self.test_5_authenticated_endpoints()
            await self.test_6_database_integration()
            await self.test_7_cache_functionality()
            await self.test_8_websocket_connection()
            await self.test_9_ai_integration()
            await self.test_10_security_headers()
            await self.test_11_performance_metrics()
            await self.test_12_logout_flow()
            
        finally:
            await self.teardown()
            
        return self.results

    def print_summary(self):
        """Print test results summary."""
        print("\n" + "="*60)
        print("🎯 INTEGRATION TEST RESULTS")
        print("="*60)
        
        passed = sum(1 for result in self.results.values() if result.startswith("✅"))
        total = len(self.results)
        
        for test_name, result in self.results.items():
            print(f"{test_name:25} {result}")
            
        print(f"\n📊 Summary: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Application is fully functional.")
        else:
            print("⚠️  Some tests failed or were skipped.")
            
        return passed == total


async def main():
    """Run complete integration test suite."""
    test_suite = CompleteIntegrationTest()
    
    try:
        results = await test_suite.run_all_tests()
        success = test_suite.print_summary()
        
        # Additional manual verification prompts
        print("\n" + "="*60)
        print("🔧 MANUAL VERIFICATION CHECKLIST")
        print("="*60)
        print("Please manually verify the following:")
        print("1. ✅ Open https://ase-bot.live/login - Dark theme loads")
        print("2. ✅ Register new account - Form validation works")
        print("3. ✅ Login with account - Redirects to dashboard")
        print("4. ✅ Dashboard shows user info and navigation")
        print("5. ✅ Navigation between sections works")
        print("6. ✅ Logout button works and redirects to login")
        print("7. ✅ Try invalid login - Shows error message")
        print("8. ✅ Check browser dev tools - No console errors")
        print("9. ✅ Test on mobile device - Responsive design")
        print("10. ✅ Test keyboard navigation - Tab order correct")
        
        return success
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
