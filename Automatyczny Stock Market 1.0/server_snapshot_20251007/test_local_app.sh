#!/bin/bash
# ASE-Bot Local Testing Script
# Kompletne testowanie lokalnej aplikacji

echo "🧪 ASE-Bot Local Application Testing"
echo "===================================="
echo "Data: $(date)"
echo ""

# Kolory dla output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:6000"

# Funkcja testowania endpoint
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="$3"
    
    echo -n "Testing $name... "
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$status_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}✅ PASS${NC} (Status: $status_code)"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (Expected: $expected_status, Got: $status_code)"
        return 1
    fi
}

# Funkcja testowania JSON response
test_json_endpoint() {
    local name="$1"
    local url="$2"
    
    echo -n "Testing $name JSON... "
    response=$(curl -s "$url")
    
    if echo "$response" | python3 -m json.tool >/dev/null 2>&1; then
        echo -e "${GREEN}✅ VALID JSON${NC}"
        return 0
    else
        echo -e "${RED}❌ INVALID JSON${NC}"
        return 1
    fi
}

# Funkcja testowania CORS
test_cors() {
    local url="$1"
    
    echo -n "Testing CORS... "
    cors_header=$(curl -s -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: X-Requested-With" -X OPTIONS "$url" -I | grep -i "access-control-allow-origin")
    
    if [ ! -z "$cors_header" ]; then
        echo -e "${GREEN}✅ CORS ENABLED${NC}"
        return 0
    else
        echo -e "${RED}❌ CORS NOT FOUND${NC}"
        return 1
    fi
}

echo -e "${BLUE}🔍 Checking Server Status${NC}"
echo "================================"

if ps aux | grep "simple_test_server" | grep -v grep >/dev/null; then
    echo -e "${GREEN}✅ Server process found${NC}"
else
    echo -e "${RED}❌ Server not running${NC}"
    echo "Trying to connect to server directly..."
    if curl -s "$BASE_URL/health" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Server responds to HTTP requests${NC}"
    else
        echo -e "${RED}❌ Server not responding${NC}"
        exit 1
    fi
fi
echo ""

echo -e "${BLUE}🌐 HTTP Endpoint Tests${NC}"
echo "========================"

passed=0
failed=0

# Test podstawowych endpoint
if test_endpoint "Main Page" "$BASE_URL/" 200; then ((passed++)); else ((failed++)); fi
if test_endpoint "Health Check" "$BASE_URL/health" 200; then ((passed++)); else ((failed++)); fi
if test_endpoint "Admin Panel" "$BASE_URL/admin/" 200; then ((passed++)); else ((failed++)); fi
if test_endpoint "API Test" "$BASE_URL/api/test" 200; then ((passed++)); else ((failed++)); fi
if test_endpoint "API Portfolio" "$BASE_URL/api/portfolio" 200; then ((passed++)); else ((failed++)); fi

echo ""

echo -e "${BLUE}📊 JSON Response Tests${NC}"
echo "========================="

# Test JSON endpoints
if test_json_endpoint "Health Check" "$BASE_URL/health"; then ((passed++)); else ((failed++)); fi
if test_json_endpoint "API Test" "$BASE_URL/api/test"; then ((passed++)); else ((failed++)); fi

echo ""

echo -e "${BLUE}🔗 CORS Tests${NC}"
echo "================"

# Test CORS
if test_cors "$BASE_URL/health"; then ((passed++)); else ((failed++)); fi

echo ""

echo -e "${BLUE}📨 HTTP Methods Tests${NC}"
echo "=========================="

# Test POST
echo -n "Testing POST request... "
post_response=$(curl -s -X POST "$BASE_URL/api/orders" -d '{"test":"data"}')
if echo "$post_response" | grep -q "POST received"; then
    echo -e "${GREEN}✅ POST WORKS${NC}"
    ((passed++))
else
    echo -e "${RED}❌ POST FAILED${NC}"
    ((failed++))
fi

echo ""

echo -e "${BLUE}📁 Content Tests${NC}"
echo "=================="

# Test HTML content
echo -n "Testing HTML content... "
html_response=$(curl -s "$BASE_URL/")
if echo "$html_response" | grep -q "ASE-Bot"; then
    echo -e "${GREEN}✅ HTML CONTAINS ASE-BOT${NC}"
    ((passed++))
else
    echo -e "${RED}❌ HTML MISSING ASE-BOT${NC}"
    ((failed++))
fi

# Test Admin content
echo -n "Testing Admin content... "
admin_response=$(curl -s "$BASE_URL/admin/")
if echo "$admin_response" | grep -q "Admin Panel"; then
    echo -e "${GREEN}✅ ADMIN PANEL FOUND${NC}"
    ((passed++))
else
    echo -e "${RED}❌ ADMIN PANEL MISSING${NC}"
    ((failed++))
fi

echo ""

echo -e "${BLUE}⚡ Performance Tests${NC}"
echo "===================="

# Test response time
echo -n "Testing response time... "
response_time=$(curl -s -w "%{time_total}" -o /dev/null "$BASE_URL/health")
if (( $(echo "$response_time < 1.0" | bc -l) )); then
    echo -e "${GREEN}✅ FAST RESPONSE${NC} (${response_time}s)"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  SLOW RESPONSE${NC} (${response_time}s)"
    ((failed++))
fi

echo ""

echo -e "${BLUE}📋 Test Summary${NC}"
echo "================="
echo -e "Total Tests: $((passed + failed))"
echo -e "${GREEN}Passed: $passed${NC}"
echo -e "${RED}Failed: $failed${NC}"

if [ $failed -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}✅ ASE-Bot application is working correctly${NC}"
    echo ""
    echo -e "${BLUE}🌐 Application URLs:${NC}"
    echo "Main App: $BASE_URL/"
    echo "Admin Panel: $BASE_URL/admin/"
    echo "Health Check: $BASE_URL/health"
    echo "API Test: $BASE_URL/api/test"
    exit 0
else
    echo ""
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo -e "${YELLOW}Please check the server configuration${NC}"
    exit 1
fi
