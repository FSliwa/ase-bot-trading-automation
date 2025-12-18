"""
Alert Service - Send trading alerts via Resend SMTP
Supports email notifications for:
- Trade executions (BUY/SELL)
- Stop Loss triggers
- Take Profit triggers
- Trailing Stop updates
- Position reevaluations
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """Configuration for alert service."""
    resend_api_key: str
    from_email: str = "ASE Bot <alerts@asebot.io>"
    enabled: bool = True


class AlertService:
    """
    Alert service using Resend API for email notifications.
    """
    
    RESEND_API_URL = "https://api.resend.com/emails"
    
    def __init__(self, api_key: str, from_email: str = "ASE Bot <noreply@resend.dev>"):
        """
        Initialize alert service with Resend API key.
        
        Args:
            api_key: Resend API key (re_...)
            from_email: Sender email address
        """
        self.api_key = api_key
        self.from_email = from_email
        self.enabled = True
        logger.info("📧 AlertService initialized with Resend API")
    
    async def send_email(
        self, 
        to_email: str, 
        subject: str, 
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send email via Resend API.
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body (optional)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug("Alerts disabled, skipping email")
            return False
        
        if not to_email:
            logger.warning("No recipient email provided")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            
            if text_content:
                payload["text"] = text_content
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.RESEND_API_URL,
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"📧 Email sent to {to_email}: {subject}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Failed to send email: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    async def send_trade_alert(
        self,
        user_email: str,
        symbol: str,
        action: str,
        price: float,
        quantity: float,
        pnl: Optional[float] = None,
        reason: str = ""
    ) -> bool:
        """Send trade execution alert."""
        emoji = "🟢" if action.upper() in ["BUY", "LONG"] else "🔴"
        pnl_text = f"<br><strong>P&L:</strong> ${pnl:.2f}" if pnl else ""
        
        subject = f"{emoji} ASE Bot: {action.upper()} {symbol}"
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">{emoji} Trade Executed</h1>
            </div>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 0 0 10px 10px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Symbol:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{symbol}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Action:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{action.upper()}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Quantity:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{quantity}</td>
                    </tr>
                    {f'<tr><td style="padding: 10px;"><strong>P&L:</strong></td><td style="padding: 10px; color: {"green" if pnl and pnl > 0 else "red"};">${pnl:.2f}</td></tr>' if pnl else ''}
                </table>
                {f'<p style="margin-top: 15px; color: #666;"><em>{reason}</em></p>' if reason else ''}
                <p style="margin-top: 20px; color: #999; font-size: 12px;">
                    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </div>
        """
        
        return await self.send_email(user_email, subject, html)
    
    async def send_sl_alert(
        self,
        user_email: str,
        symbol: str,
        entry_price: float,
        sl_price: float,
        current_price: float,
        pnl: float,
        quantity: float
    ) -> bool:
        """Send Stop Loss triggered alert."""
        subject = f"🛑 ASE Bot: Stop Loss Triggered - {symbol}"
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">🛑 Stop Loss Triggered</h1>
            </div>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 18px; color: #e74c3c;">Position closed to protect your capital</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Symbol:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{symbol}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Entry Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${entry_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Stop Loss:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${sl_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Exit Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${current_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Quantity:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{quantity}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px;"><strong>P&L:</strong></td>
                        <td style="padding: 10px; color: red; font-weight: bold;">${pnl:.2f}</td>
                    </tr>
                </table>
                <p style="margin-top: 20px; color: #999; font-size: 12px;">
                    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </div>
        """
        
        return await self.send_email(user_email, subject, html)
    
    async def send_tp_alert(
        self,
        user_email: str,
        symbol: str,
        entry_price: float,
        tp_price: float,
        current_price: float,
        pnl: float,
        quantity: float,
        partial: bool = False,
        level: int = 0
    ) -> bool:
        """Send Take Profit triggered alert."""
        tp_type = f"Partial TP (Level {level})" if partial else "Take Profit"
        subject = f"🎯 ASE Bot: {tp_type} Hit - {symbol}"
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">🎯 {tp_type} Hit!</h1>
            </div>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 18px; color: #27ae60;">Congratulations! Your target was reached.</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Symbol:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{symbol}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Entry Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${entry_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Target Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${tp_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Exit Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${current_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Quantity:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{quantity}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px;"><strong>P&L:</strong></td>
                        <td style="padding: 10px; color: green; font-weight: bold;">+${pnl:.2f}</td>
                    </tr>
                </table>
                <p style="margin-top: 20px; color: #999; font-size: 12px;">
                    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </div>
        """
        
        return await self.send_email(user_email, subject, html)
    
    async def send_trailing_update_alert(
        self,
        user_email: str,
        symbol: str,
        old_sl: float,
        new_sl: float,
        current_price: float,
        profit_pct: float
    ) -> bool:
        """Send Trailing Stop update alert."""
        subject = f"📈 ASE Bot: Trailing Stop Updated - {symbol}"
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #3498db 0%, #2980b9 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">📈 Trailing Stop Updated</h1>
            </div>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 18px; color: #3498db;">Your stop loss has been raised to lock in profits!</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Symbol:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{symbol}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Current Price:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${current_price:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Old Stop Loss:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">${old_sl:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>New Stop Loss:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; color: #27ae60; font-weight: bold;">${new_sl:,.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px;"><strong>Current Profit:</strong></td>
                        <td style="padding: 10px; color: green; font-weight: bold;">+{profit_pct:.2f}%</td>
                    </tr>
                </table>
                <p style="margin-top: 20px; color: #999; font-size: 12px;">
                    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </div>
        """
        
        return await self.send_email(user_email, subject, html)
    
    async def send_reevaluation_alert(
        self,
        user_email: str,
        symbol: str,
        reevaluation_type: str,
        details: Dict[str, Any]
    ) -> bool:
        """Send position reevaluation alert."""
        type_emoji = {
            'trailing_update': '📈',
            'partial_tp': '🎯',
            'dynamic_sl': '🛡️',
            'time_check': '⏰',
            'manual': '👤'
        }.get(reevaluation_type, '🔄')
        
        subject = f"{type_emoji} ASE Bot: Position Reevaluated - {symbol}"
        
        details_html = "".join([
            f'<tr><td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>{k}:</strong></td>'
            f'<td style="padding: 10px; border-bottom: 1px solid #ddd;">{v}</td></tr>'
            for k, v in details.items()
        ])
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #9b59b6 0%, #8e44ad 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">{type_emoji} Position Reevaluated</h1>
            </div>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px;"><strong>Type:</strong> {reevaluation_type.replace('_', ' ').title()}</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>Symbol:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{symbol}</td>
                    </tr>
                    {details_html}
                </table>
                <p style="margin-top: 20px; color: #999; font-size: 12px;">
                    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </div>
        """
        
        return await self.send_email(user_email, subject, html)


# Global instance (initialized on first use)
_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get or create the global alert service instance."""
    global _alert_service
    if _alert_service is None:
        # Use the Resend API key
        _alert_service = AlertService(
            api_key="re_b5Uy7ZAs_QLEPdnC1hQsg8y3hXCyPNR24",
            from_email="ASE Bot <onboarding@resend.dev>"
        )
    return _alert_service


def set_alert_service(service: AlertService):
    """Set a custom alert service instance."""
    global _alert_service
    _alert_service = service
