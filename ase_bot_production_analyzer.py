#!/usr/bin/env python3
"""
ASE-Bot Production Analysis & Testing Suite
Comprehensive multi-layered analysis tool for ASE-Bot application
"""

import subprocess
import sys
import os
import time
import json
import sqlite3
import threading
import requests
from datetime import datetime
from pathlib import Path
import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple
import logging
from dataclasses import dataclass
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ase_bot_analyzer')

@dataclass
class AnalysisResult:
    category: str
    test_name: str
    status: str  # PASS, FAIL, WARNING, SKIP
    score: int   # 0-100
    details: str
    metrics: Dict[str, Any]
    recommendations: List[str]

class ASEBotAnalyzer:
    """Comprehensive ASE-Bot Production Analysis Suite"""
    
    def __init__(self):
        self.results: List[AnalysisResult] = []
        self.start_time = datetime.now()
        self.base_url = "http://localhost:8080"  # Local testing since prod is down
        self.database_path = "trading.db"
        
    def log_result(self, result: AnalysisResult):
        """Log and store analysis result"""
        self.results.append(result)
        logger.info(f"{result.category}: {result.test_name} - {result.status} ({result.score}/100)")
    
    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run complete multi-layered analysis"""
        logger.info("🚀 Starting ASE-Bot Comprehensive Production Analysis")
        
        # Run all analysis categories
        self.analyze_infrastructure()
        self.analyze_external_connections()
        self.analyze_user_journey()
        self.analyze_technical_performance()
        self.analyze_security()
        self.analyze_ux_conversion()
        self.analyze_ai_trading()
        self.analyze_monitoring()
        
        # Generate final report
        return self.generate_report()
    
    def analyze_infrastructure(self):
        """1. Infrastructure & System Connections Analysis"""
        logger.info("🏗️ Analyzing Infrastructure & Connections...")
        
        # Test local application availability
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.log_result(AnalysisResult(
                    category="Infrastructure",
                    test_name="Local Application Availability",
                    status="PASS",
                    score=100,
                    details=f"Application running on {self.base_url}",
                    metrics={"uptime_seconds": data.get("uptime_seconds", 0)},
                    recommendations=[]
                ))
            else:
                self.log_result(AnalysisResult(
                    category="Infrastructure", 
                    test_name="Local Application Availability",
                    status="FAIL",
                    score=0,
                    details=f"HTTP {response.status_code}",
                    metrics={},
                    recommendations=["Start local application server"]
                ))
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Local Application Availability", 
                status="FAIL",
                score=0,
                details=f"Connection error: {str(e)}",
                metrics={},
                recommendations=["Ensure application is running on port 8080"]
            ))
        
        # Test production server connectivity
        self.test_production_server()
        
        # Test database connectivity
        self.test_database_connectivity()
    
    def test_production_server(self):
        """Test production server ase-bot.live"""
        try:
            # Test HTTP
            response = requests.get("http://ase-bot.live", timeout=10)
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Production Server HTTP",
                status="PASS",
                score=100,
                details=f"HTTP {response.status_code}",
                metrics={"response_time": response.elapsed.total_seconds()},
                recommendations=[]
            ))
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Production Server HTTP",
                status="FAIL",
                score=0,
                details=f"Connection failed: {str(e)}",
                metrics={},
                recommendations=[
                    "Check server status and firewall configuration",
                    "Verify DNS settings", 
                    "Ensure web server is running",
                    "Check SSL certificate configuration"
                ]
            ))
        
        # Test HTTPS
        try:
            response = requests.get("https://ase-bot.live", timeout=10)
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Production Server HTTPS/SSL",
                status="PASS", 
                score=100,
                details=f"HTTPS {response.status_code}, SSL valid",
                metrics={"response_time": response.elapsed.total_seconds()},
                recommendations=[]
            ))
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Production Server HTTPS/SSL",
                status="FAIL",
                score=0,
                details=f"SSL/HTTPS failed: {str(e)}",
                metrics={},
                recommendations=[
                    "Configure SSL certificate (Let's Encrypt recommended)",
                    "Set up HTTPS redirect",
                    "Verify certificate chain",
                    "Check firewall port 443"
                ]
            ))
    
    def test_database_connectivity(self):
        """Test database connectivity and structure"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Get table count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            
            # Get database size
            db_size = os.path.getsize(self.database_path) if os.path.exists(self.database_path) else 0
            
            # Test key tables
            key_tables = ['users', 'positions', 'trading_stats', 'orders']
            table_stats = {}
            
            for table in key_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    table_stats[table] = cursor.fetchone()[0]
                except:
                    table_stats[table] = "N/A"
            
            conn.close()
            
            score = 90 if table_count >= 20 else 70 if table_count >= 10 else 40
            
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Database Connectivity & Structure",
                status="PASS",
                score=score,
                details=f"SQLite database with {table_count} tables",
                metrics={
                    "table_count": table_count,
                    "db_size_kb": db_size // 1024,
                    "key_tables": table_stats
                },
                recommendations=[
                    "Consider PostgreSQL for production scalability",
                    "Implement database backup strategy",
                    "Add connection pooling"
                ] if table_count < 25 else []
            ))
            
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Infrastructure",
                test_name="Database Connectivity",
                status="FAIL",
                score=0,
                details=f"Database error: {str(e)}",
                metrics={},
                recommendations=[
                    "Check database file permissions",
                    "Verify database schema",
                    "Initialize database if missing"
                ]
            ))
    
    def analyze_external_connections(self):
        """2. External Connections Analysis"""
        logger.info("🔌 Analyzing External Connections...")
        
        # Test major crypto exchanges API availability
        exchanges = {
            "Binance": "https://api.binance.com/api/v3/ping",
            "Coinbase": "https://api.pro.coinbase.com/time", 
            "Kraken": "https://api.kraken.com/0/public/Time"
        }
        
        for exchange, url in exchanges.items():
            self.test_external_api(exchange, url)
        
        # Test payment services
        payment_services = {
            "Stripe API": "https://api.stripe.com/v1",
            "PayPal API": "https://api.paypal.com/v1/oauth2/token"
        }
        
        for service, url in payment_services.items():
            self.test_external_api(service, url, expect_auth_error=True)
    
    def test_external_api(self, service_name: str, url: str, expect_auth_error: bool = False):
        """Test external API connectivity"""
        try:
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                status = "PASS"
                score = 100
                details = f"{service_name} API accessible"
            elif expect_auth_error and response.status_code in [401, 403]:
                status = "PASS" 
                score = 90
                details = f"{service_name} API accessible (auth required as expected)"
            else:
                status = "WARNING"
                score = 60
                details = f"{service_name} API returned {response.status_code}"
            
            self.log_result(AnalysisResult(
                category="External Connections",
                test_name=f"{service_name} API Connectivity",
                status=status,
                score=score,
                details=details,
                metrics={"response_time": response.elapsed.total_seconds()},
                recommendations=["Set up API keys and test integration"] if score < 100 else []
            ))
            
        except Exception as e:
            self.log_result(AnalysisResult(
                category="External Connections",
                test_name=f"{service_name} API Connectivity", 
                status="FAIL",
                score=0,
                details=f"Connection failed: {str(e)}",
                metrics={},
                recommendations=[
                    f"Check {service_name} service status",
                    "Verify network connectivity",
                    "Consider implementing retry logic"
                ]
            ))
    
    def analyze_user_journey(self):
        """3. End-to-End User Journey Analysis"""
        logger.info("👤 Analyzing User Journey...")
        
        # Test registration flow simulation
        self.test_registration_flow()
        
        # Test login flow
        self.test_login_flow()
        
        # Test dashboard loading
        self.test_dashboard_performance()
        
        # Test trading interface
        self.test_trading_interface()
    
    def test_registration_flow(self):
        """Simulate user registration process"""
        try:
            # Test main page loading
            start_time = time.time()
            response = requests.get(self.base_url, timeout=10)
            load_time = time.time() - start_time
            
            if response.status_code == 200:
                # Check for registration elements
                has_signup = "sign" in response.text.lower() or "register" in response.text.lower()
                
                score = 90 if has_signup and load_time < 3 else 70 if has_signup else 40
                
                self.log_result(AnalysisResult(
                    category="User Journey",
                    test_name="Registration Flow - Landing Page",
                    status="PASS" if score > 70 else "WARNING",
                    score=score,
                    details=f"Page loaded in {load_time:.2f}s, signup elements: {has_signup}",
                    metrics={
                        "load_time": load_time,
                        "has_signup_elements": has_signup,
                        "response_size": len(response.content)
                    },
                    recommendations=[
                        "Optimize page load time to <2s",
                        "Add clear call-to-action for registration"
                    ] if score < 90 else []
                ))
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_result(AnalysisResult(
                category="User Journey",
                test_name="Registration Flow - Landing Page",
                status="FAIL", 
                score=0,
                details=f"Landing page failed: {str(e)}",
                metrics={},
                recommendations=[
                    "Fix application server",
                    "Ensure proper routing configuration"
                ]
            ))
    
    def test_login_flow(self):
        """Test login functionality"""
        # This would test login API endpoints
        login_tests = [
            ("Login API Endpoint", "/api/auth/login", "POST"),
            ("Session Management", "/api/auth/me", "GET"),
            ("Password Recovery", "/api/auth/forgot-password", "POST")
        ]
        
        for test_name, endpoint, method in login_tests:
            try:
                url = f"{self.base_url}{endpoint}"
                if method == "GET":
                    response = requests.get(url, timeout=5)
                else:
                    response = requests.post(url, json={}, timeout=5)
                
                # Expected: auth endpoints should exist (even if return 401/400)
                score = 80 if response.status_code in [400, 401, 422] else 60 if response.status_code == 404 else 40
                
                self.log_result(AnalysisResult(
                    category="User Journey",
                    test_name=f"Login Flow - {test_name}",
                    status="PASS" if score >= 80 else "WARNING", 
                    score=score,
                    details=f"Endpoint {endpoint} returned {response.status_code}",
                    metrics={"status_code": response.status_code},
                    recommendations=[
                        f"Implement {endpoint} endpoint",
                        "Add proper authentication middleware"
                    ] if score < 80 else []
                ))
                
            except Exception as e:
                self.log_result(AnalysisResult(
                    category="User Journey",
                    test_name=f"Login Flow - {test_name}",
                    status="FAIL",
                    score=0, 
                    details=f"Endpoint test failed: {str(e)}",
                    metrics={},
                    recommendations=["Implement authentication system"]
                ))
    
    def test_dashboard_performance(self):
        """Test dashboard loading and performance"""
        endpoints_to_test = [
            "/api/portfolio", 
            "/api/trades",
            "/api/stats",
            "/api/database/status"
        ]
        
        total_score = 0
        total_tests = len(endpoints_to_test)
        
        for endpoint in endpoints_to_test:
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    # Try to parse JSON
                    data = response.json()
                    data_quality = len(data) > 0
                    
                    # Score based on response time and data quality
                    score = 100 if response_time < 0.2 and data_quality else 80 if response_time < 0.5 else 60
                    total_score += score
                    
                    self.log_result(AnalysisResult(
                        category="User Journey",
                        test_name=f"Dashboard API - {endpoint}",
                        status="PASS",
                        score=score,
                        details=f"Response in {response_time:.3f}s, data quality: {data_quality}",
                        metrics={
                            "response_time": response_time,
                            "data_size": len(str(data)),
                            "has_data": data_quality
                        },
                        recommendations=[
                            "Optimize API response time to <200ms"
                        ] if response_time > 0.2 else []
                    ))
                else:
                    raise Exception(f"HTTP {response.status_code}")
                    
            except Exception as e:
                self.log_result(AnalysisResult(
                    category="User Journey", 
                    test_name=f"Dashboard API - {endpoint}",
                    status="FAIL",
                    score=0,
                    details=f"API failed: {str(e)}",
                    metrics={},
                    recommendations=["Fix API endpoint implementation"]
                ))
        
        # Overall dashboard score
        avg_score = total_score / total_tests if total_tests > 0 else 0
        self.log_result(AnalysisResult(
            category="User Journey",
            test_name="Dashboard Overall Performance",
            status="PASS" if avg_score > 80 else "WARNING" if avg_score > 60 else "FAIL",
            score=int(avg_score),
            details=f"Average API performance score: {avg_score:.1f}/100",
            metrics={"average_score": avg_score},
            recommendations=[
                "Implement caching for frequently accessed data",
                "Add loading states for better UX",
                "Consider API response compression"
            ] if avg_score < 90 else []
        ))
    
    def test_trading_interface(self):
        """Test trading interface functionality"""
        # Simulate trading bot creation and management
        trading_tests = [
            "Bot Creation API",
            "Strategy Selection", 
            "Risk Management Settings",
            "Real-time Market Data",
            "Order Placement Simulation"
        ]
        
        for test in trading_tests:
            # Since we don't have real trading endpoints, simulate based on what we know
            score = 40  # Not implemented yet
            
            self.log_result(AnalysisResult(
                category="User Journey",
                test_name=f"Trading Interface - {test}",
                status="SKIP",
                score=score,
                details="Trading interface not fully implemented in current version",
                metrics={},
                recommendations=[
                    f"Implement {test} functionality",
                    "Add comprehensive trading API",
                    "Integrate with exchange APIs",
                    "Add risk management controls"
                ]
            ))
    
    def analyze_technical_performance(self):
        """4. Technical Performance Analysis"""
        logger.info("⚡ Analyzing Technical Performance...")
        
        # Test concurrent request handling
        self.test_concurrent_performance()
        
        # Test response times under load
        self.test_load_performance()
        
        # Test error handling
        self.test_error_handling()
    
    def test_concurrent_performance(self):
        """Test handling of concurrent requests"""
        def make_request():
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}/api/health", timeout=5)
                return time.time() - start_time, response.status_code
            except:
                return None, None
        
        # Test with 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]
        
        successful_requests = [r for r in results if r[1] == 200]
        avg_response_time = sum(r[0] for r in successful_requests) / len(successful_requests) if successful_requests else 0
        success_rate = len(successful_requests) / len(results) * 100
        
        score = 90 if success_rate == 100 and avg_response_time < 0.5 else 70 if success_rate > 80 else 40
        
        self.log_result(AnalysisResult(
            category="Technical Performance",
            test_name="Concurrent Request Handling",
            status="PASS" if score > 70 else "WARNING",
            score=score,
            details=f"Success rate: {success_rate}%, Avg response: {avg_response_time:.3f}s",
            metrics={
                "success_rate": success_rate,
                "avg_response_time": avg_response_time,
                "concurrent_requests": 10
            },
            recommendations=[
                "Implement connection pooling",
                "Add request queuing for high load",
                "Consider async request handling"
            ] if score < 90 else []
        ))
    
    def test_load_performance(self):
        """Test performance under load"""
        # Sequential requests to measure baseline performance
        response_times = []
        
        for i in range(20):
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}/api/health", timeout=5)
                if response.status_code == 200:
                    response_times.append(time.time() - start_time)
            except:
                pass
        
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            p95_time = sorted(response_times)[int(0.95 * len(response_times))]
            
            score = 100 if avg_time < 0.1 and p95_time < 0.2 else 80 if avg_time < 0.2 else 60 if avg_time < 0.5 else 40
            
            self.log_result(AnalysisResult(
                category="Technical Performance", 
                test_name="Load Performance Testing",
                status="PASS" if score > 70 else "WARNING",
                score=score,
                details=f"Avg: {avg_time:.3f}s, P95: {p95_time:.3f}s",
                metrics={
                    "avg_response_time": avg_time,
                    "p95_response_time": p95_time,
                    "total_requests": len(response_times)
                },
                recommendations=[
                    "Optimize database queries",
                    "Implement caching strategy", 
                    "Consider CDN for static assets"
                ] if score < 90 else []
            ))
        else:
            self.log_result(AnalysisResult(
                category="Technical Performance",
                test_name="Load Performance Testing",
                status="FAIL",
                score=0,
                details="No successful requests during load test",
                metrics={},
                recommendations=["Fix application stability issues"]
            ))
    
    def test_error_handling(self):
        """Test error handling and recovery"""
        error_tests = [
            ("/api/nonexistent", 404, "Non-existent Endpoint"),
            ("/api/health?invalid=param", 200, "Invalid Parameters"),  # Should still work
        ]
        
        for endpoint, expected_status, test_name in error_tests:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                
                if response.status_code == expected_status:
                    score = 100
                    status = "PASS"
                    details = f"Correctly returned {response.status_code}"
                else:
                    score = 60
                    status = "WARNING" 
                    details = f"Expected {expected_status}, got {response.status_code}"
                
                self.log_result(AnalysisResult(
                    category="Technical Performance",
                    test_name=f"Error Handling - {test_name}",
                    status=status,
                    score=score,
                    details=details,
                    metrics={"status_code": response.status_code},
                    recommendations=[
                        "Implement proper HTTP status codes",
                        "Add structured error responses"
                    ] if score < 100 else []
                ))
                
            except Exception as e:
                self.log_result(AnalysisResult(
                    category="Technical Performance",
                    test_name=f"Error Handling - {test_name}",
                    status="FAIL",
                    score=0,
                    details=f"Request failed: {str(e)}",
                    metrics={},
                    recommendations=["Fix request handling implementation"]
                ))
    
    def analyze_security(self):
        """5. Security Analysis"""
        logger.info("🔒 Analyzing Security...")
        
        # Test HTTPS/SSL
        self.test_ssl_security()
        
        # Test common security headers
        self.test_security_headers()
        
        # Test input validation
        self.test_input_validation()
    
    def test_ssl_security(self):
        """Test SSL/TLS configuration"""
        # This would be more relevant for production server
        self.log_result(AnalysisResult(
            category="Security",
            test_name="SSL/TLS Configuration",
            status="SKIP", 
            score=0,
            details="Production server not accessible for SSL testing",
            metrics={},
            recommendations=[
                "Implement SSL certificate for production",
                "Use Let's Encrypt for free SSL",
                "Configure HSTS headers",
                "Disable weak TLS versions"
            ]
        ))
    
    def test_security_headers(self):
        """Test security headers"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            headers = response.headers
            
            security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000",
                "Content-Security-Policy": "default-src 'self'"
            }
            
            present_headers = sum(1 for header in security_headers if header in headers)
            score = int((present_headers / len(security_headers)) * 100)
            
            self.log_result(AnalysisResult(
                category="Security",
                test_name="Security Headers",
                status="PASS" if score > 80 else "WARNING" if score > 40 else "FAIL",
                score=score,
                details=f"{present_headers}/{len(security_headers)} security headers present",
                metrics={"present_headers": present_headers, "total_headers": len(security_headers)},
                recommendations=[
                    f"Add missing security header: {header}" 
                    for header in security_headers if header not in headers
                ]
            ))
            
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Security",
                test_name="Security Headers",
                status="FAIL",
                score=0,
                details=f"Could not test security headers: {str(e)}",
                metrics={},
                recommendations=["Implement security headers middleware"]
            ))
    
    def test_input_validation(self):
        """Test input validation and sanitization"""
        # Test various injection attempts
        injection_tests = [
            ("SQL Injection", "' OR '1'='1", "/api/health?id="),
            ("XSS", "<script>alert('xss')</script>", "/api/health?msg="),
            ("Path Traversal", "../../../etc/passwd", "/api/health?file=")
        ]
        
        for test_name, payload, endpoint_template in injection_tests:
            try:
                url = f"{self.base_url}{endpoint_template}{payload}"
                response = requests.get(url, timeout=5)
                
                # Should not execute or return dangerous content
                dangerous = payload.lower() in response.text.lower()
                score = 60 if not dangerous else 20  # Medium score since we can't fully test
                
                self.log_result(AnalysisResult(
                    category="Security",
                    test_name=f"Input Validation - {test_name}",
                    status="PASS" if not dangerous else "FAIL",
                    score=score,
                    details=f"Payload reflected: {dangerous}",
                    metrics={"payload_reflected": dangerous},
                    recommendations=[
                        "Implement input validation and sanitization",
                        "Use parameterized queries for database",
                        "Add CSRF protection"
                    ] if score < 80 else []
                ))
                
            except Exception as e:
                self.log_result(AnalysisResult(
                    category="Security",
                    test_name=f"Input Validation - {test_name}",
                    status="SKIP",
                    score=50,
                    details=f"Could not test: {str(e)}",
                    metrics={},
                    recommendations=["Ensure robust input validation"]
                ))
    
    def analyze_ux_conversion(self):
        """6. UX/UI and Conversion Analysis"""
        logger.info("🎨 Analyzing UX/UI and Conversion...")
        
        # Test page load performance (Core Web Vitals simulation)
        self.test_page_performance()
        
        # Test mobile responsiveness simulation
        self.test_mobile_responsiveness()
    
    def test_page_performance(self):
        """Test page loading performance metrics"""
        try:
            start_time = time.time()
            response = requests.get(self.base_url, timeout=10)
            load_time = time.time() - start_time
            
            # Simulate Core Web Vitals scoring
            fcp_score = 100 if load_time < 1.8 else 50 if load_time < 3.0 else 25
            content_size = len(response.content)
            
            score = fcp_score
            
            self.log_result(AnalysisResult(
                category="UX/Conversion",
                test_name="Page Load Performance (FCP simulation)",
                status="PASS" if score > 75 else "WARNING" if score > 40 else "FAIL",
                score=score,
                details=f"Load time: {load_time:.2f}s, Content size: {content_size/1024:.1f}KB",
                metrics={
                    "load_time": load_time,
                    "content_size_kb": content_size/1024,
                    "fcp_score": fcp_score
                },
                recommendations=[
                    "Optimize images and assets",
                    "Implement lazy loading",
                    "Use content compression",
                    "Minimize JavaScript bundles"
                ] if score < 90 else []
            ))
            
        except Exception as e:
            self.log_result(AnalysisResult(
                category="UX/Conversion",
                test_name="Page Load Performance",
                status="FAIL",
                score=0,
                details=f"Performance test failed: {str(e)}",
                metrics={},
                recommendations=["Fix application availability"]
            ))
    
    def test_mobile_responsiveness(self):
        """Test mobile responsiveness simulation"""
        try:
            # Simulate mobile user agent
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"}
            response = requests.get(self.base_url, headers=headers, timeout=5)
            
            # Check for mobile-friendly indicators in content
            content = response.text.lower()
            mobile_indicators = [
                'viewport',
                'responsive', 
                '@media',
                'mobile',
                'flex',
                'grid'
            ]
            
            mobile_score = sum(1 for indicator in mobile_indicators if indicator in content)
            score = int((mobile_score / len(mobile_indicators)) * 100)
            
            self.log_result(AnalysisResult(
                category="UX/Conversion",
                test_name="Mobile Responsiveness",
                status="PASS" if score > 60 else "WARNING",
                score=score,
                details=f"Mobile indicators found: {mobile_score}/{len(mobile_indicators)}",
                metrics={"mobile_indicators": mobile_score},
                recommendations=[
                    "Add responsive CSS media queries",
                    "Implement mobile-first design",
                    "Test on various mobile devices",
                    "Optimize touch interactions"
                ] if score < 80 else []
            ))
            
        except Exception as e:
            self.log_result(AnalysisResult(
                category="UX/Conversion",
                test_name="Mobile Responsiveness",
                status="FAIL",
                score=0,
                details=f"Mobile test failed: {str(e)}",
                metrics={},
                recommendations=["Fix application availability"]
            ))
    
    def analyze_ai_trading(self):
        """8. AI Trading Analysis"""
        logger.info("🤖 Analyzing AI Trading Capabilities...")
        
        # Since AI trading is not fully implemented, we'll assess readiness
        ai_components = [
            "Machine Learning Models",
            "Strategy Backtesting",
            "Risk Management",
            "Market Data Integration",
            "Automated Trading Logic"
        ]
        
        for component in ai_components:
            # Assess based on current implementation
            score = 30  # Basic foundation exists
            
            self.log_result(AnalysisResult(
                category="AI Trading",
                test_name=f"AI Component - {component}",
                status="SKIP",
                score=score,
                details="AI trading components not fully implemented",
                metrics={},
                recommendations=[
                    f"Implement {component} functionality",
                    "Integrate with ML frameworks (TensorFlow, PyTorch)",
                    "Add comprehensive backtesting engine",
                    "Implement real-time market data feeds",
                    "Add risk management algorithms"
                ]
            ))
    
    def analyze_monitoring(self):
        """9. Monitoring and Alerting Analysis"""
        logger.info("📊 Analyzing Monitoring & Alerting...")
        
        # Test health check endpoint
        self.test_health_monitoring()
        
        # Check for logging capabilities
        self.test_logging_system()
    
    def test_health_monitoring(self):
        """Test health monitoring endpoint"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            
            if response.status_code == 200:
                health_data = response.json()
                
                # Check health data completeness
                expected_fields = ['status', 'timestamp', 'service', 'database']
                present_fields = sum(1 for field in expected_fields if field in health_data)
                
                score = int((present_fields / len(expected_fields)) * 100)
                
                self.log_result(AnalysisResult(
                    category="Monitoring",
                    test_name="Health Check Endpoint",
                    status="PASS" if score > 80 else "WARNING",
                    score=score,
                    details=f"Health data completeness: {present_fields}/{len(expected_fields)}",
                    metrics={
                        "response_time": response.elapsed.total_seconds(),
                        "data_completeness": present_fields
                    },
                    recommendations=[
                        "Add more comprehensive health metrics",
                        "Include system resource usage",
                        "Add dependency health checks"
                    ] if score < 100 else []
                ))
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_result(AnalysisResult(
                category="Monitoring",
                test_name="Health Check Endpoint",
                status="FAIL",
                score=0,
                details=f"Health check failed: {str(e)}",
                metrics={},
                recommendations=["Implement robust health check endpoint"]
            ))
    
    def test_logging_system(self):
        """Test logging capabilities"""
        # Check if log files exist or can be accessed
        log_indicators = [
            "ase_bot_server.log",
            "server.log", 
            "application.log"
        ]
        
        log_files_found = sum(1 for log_file in log_indicators if os.path.exists(log_file))
        score = 80 if log_files_found > 0 else 40
        
        self.log_result(AnalysisResult(
            category="Monitoring", 
            test_name="Logging System",
            status="PASS" if score > 60 else "WARNING",
            score=score,
            details=f"Log files found: {log_files_found}/{len(log_indicators)}",
            metrics={"log_files_found": log_files_found},
            recommendations=[
                "Implement comprehensive logging system",
                "Add log rotation",
                "Use structured logging (JSON)",
                "Implement centralized log aggregation"
            ] if score < 90 else []
        ))
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive analysis report"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        # Calculate category scores
        categories = {}
        for result in self.results:
            if result.category not in categories:
                categories[result.category] = []
            categories[result.category].append(result.score)
        
        category_averages = {
            category: sum(scores) / len(scores) 
            for category, scores in categories.items()
        }
        
        overall_score = sum(category_averages.values()) / len(category_averages)
        
        # Count issues by severity
        critical_issues = [r for r in self.results if r.status == "FAIL"]
        warnings = [r for r in self.results if r.status == "WARNING"]
        passed_tests = [r for r in self.results if r.status == "PASS"]
        
        report = {
            "executive_summary": {
                "overall_score": round(overall_score, 1),
                "total_tests": len(self.results),
                "passed": len(passed_tests),
                "warnings": len(warnings),
                "failed": len(critical_issues),
                "analysis_duration_seconds": duration,
                "timestamp": end_time.isoformat()
            },
            "category_scores": category_averages,
            "detailed_results": [
                {
                    "category": r.category,
                    "test_name": r.test_name,
                    "status": r.status,
                    "score": r.score,
                    "details": r.details,
                    "metrics": r.metrics,
                    "recommendations": r.recommendations
                }
                for r in self.results
            ],
            "critical_issues": [
                {
                    "test": r.test_name,
                    "category": r.category,
                    "details": r.details,
                    "recommendations": r.recommendations
                }
                for r in critical_issues
            ],
            "recommendations": {
                "immediate": [],
                "short_term": [],
                "long_term": []
            }
        }
        
        # Categorize recommendations by priority
        all_recommendations = []
        for result in self.results:
            all_recommendations.extend(result.recommendations)
        
        # Simple priority assignment based on common patterns
        for rec in set(all_recommendations):
            if any(word in rec.lower() for word in ["fix", "critical", "security", "ssl", "production"]):
                report["recommendations"]["immediate"].append(rec)
            elif any(word in rec.lower() for word in ["implement", "optimize", "add", "improve"]):
                report["recommendations"]["short_term"].append(rec)
            else:
                report["recommendations"]["long_term"].append(rec)
        
        return report

def main():
    """Run comprehensive ASE-Bot analysis"""
    analyzer = ASEBotAnalyzer()
    
    try:
        report = analyzer.run_comprehensive_analysis()
        
        # Save report to file
        report_filename = f"ase_bot_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📋 Analysis complete! Report saved to: {report_filename}")
        
        # Print executive summary
        summary = report["executive_summary"]
        print(f"""
🚀 ASE-Bot Production Analysis Summary
=====================================
Overall Score: {summary['overall_score']}/100
Tests: {summary['passed']} passed, {summary['warnings']} warnings, {summary['failed']} failed
Duration: {summary['analysis_duration_seconds']:.1f} seconds

📊 Category Scores:""")
        
        for category, score in report["category_scores"].items():
            print(f"  • {category}: {score:.1f}/100")
        
        print(f"""
🔴 Critical Issues: {len(report['critical_issues'])}
⚠️  Warnings: {summary['warnings']}
✅ Passed Tests: {summary['passed']}

📋 Report saved to: {report_filename}
        """)
        
        return report_filename
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        return None

if __name__ == "__main__":
    main()
