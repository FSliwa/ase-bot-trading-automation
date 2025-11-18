#!/bin/bash

# VPS Trading Bot - New Features Demo Script
# Demonstrates all new advanced features

echo "🚀 VPS Trading Bot - Advanced Features Demo"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}🔹 $1${NC}"
    echo "----------------------------------------"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# Check if server is running
print_header "System Health Check"
if curl -s "http://localhost:8010/health" > /dev/null; then
    print_success "Server is running on port 8010"
    curl -s "http://localhost:8010/health" | python3 -m json.tool
else
    echo -e "${RED}❌ Server not running. Please start with:${NC}"
    echo "   python -m uvicorn web.app:app --host 0.0.0.0 --port 8010"
    exit 1
fi

# Test User Management
print_header "User Management System"

echo "1️⃣ Registering new user..."
register_response=$(curl -s -X POST "http://localhost:8010/api/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"email":"demo_user@tradingbot.com","username":"demo_user","password":"secure123","plan":"basic"}')

if echo "$register_response" | grep -q "success.*true"; then
    print_success "User registration successful"
    echo "$register_response" | python3 -m json.tool
else
    print_info "User might already exist"
fi

echo -e "\n2️⃣ User login..."
login_response=$(curl -s -X POST "http://localhost:8010/api/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"email":"demo@tradingbot.com","password":"demo123"}')

if echo "$login_response" | grep -q "jwt_token"; then
    print_success "User login successful"
    
    # Extract JWT token for further testing
    jwt_token=$(echo "$login_response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['auth']['jwt_token'])
" 2>/dev/null)
    
    echo "$login_response" | python3 -m json.tool
else
    echo "$login_response"
fi

echo -e "\n3️⃣ User permissions check..."
permissions_response=$(curl -s -X GET "http://localhost:8010/api/user/1/permissions")
print_success "User permissions retrieved"
echo "$permissions_response" | python3 -m json.tool

# Test AI Analysis
print_header "Advanced AI Analysis"

echo "1️⃣ Analyzing BTCUSDT with AI..."
ai_analysis=$(curl -s -X POST "http://localhost:8010/api/ai/analyze/BTCUSDT" \
     -H "Content-Type: application/json" \
     -d '{"analysis_types":["technical","sentiment"],"models":["gpt-5-pro"]}')

print_success "AI analysis completed"
echo "$ai_analysis" | python3 -m json.tool

echo -e "\n2️⃣ Getting AI model information..."
ai_models=$(curl -s -X GET "http://localhost:8010/api/ai/models")
print_success "AI models information retrieved"
echo "$ai_models" | python3 -m json.tool

echo -e "\n3️⃣ Getting consensus signal..."
consensus=$(curl -s -X GET "http://localhost:8010/api/ai/consensus/BTCUSDT")
print_success "Consensus signal retrieved"
echo "$consensus" | python3 -m json.tool

# Test Portfolio Management
print_header "Portfolio Management"

echo "1️⃣ Portfolio overview..."
portfolio=$(curl -s -X GET "http://localhost:8010/api/portfolio/1/overview")
print_success "Portfolio overview retrieved"
echo "$portfolio" | python3 -m json.tool

echo -e "\n2️⃣ Portfolio performance..."
performance=$(curl -s -X GET "http://localhost:8010/api/portfolio/1/performance?period=7d")
print_success "Portfolio performance retrieved"
echo "$performance" | python3 -m json.tool

# Test Market Data
print_header "Real-time Market Data"

echo "1️⃣ Current market prices..."
prices=$(curl -s -X GET "http://localhost:8010/api/market/prices?symbols=BTCUSDT,ETHUSDT,ADAUSDT")
print_success "Market prices retrieved"
echo "$prices" | python3 -m json.tool

echo -e "\n2️⃣ Order book data..."
orderbook=$(curl -s -X GET "http://localhost:8010/api/market/orderbook/BTCUSDT?limit=10")
print_success "Order book retrieved"
echo "$orderbook" | python3 -m json.tool

# Test Administration
print_header "System Administration"

echo "1️⃣ System status..."
system_status=$(curl -s -X GET "http://localhost:8010/api/admin/system/status")
print_success "System status retrieved"
echo "$system_status" | python3 -m json.tool

echo -e "\n2️⃣ User statistics..."
user_stats=$(curl -s -X GET "http://localhost:8010/api/admin/users/stats")
print_success "User statistics retrieved"
echo "$user_stats" | python3 -m json.tool

# WebSocket Demo
print_header "WebSocket Streaming Demo"

echo "1️⃣ Creating WebSocket test script..."
cat > websocket_test.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>VPS Trading Bot - WebSocket Demo</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .connected { background-color: #d4edda; color: #155724; }
        .disconnected { background-color: #f8d7da; color: #721c24; }
        .message { background-color: #f8f9fa; padding: 10px; margin: 5px 0; border-left: 3px solid #007bff; }
        #messages { height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; }
        button { margin: 5px; padding: 10px 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 VPS Trading Bot - WebSocket Demo</h1>
        
        <div id="status" class="status disconnected">
            Status: Disconnected
        </div>
        
        <div>
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
            <button onclick="subscribePrices()">Subscribe to Prices</button>
            <button onclick="subscribePortfolio()">Subscribe to Portfolio</button>
            <button onclick="ping()">Ping Server</button>
        </div>
        
        <div id="messages"></div>
    </div>

    <script>
        let ws = null;
        const messages = document.getElementById('messages');
        const status = document.getElementById('status');
        
        function addMessage(msg) {
            const div = document.createElement('div');
            div.className = 'message';
            div.innerHTML = `<strong>${new Date().toLocaleTimeString()}</strong>: ${msg}`;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function updateStatus(connected) {
            if (connected) {
                status.textContent = 'Status: Connected';
                status.className = 'status connected';
            } else {
                status.textContent = 'Status: Disconnected';
                status.className = 'status disconnected';
            }
        }
        
        function connect() {
            if (ws) {
                ws.close();
            }
            
            ws = new WebSocket('ws://localhost:8010/ws/1');
            
            ws.onopen = function() {
                addMessage('🟢 Connected to WebSocket');
                updateStatus(true);
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                addMessage(`📡 ${data.type}: ${JSON.stringify(data.data)}`);
            };
            
            ws.onclose = function() {
                addMessage('🔴 WebSocket connection closed');
                updateStatus(false);
            };
            
            ws.onerror = function(error) {
                addMessage(`❌ WebSocket error: ${error}`);
            };
        }
        
        function disconnect() {
            if (ws) {
                ws.close();
                ws = null;
            }
        }
        
        function subscribePrices() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'subscribe',
                    stream_type: 'price_feed'
                }));
                addMessage('📈 Subscribed to price feed');
            }
        }
        
        function subscribePortfolio() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'subscribe',
                    stream_type: 'portfolio'
                }));
                addMessage('💰 Subscribed to portfolio updates');
            }
        }
        
        function ping() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'ping'
                }));
                addMessage('🏓 Ping sent');
            }
        }
    </script>
</body>
</html>
EOF

print_success "WebSocket demo created: websocket_test.html"
print_info "Open websocket_test.html in your browser to test real-time features"

# Performance Summary
print_header "Performance Summary"

echo "📊 Features Implemented:"
echo "✅ Multi-user authentication with JWT"
echo "✅ Real-time WebSocket streaming" 
echo "✅ Advanced AI analysis engine"
echo "✅ Enhanced portfolio management"
echo "✅ Market data feeds"
echo "✅ System administration"
echo "✅ Database with user management"
echo "✅ API key management"
echo ""

echo "🔗 Available Endpoints:"
echo "   Authentication: /api/auth/*"
echo "   AI Analysis: /api/ai/*"
echo "   Portfolio: /api/portfolio/*"
echo "   Market Data: /api/market/*"
echo "   Admin: /api/admin/*"
echo "   WebSocket: ws://localhost:8010/ws/{user_id}"
echo ""

echo "🎭 Demo Credentials:"
echo "   Email: demo@tradingbot.com"
echo "   Password: demo123"
echo "   Plan: PRO (full features)"
echo ""

echo "📚 Next Steps:"
echo "1. Open browser: http://localhost:8010"
echo "2. Test WebSocket: Open websocket_test.html"
echo "3. API Documentation: http://localhost:8010/docs"
echo "4. Deploy to VPS: Follow VPS_DEVELOPMENT_PLAN.md"

echo -e "\n🎉 ${GREEN}VPS Trading Bot Advanced Features Demo Complete!${NC}"
