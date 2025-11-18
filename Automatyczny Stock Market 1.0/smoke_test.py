import requests
import os
import uuid
import time
from urllib.parse import urljoin
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from a .env file if it exists
load_dotenv()

# The base URL of the deployed application
BASE_URL = "https://ase-bot.live/"

# Use environment variables for credentials, with fallbacks for local testing
# Generate a unique username and email for each test run to ensure idempotency
UNIQUE_ID = str(uuid.uuid4())[:8]
TEST_USERNAME = os.getenv("TEST_USERNAME", f"tester-{UNIQUE_ID}")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "aSecurePassword123!")
TEST_EMAIL = os.getenv("TEST_EMAIL", f"test-{UNIQUE_ID}@example.com")

# Session object to persist cookies across requests
session = requests.Session()
AUTH_TOKEN: str | None = None

def is_json_response(response: requests.Response) -> bool:
    content_type = response.headers.get("Content-Type", "").lower()
    return "application/json" in content_type

# --- Helper Functions ---
def print_step(title):
    """Prints a formatted step title."""
    print("\n" + "="*80)
    print(f"▶️  STEP: {title}")
    print("="*80)

def print_result(success, message, data=None):
    """Prints a formatted result."""
    status = "✅ SUCCESS" if success else "❌ FAILED"
    print(f"{status}: {message}")
    if data:
        import json
        # Pretty print JSON data if available
        print(json.dumps(data, indent=2, default=str))

# --- Test Functions ---

def test_01_health_check():
    """Tests if the gateway health endpoint is responsive."""
    print_step("Health Check")
    url = urljoin(BASE_URL, "/health")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and is_json_response(response):
            body = response.json()
            if body.get("status") == "ok":
                print_result(True, f"Gateway is healthy. Status: {response.status_code}")
                return True

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Gateway health check failed. Status: {response.status_code}", snippet)
        return False
    except requests.RequestException as e:
        print_result(False, f"Could not connect to health endpoint: {e}")
        return False

def test_02_registration():
    """Registers a user using the public API."""
    print_step("User Registration")

    url = urljoin(BASE_URL, "/api/v2/users/register")
    payload = {
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }

    try:
        response = session.post(url, json=payload, timeout=20)

        if response.status_code == 201 and is_json_response(response):
            data = response.json()
            print_result(True, f"Registration successful for user '{TEST_USERNAME}'.", data)
            return True

        if response.status_code == 400 and "already" in response.text.lower():
            print_result(True, "User already registered. Continuing with existing account.")
            return True

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Registration failed. Status: {response.status_code}", snippet)
        return False
    except requests.RequestException as e:
        print_result(False, f"Error during registration request: {e}")
        return False

def test_03_login():
    """Authenticates the user and stores the bearer token."""
    global AUTH_TOKEN

    print_step("User Login")

    url = urljoin(BASE_URL, "/api/v2/users/login")
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }

    try:
        response = session.post(url, json=payload, timeout=20)
        if response.status_code == 200 and is_json_response(response):
            data = response.json()
            AUTH_TOKEN = data.get("access_token")
            if AUTH_TOKEN:
                session.headers.update({"Authorization": f"Bearer {AUTH_TOKEN}"})
                print_result(True, f"Login successful for user '{TEST_USERNAME}'.", data.get("user"))
                return True
            print_result(False, "Login response missing access token.", data)
            return False

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Login failed. Status: {response.status_code}", snippet)
        return False
    except requests.RequestException as e:
        print_result(False, f"Error during login request: {e}")
        return False

def test_04_user_profile():
    """Fetch the authenticated user's profile."""
    if not AUTH_TOKEN:
        print_result(False, "Skipping profile check: missing bearer token.")
        return False

    print_step("Fetch Current User Profile")
    url = urljoin(BASE_URL, "/api/v2/users/me")
    try:
        response = session.get(url, timeout=15)
        if response.status_code == 200 and is_json_response(response):
            data = response.json()
            if data.get("email") == TEST_EMAIL and data.get("username") == TEST_USERNAME:
                print_result(True, "User profile matches registration info.", data)
                return True
            print_result(False, "Profile fetched but does not match expected user.", data)
            return False

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Failed to fetch profile. Status: {response.status_code}", snippet)
        return False
    except (requests.RequestException, ValueError) as e:
        print_result(False, f"Error fetching user profile: {e}")
        return False


def test_05_list_trading_keys():
    """Ensure the authenticated trading keys endpoint responds."""
    if not AUTH_TOKEN:
        print_result(False, "Skipping trading keys check: missing bearer token.")
        return False

    print_step("List Trading API Keys")
    url = urljoin(BASE_URL, "/api/v2/trading/keys")
    try:
        response = session.get(url, timeout=20)
        if response.status_code == 200 and is_json_response(response):
            data = response.json()
            if isinstance(data.get("items"), list):
                print_result(True, "Trading keys endpoint reachable.", {"count": len(data["items"])})
                return True
            print_result(False, "Trading keys response missing items list.", data)
            return False

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Trading keys request failed. Status: {response.status_code}", snippet)
        return False
    except (requests.RequestException, ValueError) as e:
        print_result(False, f"Error fetching trading keys: {e}")
        return False


def test_06_list_exchanges():
    """Check the public exchanges listing endpoint."""
    print_step("List Supported Exchanges")
    url = urljoin(BASE_URL, "/api/v2/trading/exchanges")
    try:
        response = session.get(url, timeout=15)
        if response.status_code == 200 and is_json_response(response):
            data = response.json()
            exchanges = data.get("exchanges") or []
            if isinstance(exchanges, list) and exchanges:
                print_result(True, "Supported exchanges retrieved.", {"sample": exchanges[:3]})
                return True
            print_result(False, "Exchanges list empty or invalid.", data)
            return False

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Failed to fetch exchanges. Status: {response.status_code}", snippet)
        return False
    except (requests.RequestException, ValueError) as e:
        print_result(False, f"Error fetching exchanges: {e}")
        return False


def test_07_logout():
    """Logs the user out to ensure the token can be revoked."""
    if not AUTH_TOKEN:
        print_result(False, "Skipping logout: missing bearer token.")
        return False

    print_step("User Logout")
    url = urljoin(BASE_URL, "/api/v2/users/logout")
    try:
        response = session.post(url, timeout=10)
        if response.status_code == 200 and is_json_response(response):
            print_result(True, "Logout successful.", response.json())
            return True

        snippet = response.text[:500] if response.text else "<empty>"
        print_result(False, f"Logout failed. Status: {response.status_code}", snippet)
        return False
    except requests.RequestException as e:
        print_result(False, f"Error during logout request: {e}")
        return False


def run_all_tests():
    """Executes all defined tests in sequence."""
    print("="*80)
    print("🚀 STARTING APPLICATION E2E SMOKE TEST SUITE")
    print(f" targeting base URL: {BASE_URL}")
    print(f" using test user: {TEST_USERNAME}")
    print("="*80)

    results = {}
    
    results["health"] = test_01_health_check()

    if results["health"]:
        time.sleep(1)
        results["registration"] = test_02_registration()
    else:
        results["registration"] = False

    time.sleep(1)
    results["login"] = test_03_login()

    time.sleep(1)
    results["profile"] = test_04_user_profile()
    results["trading_keys"] = test_05_list_trading_keys()
    results["exchanges"] = test_06_list_exchanges()
    results["logout"] = test_07_logout()

    print("\n" + "="*80)
    print("📊 TEST SUITE SUMMARY")
    print("="*80)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"- {test_name.replace('_', ' ').title()}: {status}")
        if not passed:
            all_passed = False
            
    print("="*80)
    if all_passed:
        print("🎉 All smoke tests passed successfully!")
        return 0

    print("🔥 Some smoke tests failed. Please review the logs above.")
    return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    exit(exit_code)
