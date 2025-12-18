#!/bin/bash

# test_endpoint() {
    local url="$1"
    local expected_status="$2"
    local name="$3"
    
    echo -n "Testing $name... "
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$status" = "$expected_status" ]; then
        echo "✅ $status"
        return 0
    else
        echo "❌ Expected $expected_status, got $status"
        return 1
    fi
}

test_json_endpoint() {
    local url="$1" 
    local method="$2"
    local data="$3"
    local name="$4"
    
    echo -n "Testing $name... "
    if [ "$method" = "GET" ]; then
        status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    else
        status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" -H "Content-Type: application/json" -d "$data" "$url")
    fi
    
    if [ "$status" -ge 200 ] && [ "$status" -le 299 ]; then
        echo "✅ $status"
        return 0
    elif [ "$status" = "422" ] && [[ "$name" == *"Register"* ]]; then
        echo "✅ $status (validation works)"
        return 0
    else
        echo "❌ $status"
        return 1
    fi
}ipt for Trading Bot v2
# Tests all endpoints and functionality locally

echo "🧪 Testing Trading Bot v2 with Registration System..."

BASE_URL="http://localhost:8009"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

test_endpoint() {
    local url=$1
    local expected_code=$2
    local description=$3
    
    echo -n "Testing $description... "
    
    response_code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$response_code" = "$expected_code" ]; then
        echo -e "${GREEN}✅ PASS${NC} ($response_code)"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (got $response_code, expected $expected_code)"
        return 1
    fi
}

echo "🔍 Testing main endpoints..."

# Test main pages
test_endpoint "$BASE_URL/login" "200" "Login page"
test_endpoint "$BASE_URL/register" "200" "Registration page"
test_endpoint "$BASE_URL/" "302" "Main page (should redirect to login)"

echo ""
echo "�️ Testing database connectivity..."

# Test if PostgreSQL is available  
if command -v psql >/dev/null 2>&1; then
    echo -n "Testing PostgreSQL connection... "
    if psql -U trading_bot_user -d trading_bot -c "SELECT 1;" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL available${NC}"
        DB_TYPE="PostgreSQL"
    else
        echo -e "${YELLOW}⚠️ PostgreSQL not accessible, using JSON fallback${NC}"
        DB_TYPE="JSON"
    fi
else
    echo -e "${YELLOW}⚠️ PostgreSQL not installed, using JSON fallback${NC}"
    DB_TYPE="JSON"
fi

echo "Database backend: $DB_TYPE"

# Test API endpoints (should return 401 without auth)
test_endpoint "$BASE_URL/api/status" "401" "API Status (unauthorized)"
test_endpoint "$BASE_URL/api/account" "401" "API Account (unauthorized)"

echo ""
echo "📊 Testing registration API..."

# Test registration endpoint
registration_response=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d '{"username":"testuser","password":"testpassword123","email":"test@example.com","first_name":"Test","last_name":"User"}' \
    -w "%{http_code}")

response_code="${registration_response: -3}"
response_body="${registration_response%???}"

echo -n "Testing user registration... "
if [ "$response_code" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC} (Registration successful)"
else
    echo -e "${RED}❌ FAIL${NC} (Response: $response_code)"
    echo "Response body: $response_body"
fi

echo ""
echo "🔐 Testing login API..."

# Test login endpoint
login_response=$(curl -s -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"password"}' \
    -w "%{http_code}")

response_code="${login_response: -3}"
response_body="${login_response%???}"

echo -n "Testing admin login... "
if [ "$response_code" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC} (Login successful)"
    
    # Extract token for authenticated requests
    token=$(echo "$response_body" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
    
    if [ ! -z "$token" ]; then
        echo "🎟️  Authentication token received"
        
        # Test authenticated endpoints
        echo ""
        echo "🔓 Testing authenticated endpoints..."
        
        auth_test_endpoint() {
            local url=$1
            local description=$2
            
            echo -n "Testing $description... "
            
            response_code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $token" "$url")
            
            if [ "$response_code" = "200" ]; then
                echo -e "${GREEN}✅ PASS${NC} ($response_code)"
                return 0
            else
                echo -e "${RED}❌ FAIL${NC} (got $response_code)"
                return 1
            fi
        }
        
        auth_test_endpoint "$BASE_URL/api/status" "API Status (authenticated)"
        auth_test_endpoint "$BASE_URL/api/account" "API Account (authenticated)"
        auth_test_endpoint "$BASE_URL/" "Main dashboard (authenticated)"
    fi
else
    echo -e "${RED}❌ FAIL${NC} (Response: $response_code)"
    echo "Response body: $response_body"
fi

echo ""
echo "🗄️ Testing user database..."

# Test user database directly
echo -n "Testing user database functionality... "
db_test=$(python3 -c "
from user_database import UserDatabase
db = UserDatabase()
stats = db.get_user_stats()
print(f'Users: {stats[\"total_users\"]}, Active: {stats[\"active_users\"]}')
" 2>/dev/null)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC} ($db_test)"
else
    echo -e "${RED}❌ FAIL${NC} (Database error)"
fi

echo ""
echo "📋 Test Summary:"
echo "═══════════════════════════════════════"
echo "🌐 Server URL: $BASE_URL"
echo "🔐 Admin Login: admin / password"
echo "📝 Registration: Available at /register"
echo "🗄️ User Database: users.json"
echo ""

# Check if server is running
if pgrep -f "enhanced_server_gpt5.py" > /dev/null; then
    echo -e "🟢 Server Status: ${GREEN}RUNNING${NC}"
else
    echo -e "🔴 Server Status: ${RED}NOT RUNNING${NC}"
    echo "Start server with: python3 enhanced_server_gpt5.py"
fi

echo ""
echo "🎉 Testing completed!"
