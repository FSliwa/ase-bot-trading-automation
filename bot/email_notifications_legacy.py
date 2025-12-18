"""
Email notifications for trading bot
Handles SMTP email sending for alerts, trade notifications, and system status
"""

import os
import smtplib
import structlog
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = structlog.get_logger(__name__)

@dataclass
class EmailConfig:
    """Email configuration from environment variables"""
    enabled: bool
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    use_tls: bool
    use_ssl: bool
    from_email: str
    admin_email: str
    subject_prefix: str

def load_email_config() -> EmailConfig:
    """Load email configuration from environment variables"""
    return EmailConfig(
        enabled=os.getenv('EMAIL_ENABLED', 'false').lower() == 'true',
        smtp_host=os.getenv('SMTP_HOST', 'smtp.gmail.com'),
        smtp_port=int(os.getenv('SMTP_PORT', '587')),
        username=os.getenv('SMTP_USERNAME', ''),
        password=os.getenv('SMTP_PASSWORD', ''),
        use_tls=os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
        use_ssl=os.getenv('SMTP_USE_SSL', 'false').lower() == 'true',
        from_email=os.getenv('EMAIL_FROM', 'trading-bot@localhost'),
        admin_email=os.getenv('EMAIL_ADMIN', 'admin@localhost'),
        subject_prefix=os.getenv('EMAIL_SUBJECT_PREFIX', '[Trading Bot]')
    )

class EmailNotifier:
    """Email notification service for trading bot"""
    
    def __init__(self):
        self.config = load_email_config()
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    def _create_smtp_connection(self) -> Optional[smtplib.SMTP]:
        """Create and configure SMTP connection"""
        try:
            if not self.config.enabled:
                self.logger.info("Email notifications disabled")
                return None
            
            # Use SSL or regular SMTP based on configuration
            if self.config.use_ssl:
                smtp = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port)
            else:
                smtp = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                
                if self.config.use_tls:
                    smtp.starttls()
            
            # Only login if credentials are provided
            if self.config.username and self.config.password:
                smtp.login(self.config.username, self.config.password)
            
            return smtp
            
        except Exception as e:
            self.logger.error("Failed to create SMTP connection", error=str(e))
            return None
    
    def send_email(
        self, 
        to_emails: List[str], 
        subject: str, 
        body: str, 
        html_body: Optional[str] = None,
        attachments: Optional[List[str]] = None
    ) -> bool:
        """Send email notification"""
        try:
            smtp = self._create_smtp_connection()
            if not smtp:
                return False
            
            msg = EmailMessage()
            msg['From'] = self.config.from_email
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = f"{self.config.subject_prefix} {subject}"
            
            # Set text content
            msg.set_content(body)
            
            # Add HTML alternative if provided
            if html_body:
                msg.add_alternative(html_body, subtype='html')
            
            # Add attachments if provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            file_data = f.read()
                            file_name = os.path.basename(file_path)
                            msg.add_attachment(file_data, filename=file_name)
            
            smtp.send_message(msg)
            smtp.quit()
            
            self.logger.info("Email sent successfully", 
                           to=to_emails, subject=subject)
            return True
            
        except Exception as e:
            self.logger.error("Failed to send email", 
                            error=str(e), to=to_emails, subject=subject)
            return False
    
    def send_trade_alert(
        self, 
        symbol: str, 
        action: str, 
        price: float, 
        quantity: float, 
        profit_loss: Optional[float] = None
    ) -> bool:
        """Send trading alert notification"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        subject = f"Trade Alert: {action.upper()} {symbol}"
        
        body = f"""
Trading Bot Alert
================

Time: {timestamp}
Action: {action.upper()}
Symbol: {symbol}
Price: ${price:.4f}
Quantity: {quantity}
"""
        
        if profit_loss is not None:
            body += f"P&L: ${profit_loss:.2f}\n"
        
        html_body = f"""
        <html>
        <body>
            <h2>🤖 Trading Bot Alert</h2>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr><td><strong>Time</strong></td><td>{timestamp}</td></tr>
                <tr><td><strong>Action</strong></td><td><span style="color: {'green' if action.lower() == 'buy' else 'red'}">{action.upper()}</span></td></tr>
                <tr><td><strong>Symbol</strong></td><td>{symbol}</td></tr>
                <tr><td><strong>Price</strong></td><td>${price:.4f}</td></tr>
                <tr><td><strong>Quantity</strong></td><td>{quantity}</td></tr>
        """
        
        if profit_loss is not None:
            color = 'green' if profit_loss > 0 else 'red'
            html_body += f"""<tr><td><strong>P&L</strong></td><td><span style="color: {color}">${profit_loss:.2f}</span></td></tr>"""
        
        html_body += """
            </table>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)
    
    def send_system_alert(self, alert_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """Send system alert notification"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        subject = f"System Alert: {alert_type}"
        
        body = f"""
Trading Bot System Alert
=======================

Time: {timestamp}
Type: {alert_type}
Message: {message}
"""
        
        if details:
            body += "\nDetails:\n"
            for key, value in details.items():
                body += f"  {key}: {value}\n"
        
        html_body = f"""
        <html>
        <body>
            <h2>⚠️ Trading Bot System Alert</h2>
            <p><strong>Time:</strong> {timestamp}</p>
            <p><strong>Type:</strong> <span style="color: orange">{alert_type}</span></p>
            <p><strong>Message:</strong> {message}</p>
        """
        
        if details:
            html_body += "<h3>Details:</h3><ul>"
            for key, value in details.items():
                html_body += f"<li><strong>{key}:</strong> {value}</li>"
            html_body += "</ul>"
        
        html_body += """
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)
    
    def send_daily_report(self, trades_count: int, total_pnl: float, active_positions: int) -> bool:
        """Send daily trading report"""
        date = datetime.now().strftime("%Y-%m-%d")
        
        subject = f"Daily Trading Report - {date}"
        
        body = f"""
Daily Trading Report
===================

Date: {date}
Total Trades: {trades_count}
Total P&L: ${total_pnl:.2f}
Active Positions: {active_positions}

Generated by Automatyczny Trading Bot
"""
        
        pnl_color = 'green' if total_pnl >= 0 else 'red'
        html_body = f"""
        <html>
        <body>
            <h2>📊 Daily Trading Report</h2>
            <h3>{date}</h3>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Total Trades</strong></td><td>{trades_count}</td></tr>
                <tr><td><strong>Total P&L</strong></td><td><span style="color: {pnl_color}; font-weight: bold">${total_pnl:.2f}</span></td></tr>
                <tr><td><strong>Active Positions</strong></td><td>{active_positions}</td></tr>
            </table>
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)
    
    def test_email_connection(self) -> bool:
        """Test email configuration by sending a test email"""
        subject = "Email Configuration Test"
        body = "This is a test email from your Trading Bot. Email notifications are working correctly!"
        
        html_body = """
        <html>
        <body>
            <h2>✅ Email Test Successful</h2>
            <p>This is a test email from your <strong>Automatyczny Trading Bot</strong>.</p>
            <p>Email notifications are configured and working correctly!</p>
            <p><em>Timestamp: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

    def send_performance_alert(self, metric: str, current_value: float, threshold: float, time_period: str) -> bool:
        """Send performance alert when metrics exceed thresholds"""
        alert_type = "HIGH" if current_value > threshold else "LOW"
        
        subject = f"Performance Alert: {metric} {alert_type}"
        
        body = f"""
Performance Alert
================

Metric: {metric}
Current Value: {current_value:.2f}
Threshold: {threshold:.2f}
Time Period: {time_period}
Alert Type: {alert_type}

Please review your trading strategy if this trend continues.

Generated by Automatyczny Trading Bot
"""
        
        color = 'red' if alert_type == 'HIGH' else 'orange'
        html_body = f"""
        <html>
        <body>
            <h2>⚠️ Performance Alert</h2>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Metric</strong></td><td>{metric}</td></tr>
                <tr><td><strong>Current Value</strong></td><td><span style="color: {color}; font-weight: bold">{current_value:.2f}</span></td></tr>
                <tr><td><strong>Threshold</strong></td><td>{threshold:.2f}</td></tr>
                <tr><td><strong>Time Period</strong></td><td>{time_period}</td></tr>
                <tr><td><strong>Alert Type</strong></td><td><span style="color: {color}; font-weight: bold">{alert_type}</span></td></tr>
            </table>
            <p><strong>Recommendation:</strong> Please review your trading strategy if this trend continues.</p>
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

    def send_risk_alert(self, risk_type: str, current_risk: float, max_risk: float, positions: List[Dict]) -> bool:
        """Send risk management alert"""
        risk_percentage = (current_risk / max_risk) * 100 if max_risk > 0 else 0
        
        subject = f"Risk Management Alert: {risk_type}"
        
        body = f"""
Risk Management Alert
====================

Risk Type: {risk_type}
Current Risk: {current_risk:.2f}
Maximum Risk: {max_risk:.2f}
Risk Percentage: {risk_percentage:.1f}%

Active Positions:
"""
        
        for pos in positions:
            body += f"- {pos.get('symbol', 'Unknown')}: {pos.get('side', 'Unknown')} {pos.get('size', 0):.4f} @ ${pos.get('price', 0):.2f}\n"
        
        body += "\nPlease consider reducing position sizes or closing some positions.\n\nGenerated by Automatyczny Trading Bot"
        
        risk_color = 'red' if risk_percentage > 80 else 'orange' if risk_percentage > 60 else 'yellow'
        html_body = f"""
        <html>
        <body>
            <h2>🛡️ Risk Management Alert</h2>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Risk Type</strong></td><td>{risk_type}</td></tr>
                <tr><td><strong>Current Risk</strong></td><td>{current_risk:.2f}</td></tr>
                <tr><td><strong>Maximum Risk</strong></td><td>{max_risk:.2f}</td></tr>
                <tr><td><strong>Risk Percentage</strong></td><td><span style="color: {risk_color}; font-weight: bold">{risk_percentage:.1f}%</span></td></tr>
            </table>
            
            <h3>Active Positions:</h3>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr><th>Symbol</th><th>Side</th><th>Size</th><th>Price</th></tr>
        """
        
        for pos in positions:
            html_body += f"""
                <tr>
                    <td>{pos.get('symbol', 'Unknown')}</td>
                    <td>{pos.get('side', 'Unknown')}</td>
                    <td>{pos.get('size', 0):.4f}</td>
                    <td>${pos.get('price', 0):.2f}</td>
                </tr>
            """
        
        html_body += """
            </table>
            <p><strong>Recommendation:</strong> Consider reducing position sizes or closing some positions.</p>
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

    def send_weekly_summary(self, start_date: str, end_date: str, total_trades: int, win_rate: float, total_pnl: float, best_trade: Dict, worst_trade: Dict) -> bool:
        """Send weekly trading summary"""
        subject = f"Weekly Trading Summary ({start_date} - {end_date})"
        
        body = f"""
Weekly Trading Summary
=====================

Period: {start_date} - {end_date}
Total Trades: {total_trades}
Win Rate: {win_rate:.1f}%
Total P&L: ${total_pnl:.2f}

Best Trade:
- Symbol: {best_trade.get('symbol', 'N/A')}
- P&L: ${best_trade.get('pnl', 0):.2f}
- Date: {best_trade.get('date', 'N/A')}

Worst Trade:
- Symbol: {worst_trade.get('symbol', 'N/A')}
- P&L: ${worst_trade.get('pnl', 0):.2f}
- Date: {worst_trade.get('date', 'N/A')}

Generated by Automatyczny Trading Bot
"""
        
        pnl_color = 'green' if total_pnl >= 0 else 'red'
        win_rate_color = 'green' if win_rate >= 60 else 'orange' if win_rate >= 40 else 'red'
        
        html_body = f"""
        <html>
        <body>
            <h2>📈 Weekly Trading Summary</h2>
            <h3>{start_date} - {end_date}</h3>
            
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Total Trades</strong></td><td>{total_trades}</td></tr>
                <tr><td><strong>Win Rate</strong></td><td><span style="color: {win_rate_color}; font-weight: bold">{win_rate:.1f}%</span></td></tr>
                <tr><td><strong>Total P&L</strong></td><td><span style="color: {pnl_color}; font-weight: bold">${total_pnl:.2f}</span></td></tr>
            </table>
            
            <h3>📊 Trade Performance</h3>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><th></th><th>Symbol</th><th>P&L</th><th>Date</th></tr>
                <tr>
                    <td><strong>Best Trade</strong></td>
                    <td>{best_trade.get('symbol', 'N/A')}</td>
                    <td><span style="color: green; font-weight: bold">${best_trade.get('pnl', 0):.2f}</span></td>
                    <td>{best_trade.get('date', 'N/A')}</td>
                </tr>
                <tr>
                    <td><strong>Worst Trade</strong></td>
                    <td>{worst_trade.get('symbol', 'N/A')}</td>
                    <td><span style="color: red; font-weight: bold">${worst_trade.get('pnl', 0):.2f}</span></td>
                    <td>{worst_trade.get('date', 'N/A')}</td>
                </tr>
            </table>
            
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

    def send_login_alert(self, user_email: str, ip_address: str, timestamp: str, success: bool) -> bool:
        """Send login alert notification"""
        status = "Successful" if success else "Failed"
        status_icon = "✅" if success else "❌"
        
        subject = f"Login Alert: {status} login attempt"
        
        body = f"""
Login Alert
===========

Status: {status}
User: {user_email}
IP Address: {ip_address}
Timestamp: {timestamp}

{'Login completed successfully.' if success else 'Failed login attempt detected. If this was not you, please secure your account immediately.'}

Generated by Automatyczny Trading Bot
"""
        
        status_color = 'green' if success else 'red'
        html_body = f"""
        <html>
        <body>
            <h2>{status_icon} Login Alert</h2>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Status</strong></td><td><span style="color: {status_color}; font-weight: bold">{status}</span></td></tr>
                <tr><td><strong>User</strong></td><td>{user_email}</td></tr>
                <tr><td><strong>IP Address</strong></td><td>{ip_address}</td></tr>
                <tr><td><strong>Timestamp</strong></td><td>{timestamp}</td></tr>
            </table>
            
            <p><strong>{'Login completed successfully.' if success else 'Failed login attempt detected. If this was not you, please secure your account immediately.'}</strong></p>
            
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

    def send_api_status_alert(self, exchange: str, status: str, error_message: str = None) -> bool:
        """Send API connection status alert"""
        subject = f"API Status Alert: {exchange} - {status}"
        
        body = f"""
API Status Alert
===============

Exchange: {exchange}
Status: {status}
Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        
        if error_message:
            body += f"\nError Message: {error_message}"
        
        body += "\n\nGenerated by Automatyczny Trading Bot"
        
        status_color = 'green' if status.lower() == 'connected' else 'red'
        status_icon = "✅" if status.lower() == 'connected' else "❌"
        
        html_body = f"""
        <html>
        <body>
            <h2>{status_icon} API Status Alert</h2>
            <table border="1" cellpadding="10" cellspacing="0">
                <tr><td><strong>Exchange</strong></td><td>{exchange}</td></tr>
                <tr><td><strong>Status</strong></td><td><span style="color: {status_color}; font-weight: bold">{status}</span></td></tr>
                <tr><td><strong>Timestamp</strong></td><td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
        """
        
        if error_message:
            html_body += f'<tr><td><strong>Error Message</strong></td><td><span style="color: red">{error_message}</span></td></tr>'
        
        html_body += """
            </table>
            <p><em>Generated by Automatyczny Trading Bot</em></p>
        </body>
        </html>
        """
        
        return self.send_email([self.config.admin_email], subject, body, html_body)

# Global instance
email_notifier = EmailNotifier()

# Convenience functions
def send_trade_alert(symbol: str, action: str, price: float, quantity: float, profit_loss: Optional[float] = None) -> bool:
    """Send trade alert - convenience function"""
    return email_notifier.send_trade_alert(symbol, action, price, quantity, profit_loss)

def send_system_alert(alert_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """Send system alert - convenience function"""
    return email_notifier.send_system_alert(alert_type, message, details)

def send_daily_report(trades_count: int, total_pnl: float, active_positions: int) -> bool:
    """Send daily report - convenience function"""
    return email_notifier.send_daily_report(trades_count, total_pnl, active_positions)

def test_email() -> bool:
    """Test email configuration - convenience function"""
    return email_notifier.test_email_connection()

def send_performance_alert(metric: str, current_value: float, threshold: float, time_period: str) -> bool:
    """Send performance alert when metrics exceed thresholds"""
    return email_notifier.send_performance_alert(metric, current_value, threshold, time_period)

def send_risk_alert(risk_type: str, current_risk: float, max_risk: float, positions: List[Dict]) -> bool:
    """Send risk management alert"""
    return email_notifier.send_risk_alert(risk_type, current_risk, max_risk, positions)

def send_weekly_summary(start_date: str, end_date: str, total_trades: int, win_rate: float, total_pnl: float, best_trade: Dict, worst_trade: Dict) -> bool:
    """Send weekly trading summary"""
    return email_notifier.send_weekly_summary(start_date, end_date, total_trades, win_rate, total_pnl, best_trade, worst_trade)

def send_login_alert(user_email: str, ip_address: str, timestamp: str, success: bool) -> bool:
    """Send login alert notification"""
    return email_notifier.send_login_alert(user_email, ip_address, timestamp, success)

def send_api_status_alert(exchange: str, status: str, error_message: str = None) -> bool:
    """Send API connection status alert"""
    return email_notifier.send_api_status_alert(exchange, status, error_message)
