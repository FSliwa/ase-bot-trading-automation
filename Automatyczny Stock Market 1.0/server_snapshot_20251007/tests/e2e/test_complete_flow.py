"""End-to-end tests for complete application flow."""

import pytest
from playwright.async_api import async_playwright, Page, Browser
import asyncio
import json
from typing import Dict, Any


class E2ETestSuite:
    def __init__(self):
        self.browser: Browser = None
        self.page: Page = None
        self.base_url = "https://ase-bot.live"
        self.test_user = {
            "username": "e2etest123",
            "email": "e2etest123@example.com",
            "password": "E2ETestPassword123!"
        }

    async def setup(self):
        """Setup browser and page."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        
        # Enable request/response logging
        self.page.on("request", self.log_request)
        self.page.on("response", self.log_response)

    async def teardown(self):
        """Cleanup browser."""
        if self.browser:
            await self.browser.close()

    async def log_request(self, request):
        """Log API requests."""
        if '/api/' in request.url:
            print(f"→ {request.method} {request.url}")

    async def log_response(self, response):
        """Log API responses."""
        if '/api/' in response.url:
            print(f"← {response.status} {response.url}")

    async def test_registration_flow(self):
        """Test complete registration flow."""
        print("🧪 Testing registration flow...")
        
        # Navigate to registration
        await self.page.goto(f"{self.base_url}/register")
        await self.page.wait_for_load_state("networkidle")
        
        # Check page loaded
        assert await self.page.title() == "Rejestracja - ASE Trading Bot"
        
        # Fill registration form
        await self.page.fill('#username', self.test_user['username'])
        await self.page.fill('#email', self.test_user['email'])
        await self.page.fill('#password', self.test_user['password'])
        
        # Check password strength indicator
        strength_text = await self.page.text_content('#strengthText')
        assert strength_text in ['Silne', 'Bardzo silne']
        
        # Accept terms
        await self.page.check('#terms')
        
        # Submit form
        await self.page.click('button[type="submit"]')
        
        # Wait for success or error
        await self.page.wait_for_timeout(2000)
        
        # Should redirect to login or show success
        current_url = self.page.url
        assert '/login' in current_url or 'success' in await self.page.content()
        
        print("✅ Registration flow completed")

    async def test_login_flow(self):
        """Test complete login flow."""
        print("🧪 Testing login flow...")
        
        # Navigate to login
        await self.page.goto(f"{self.base_url}/login")
        await self.page.wait_for_load_state("networkidle")
        
        # Fill login form
        await self.page.fill('#email', self.test_user['email'])
        await self.page.fill('#password', self.test_user['password'])
        
        # Submit form
        await self.page.click('button[type="submit"]')
        
        # Wait for redirect to dashboard
        await self.page.wait_for_url(f"{self.base_url}/dashboard", timeout=10000)
        
        # Check dashboard loaded
        assert await self.page.title() == "Dashboard - ASE Trading Bot"
        
        # Check user info displayed
        user_name = await self.page.text_content('#userName')
        assert user_name == self.test_user['username']
        
        print("✅ Login flow completed")

    async def test_dashboard_functionality(self):
        """Test dashboard features and data loading."""
        print("🧪 Testing dashboard functionality...")
        
        # Should already be on dashboard from login test
        await self.page.wait_for_selector('#totalBalance')
        
        # Check balance displayed
        balance = await self.page.text_content('#totalBalance')
        assert '$' in balance
        
        # Test navigation
        await self.page.click('[data-section="trading"]')
        await self.page.wait_for_selector('#trading-section:not(.hidden)')
        
        # Check trading section visible
        trading_visible = await self.page.is_visible('#trading-section')
        assert trading_visible
        
        # Test analytics section
        await self.page.click('[data-section="analytics"]')
        await self.page.wait_for_selector('#analytics-section:not(.hidden)')
        
        print("✅ Dashboard functionality completed")

    async def test_api_integration(self):
        """Test API integration and data flow."""
        print("🧪 Testing API integration...")
        
        # Test user profile API
        response = await self.page.evaluate('''
            async () => {
                const token = localStorage.getItem('access_token');
                const response = await fetch('/api/v2/users/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                return {
                    status: response.status,
                    data: await response.json()
                };
            }
        ''')
        
        assert response['status'] == 200
        assert response['data']['email'] == self.test_user['email']
        
        print("✅ API integration completed")

    async def test_logout_flow(self):
        """Test logout functionality."""
        print("🧪 Testing logout flow...")
        
        # Click logout button
        await self.page.click('#logoutBtn')
        
        # Wait for redirect to login
        await self.page.wait_for_url(f"{self.base_url}/login", timeout=5000)
        
        # Check token removed
        token = await self.page.evaluate('localStorage.getItem("access_token")')
        assert token is None
        
        print("✅ Logout flow completed")

    async def test_accessibility(self):
        """Test accessibility features."""
        print("🧪 Testing accessibility...")
        
        await self.page.goto(f"{self.base_url}/login")
        
        # Test keyboard navigation
        await self.page.keyboard.press('Tab')
        focused_element = await self.page.evaluate('document.activeElement.tagName')
        assert focused_element in ['INPUT', 'BUTTON', 'A']
        
        # Test skip link
        skip_link = await self.page.query_selector('a[href="#main-content"]')
        assert skip_link is not None
        
        # Test ARIA labels
        form = await self.page.query_selector('form')
        aria_label = await form.get_attribute('aria-label') if form else None
        
        print("✅ Accessibility tests completed")

    async def test_performance_metrics(self):
        """Test performance metrics."""
        print("🧪 Testing performance metrics...")
        
        # Navigate and measure performance
        await self.page.goto(f"{self.base_url}/dashboard")
        
        # Get Core Web Vitals
        cwv = await self.page.evaluate('''
            new Promise((resolve) => {
                new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    const metrics = {};
                    
                    entries.forEach(entry => {
                        if (entry.name === 'LCP') {
                            metrics.lcp = entry.value;
                        }
                        if (entry.name === 'INP') {
                            metrics.inp = entry.value;
                        }
                        if (entry.name === 'CLS') {
                            metrics.cls = entry.value;
                        }
                    });
                    
                    resolve(metrics);
                }).observe({entryTypes: ['largest-contentful-paint', 'first-input', 'layout-shift']});
                
                // Fallback timeout
                setTimeout(() => resolve({}), 5000);
            })
        ''')
        
        print(f"Performance metrics: {cwv}")
        
        # Check if metrics meet targets
        if 'lcp' in cwv:
            assert cwv['lcp'] < 2500, f"LCP too slow: {cwv['lcp']}ms"
        
        print("✅ Performance tests completed")


async def run_e2e_tests():
    """Run all E2E tests."""
    suite = E2ETestSuite()
    
    try:
        await suite.setup()
        
        # Run tests in sequence
        await suite.test_registration_flow()
        await suite.test_login_flow()
        await suite.test_dashboard_functionality()
        await suite.test_api_integration()
        await suite.test_accessibility()
        await suite.test_performance_metrics()
        await suite.test_logout_flow()
        
        print("🎉 All E2E tests passed!")
        
    except Exception as e:
        print(f"❌ E2E test failed: {e}")
        raise
    finally:
        await suite.teardown()


# Coverage tracking
class CoverageTracker:
    def __init__(self):
        self.covered_routes = set()
        self.covered_api_endpoints = set()
        self.covered_functions = set()

    def track_route(self, route):
        self.covered_routes.add(route)

    def track_api(self, endpoint):
        self.covered_api_endpoints.add(endpoint)

    def track_function(self, function_name):
        self.covered_functions.add(function_name)

    def get_coverage_report(self):
        total_routes = {'/login', '/register', '/dashboard', '/', '/health'}
        total_apis = {'/api/v2/users/register', '/api/v2/users/login', '/api/v2/users/me', '/api/v2/users/logout'}
        
        route_coverage = len(self.covered_routes) / len(total_routes) * 100
        api_coverage = len(self.covered_api_endpoints) / len(total_apis) * 100
        
        return {
            'route_coverage': route_coverage,
            'api_coverage': api_coverage,
            'overall_coverage': (route_coverage + api_coverage) / 2
        }


if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
