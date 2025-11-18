import requests
import uuid
from datetime import datetime

BASE_URL = "http://ase-bot.live"

def generate_unique_user():
    """Generates a unique user object for testing."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "firstName": "Test",
        "lastName": f"User_{unique_id}",
        "email": f"testuser_{unique_id}@example.com",
        "phone": "+1234567890",
        "country": "US",
        "password": "Password123!",
        "confirmPassword": "Password123!",
        "terms": "on"
    }

def run_smoke_test():
    """Runs a series of tests to verify core application functionality."""
    session = requests.Session()
    user_data = generate_unique_user()
    
    print("--- Smoke Test Starting ---")
    
    # 1. Test Registration
    print(f"\n[1] Testing Registration for: {user_data['email']}")
    try:
        reg_response = session.post(f"{BASE_URL}/register", data=user_data, allow_redirects=False)
        
        # Expecting a redirect to /login on successful registration
        if reg_response.status_code == 302 and "/login" in reg_response.headers.get("Location", ""):
            print("✅ Registration Test PASSED: Successfully redirected to login.")
        else:
            print(f"❌ Registration Test FAILED: Status {reg_response.status_code}")
            print("Response Body:", reg_response.text)
            return
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Registration Test FAILED: Could not connect to the server. {e}")
        return

    # 2. Test Login
    print(f"\n[2] Testing Login for: {user_data['email']}")
    try:
        login_data = {"email": user_data["email"], "password": user_data["password"]}
        login_response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)

        # Expecting a redirect to /dashboard and a session cookie
        if login_response.status_code == 302 and "/dashboard" in login_response.headers.get("Location", ""):
            if "access_token" in session.cookies:
                print("✅ Login Test PASSED: Successfully logged in and received access token.")
            else:
                print("❌ Login Test FAILED: Redirected but no access token found in cookies.")
                return
        else:
            print(f"❌ Login Test FAILED: Status {login_response.status_code}")
            print("Response Body:", login_response.text)
            return
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Login Test FAILED: Could not connect to the server. {e}")
        return

    # 3. Test Authenticated API Endpoint
    print("\n[3] Testing Authenticated API Endpoint (/api/dashboard-data)")
    try:
        # The session object now holds the cookie from the login
        dashboard_response = session.get(f"{BASE_URL}/api/dashboard-data")
        
        if dashboard_response.status_code == 200:
            print("✅ API Test PASSED: Successfully accessed authenticated endpoint.")
            try:
                data = dashboard_response.json()
                print("   - Received valid JSON response.")
                # Simple check to see if the structure is as expected
                if "account_overview" in data and "open_positions" in data:
                    print("   - JSON structure looks correct.")
                else:
                    print("   - WARNING: JSON structure might be incorrect.")
            except ValueError:
                print("   - ❌ FAILED: Response is not valid JSON.")
        else:
            print(f"❌ API Test FAILED: Status {dashboard_response.status_code}")
            print("   - Response Body:", dashboard_response.text)
            return

    except requests.exceptions.RequestException as e:
        print(f"❌ API Test FAILED: Could not connect to the server. {e}")
        return

    print("\n--- Smoke Test Completed Successfully ---")


if __name__ == "__main__":
    print("Ensure the FastAPI application is running before executing this test.")
    run_smoke_test()
