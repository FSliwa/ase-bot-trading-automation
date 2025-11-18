#!/usr/bin/env python3
"""
ASE-Bot Server Monitoring & Recovery Script
Automated monitoring and diagnostics for production server issues
"""

import subprocess
import requests
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import socket
import ssl
import concurrent.futures
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('server_monitor')

class ServerMonitor:
    """Comprehensive server monitoring and diagnostic tool"""
    
    def __init__(self):
        self.domain = "ase-bot.live"
        self.ip_address = "185.70.198.201"
        self.ports_to_check = [22, 80, 443, 4000, 8080, 3000, 8000, 9000]
        self.monitoring_results = []
        
    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Run complete monitoring cycle"""
        logger.info(f"🔍 Starting monitoring cycle for {self.domain}")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "domain": self.domain,
            "ip_address": self.ip_address,
            "dns_resolution": self.check_dns_resolution(),
            "ping_test": self.check_ping(),
            "port_scan": self.check_ports(),
            "http_tests": self.check_http_services(),
            "ssl_check": self.check_ssl_certificate(),
            "traceroute": self.run_traceroute(),
            "whois_info": self.get_whois_info(),
            "recommendations": []
        }
        
        # Analyze results and generate recommendations
        results["recommendations"] = self.generate_recommendations(results)
        results["overall_status"] = self.determine_overall_status(results)
        
        return results
    
    def check_dns_resolution(self) -> Dict[str, Any]:
        """Check DNS resolution"""
        try:
            result = subprocess.run(['nslookup', self.domain], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return {
                    "status": "SUCCESS",
                    "details": "DNS resolution working",
                    "output": result.stdout,
                    "resolved_ip": self.ip_address
                }
            else:
                return {
                    "status": "FAILED",
                    "details": "DNS resolution failed",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "details": "DNS lookup timed out"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "details": f"DNS check error: {str(e)}"
            }
    
    def check_ping(self) -> Dict[str, Any]:
        """Check ping connectivity"""
        try:
            result = subprocess.run(['ping', '-c', '5', self.ip_address], 
                                  capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                # Parse ping statistics
                output_lines = result.stdout.split('\n')
                stats_line = [line for line in output_lines if 'packet loss' in line]
                
                if stats_line:
                    packet_loss = stats_line[0]
                    if '0% packet loss' in packet_loss:
                        status = "SUCCESS"
                        details = "Server responding to ping"
                    elif '100% packet loss' in packet_loss:
                        status = "FAILED"
                        details = "Server not responding (100% packet loss)"
                    else:
                        status = "PARTIAL"
                        details = f"Partial connectivity: {packet_loss}"
                else:
                    status = "SUCCESS"
                    details = "Ping completed successfully"
                
                return {
                    "status": status,
                    "details": details,
                    "output": result.stdout
                }
            else:
                return {
                    "status": "FAILED", 
                    "details": "Ping failed",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "details": "Ping request timed out"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "details": f"Ping error: {str(e)}"
            }
    
    def check_ports(self) -> Dict[str, Any]:
        """Check port accessibility"""
        def check_single_port(port):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((self.ip_address, port))
                sock.close()
                
                if result == 0:
                    return port, "OPEN"
                else:
                    return port, "CLOSED/FILTERED"
            except Exception as e:
                return port, f"ERROR: {str(e)}"
        
        # Check ports concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(check_single_port, port) for port in self.ports_to_check]
            port_results = [future.result() for future in futures]
        
        open_ports = [port for port, status in port_results if status == "OPEN"]
        closed_ports = [port for port, status in port_results if "CLOSED" in status]
        
        return {
            "open_ports": open_ports,
            "closed_ports": closed_ports,
            "total_checked": len(self.ports_to_check),
            "port_details": dict(port_results),
            "status": "GOOD" if open_ports else "BAD" if closed_ports else "UNKNOWN"
        }
    
    def check_http_services(self) -> Dict[str, Any]:
        """Check HTTP/HTTPS services"""
        services = {
            "HTTP": f"http://{self.domain}",
            "HTTPS": f"https://{self.domain}",
            "HTTP_IP": f"http://{self.ip_address}",
            "HTTPS_IP": f"https://{self.ip_address}",
            "ALT_HTTP": f"http://{self.domain}:8080",
            "ALT_HTTPS": f"https://{self.domain}:8443"
        }
        
        results = {}
        
        for service_name, url in services.items():
            try:
                response = requests.get(url, timeout=10, verify=False)
                results[service_name] = {
                    "status": "SUCCESS",
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "content_length": len(response.content),
                    "headers": dict(response.headers)
                }
            except requests.exceptions.SSLError as e:
                results[service_name] = {
                    "status": "SSL_ERROR",
                    "details": str(e)
                }
            except requests.exceptions.ConnectionError as e:
                results[service_name] = {
                    "status": "CONNECTION_ERROR", 
                    "details": str(e)
                }
            except requests.exceptions.Timeout:
                results[service_name] = {
                    "status": "TIMEOUT",
                    "details": "Request timed out"
                }
            except Exception as e:
                results[service_name] = {
                    "status": "ERROR",
                    "details": str(e)
                }
        
        # Determine overall HTTP status
        successful_services = [k for k, v in results.items() if v.get("status") == "SUCCESS"]
        overall_status = "GOOD" if successful_services else "BAD"
        
        return {
            "overall_status": overall_status,
            "successful_services": successful_services,
            "service_details": results
        }
    
    def check_ssl_certificate(self) -> Dict[str, Any]:
        """Check SSL certificate status"""
        try:
            context = ssl.create_default_context()
            with socket.create_connection((self.domain, 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=self.domain) as ssock:
                    cert = ssock.getpeercert()
                    
                    # Parse certificate details
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                    days_until_expiry = (not_after - datetime.now()).days
                    
                    return {
                        "status": "SUCCESS",
                        "certificate_valid": True,
                        "subject": dict(cert['subject'][0]),
                        "issuer": dict(cert['issuer']),
                        "not_before": cert['notBefore'],
                        "not_after": cert['notAfter'],
                        "days_until_expiry": days_until_expiry,
                        "san": cert.get('subjectAltName', [])
                    }
        except socket.gaierror:
            return {
                "status": "DNS_ERROR",
                "details": "Cannot resolve domain for SSL check"
            }
        except socket.timeout:
            return {
                "status": "TIMEOUT",
                "details": "SSL connection timed out"
            }
        except ssl.SSLError as e:
            return {
                "status": "SSL_ERROR",
                "details": str(e)
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "details": f"SSL check failed: {str(e)}"
            }
    
    def run_traceroute(self) -> Dict[str, Any]:
        """Run traceroute to analyze network path"""
        try:
            result = subprocess.run(['traceroute', self.ip_address], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {
                    "status": "SUCCESS",
                    "output": result.stdout,
                    "hops": len(result.stdout.split('\n')) - 2
                }
            else:
                return {
                    "status": "FAILED",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "details": "Traceroute timed out"
            }
        except FileNotFoundError:
            # Try with tracepath if traceroute is not available
            try:
                result = subprocess.run(['tracepath', self.ip_address], 
                                      capture_output=True, text=True, timeout=30)
                return {
                    "status": "SUCCESS",
                    "output": result.stdout,
                    "method": "tracepath"
                }
            except:
                return {
                    "status": "UNAVAILABLE",
                    "details": "Traceroute tools not available"
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "details": f"Traceroute error: {str(e)}"
            }
    
    def get_whois_info(self) -> Dict[str, Any]:
        """Get WHOIS information"""
        try:
            result = subprocess.run(['whois', self.domain], 
                                  capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                # Parse relevant info from whois output
                output = result.stdout
                registrar = None
                expiry = None
                
                for line in output.split('\n'):
                    if 'registrar:' in line.lower():
                        registrar = line.split(':', 1)[1].strip()
                    elif 'expiry' in line.lower() or 'expires' in line.lower():
                        expiry = line.split(':', 1)[1].strip()
                
                return {
                    "status": "SUCCESS",
                    "registrar": registrar,
                    "expiry": expiry,
                    "full_output": output[:1000]  # Limit output size
                }
            else:
                return {
                    "status": "FAILED",
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "details": "WHOIS lookup timed out"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "details": f"WHOIS error: {str(e)}"
            }
    
    def generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on monitoring results"""
        recommendations = []
        
        # DNS issues
        if results["dns_resolution"]["status"] != "SUCCESS":
            recommendations.append("🔴 CRITICAL: Fix DNS resolution issues")
        
        # Ping issues
        if results["ping_test"]["status"] == "FAILED":
            recommendations.append("🔴 CRITICAL: Server not responding to ping - check server status")
        elif results["ping_test"]["status"] == "PARTIAL":
            recommendations.append("⚠️ WARNING: Intermittent connectivity issues detected")
        
        # Port issues
        if not results["port_scan"]["open_ports"]:
            recommendations.append("🔴 CRITICAL: All ports closed/filtered - check firewall configuration")
        elif 80 not in results["port_scan"]["open_ports"]:
            recommendations.append("⚠️ WARNING: HTTP port 80 not accessible")
        elif 443 not in results["port_scan"]["open_ports"]:
            recommendations.append("⚠️ WARNING: HTTPS port 443 not accessible")
        
        # HTTP service issues
        if results["http_tests"]["overall_status"] == "BAD":
            recommendations.append("🔴 CRITICAL: Web services not accessible")
        
        # SSL issues
        ssl_status = results["ssl_check"]["status"]
        if ssl_status == "SSL_ERROR":
            recommendations.append("🔴 CRITICAL: SSL certificate issues detected")
        elif ssl_status == "ERROR" or ssl_status == "TIMEOUT":
            recommendations.append("⚠️ WARNING: SSL connectivity issues")
        elif ssl_status == "SUCCESS":
            days_left = results["ssl_check"].get("days_until_expiry", 0)
            if days_left < 30:
                recommendations.append(f"⚠️ WARNING: SSL certificate expires in {days_left} days")
        
        # General recommendations
        if not recommendations:
            recommendations.append("✅ No critical issues detected - monitoring healthy")
        else:
            recommendations.append("📞 Contact hosting provider (UpCloud) for server issues")
            recommendations.append("🔧 Check server logs and restart services")
            recommendations.append("🛡️ Review firewall and security group settings")
        
        return recommendations
    
    def determine_overall_status(self, results: Dict[str, Any]) -> str:
        """Determine overall server status"""
        critical_issues = 0
        warnings = 0
        
        # Check each category
        if results["dns_resolution"]["status"] != "SUCCESS":
            critical_issues += 1
            
        if results["ping_test"]["status"] == "FAILED":
            critical_issues += 1
        elif results["ping_test"]["status"] == "PARTIAL":
            warnings += 1
            
        if not results["port_scan"]["open_ports"]:
            critical_issues += 1
            
        if results["http_tests"]["overall_status"] == "BAD":
            critical_issues += 1
            
        if results["ssl_check"]["status"] in ["SSL_ERROR", "ERROR"]:
            warnings += 1
        
        # Determine status
        if critical_issues > 0:
            return "CRITICAL"
        elif warnings > 0:
            return "WARNING"  
        else:
            return "HEALTHY"
    
    def save_monitoring_report(self, results: Dict[str, Any]) -> str:
        """Save monitoring report to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"server_monitoring_report_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        return filename
    
    def continuous_monitoring(self, interval_minutes: int = 5, duration_hours: int = 1):
        """Run continuous monitoring"""
        end_time = time.time() + (duration_hours * 3600)
        
        logger.info(f"🔄 Starting continuous monitoring (interval: {interval_minutes}m, duration: {duration_hours}h)")
        
        while time.time() < end_time:
            try:
                results = self.run_monitoring_cycle()
                filename = self.save_monitoring_report(results)
                
                logger.info(f"📊 Monitoring cycle complete - Status: {results['overall_status']}")
                logger.info(f"📋 Report saved: {filename}")
                
                # Print summary
                print(f"""
🕐 {datetime.now().strftime('%H:%M:%S')} - Monitoring Update
Status: {results['overall_status']}
DNS: {results['dns_resolution']['status']}
Ping: {results['ping_test']['status']} 
Ports: {len(results['port_scan']['open_ports'])} open
HTTP: {results['http_tests']['overall_status']}
SSL: {results['ssl_check']['status']}
""")
                
                if results['overall_status'] == 'CRITICAL':
                    logger.error("🚨 CRITICAL ISSUES DETECTED!")
                    for rec in results['recommendations'][:3]:
                        logger.error(f"   {rec}")
                
                # Wait for next cycle
                time.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("👋 Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Monitoring cycle failed: {str(e)}")
                time.sleep(30)  # Short wait before retry

def main():
    """Main monitoring function"""
    monitor = ServerMonitor()
    
    print("""
🔍 ASE-Bot Server Monitoring Tool
================================
Choose monitoring mode:
1. Single diagnostic scan
2. Continuous monitoring (5min intervals)
3. Quick health check
""")
    
    try:
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == "1":
            logger.info("Running single diagnostic scan...")
            results = monitor.run_monitoring_cycle()
            filename = monitor.save_monitoring_report(results)
            
            print(f"""
📊 Diagnostic Scan Complete
==========================
Overall Status: {results['overall_status']}
Report saved: {filename}

🔍 Quick Summary:
DNS: {results['dns_resolution']['status']}
Ping: {results['ping_test']['status']}
Open Ports: {len(results['port_scan']['open_ports'])}
HTTP Services: {results['http_tests']['overall_status']}
SSL: {results['ssl_check']['status']}

💡 Top Recommendations:
""")
            for i, rec in enumerate(results['recommendations'][:5], 1):
                print(f"{i}. {rec}")
        
        elif choice == "2":
            duration = input("Monitoring duration in hours (default 1): ").strip()
            duration = int(duration) if duration.isdigit() else 1
            monitor.continuous_monitoring(interval_minutes=5, duration_hours=duration)
        
        elif choice == "3":
            logger.info("Running quick health check...")
            # Quick checks only
            dns_ok = monitor.check_dns_resolution()["status"] == "SUCCESS"
            ping_ok = monitor.check_ping()["status"] == "SUCCESS"
            
            print(f"""
⚡ Quick Health Check
===================
DNS Resolution: {'✅' if dns_ok else '❌'}
Server Ping: {'✅' if ping_ok else '❌'}
Overall: {'🟢 Basic connectivity OK' if dns_ok and ping_ok else '🔴 Connection issues detected'}
""")
        else:
            print("Invalid choice. Exiting.")
    
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped by user")
    except Exception as e:
        logger.error(f"❌ Monitoring failed: {str(e)}")

if __name__ == "__main__":
    main()
