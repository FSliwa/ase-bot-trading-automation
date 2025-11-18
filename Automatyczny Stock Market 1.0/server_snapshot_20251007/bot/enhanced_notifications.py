"""
Enhanced Notification System
Obsługuje Telegram, Discord, Slack, Email i SMS notifications
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json

# Try to import notification libraries
try:
    from telegram import Bot
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

try:
    import discord
    from discord import Webhook, RequestsWebhookAdapter
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

import requests

logger = logging.getLogger(__name__)

class NotificationType(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    TRADE_SIGNAL = "trade_signal"
    TRADE_EXECUTED = "trade_executed"
    PROFIT_LOSS = "profit_loss"
    SYSTEM_STATUS = "system_status"

class NotificationChannel(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"

@dataclass
class NotificationConfig:
    enabled: bool = True
    channels: List[NotificationChannel] = None
    min_priority: int = 1  # 1-5 scale
    rate_limit: int = 10  # max notifications per minute
    quiet_hours: tuple = None  # (start_hour, end_hour)

@dataclass
class NotificationMessage:
    title: str
    message: str
    notification_type: NotificationType
    priority: int = 3  # 1-5 scale
    channels: List[NotificationChannel] = None
    metadata_payload: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.channels is None:
            self.channels = [NotificationChannel.TELEGRAM]
        if self.metadata_payload is None:
            self.metadata_payload = {}

    @property
    def metadata(self) -> Dict[str, Any]:
        """Backward-compatible alias for metadata_payload."""
        return self.metadata_payload

    @metadata.setter
    def metadata(self, value: Optional[Dict[str, Any]]) -> None:
        self.metadata_payload = value or {}

class EnhancedNotificationSystem:
    def __init__(self, config_path: str = None):
        self.config = NotificationConfig()
        self.rate_limiter = {}
        self.notification_history = []
        
        # Configuration for different services
        self.telegram_config = {
            'bot_token': None,
            'chat_ids': [],
            'parse_mode': 'Markdown'
        }
        
        self.discord_config = {
            'webhook_urls': [],
            'username': 'Trading Bot',
            'avatar_url': None
        }
        
        self.slack_config = {
            'token': None,
            'channels': [],
            'username': 'Trading Bot'
        }
        
        self.email_config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': None,
            'password': None,
            'recipients': []
        }
        
        self.sms_config = {
            'twilio_sid': None,
            'twilio_token': None,
            'from_number': None,
            'to_numbers': []
        }
        
        self.webhook_config = {
            'urls': [],
            'headers': {'Content-Type': 'application/json'}
        }
        
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: str):
        """Ładuje konfigurację z pliku"""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Update configurations
            if 'telegram' in config_data:
                self.telegram_config.update(config_data['telegram'])
            if 'discord' in config_data:
                self.discord_config.update(config_data['discord'])
            if 'slack' in config_data:
                self.slack_config.update(config_data['slack'])
            if 'email' in config_data:
                self.email_config.update(config_data['email'])
            if 'sms' in config_data:
                self.sms_config.update(config_data['sms'])
            if 'webhook' in config_data:
                self.webhook_config.update(config_data['webhook'])
                
            logger.info("Notification configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load notification config: {e}")
    
    async def send_notification(self, notification: NotificationMessage) -> bool:
        """Wysyła notification przez wybrane kanały"""
        if not self._should_send_notification(notification):
            return False
        
        success = True
        
        for channel in notification.channels:
            try:
                if channel == NotificationChannel.TELEGRAM:
                    await self._send_telegram(notification)
                elif channel == NotificationChannel.DISCORD:
                    await self._send_discord(notification)
                elif channel == NotificationChannel.SLACK:
                    await self._send_slack(notification)
                elif channel == NotificationChannel.EMAIL:
                    await self._send_email(notification)
                elif channel == NotificationChannel.SMS:
                    await self._send_sms(notification)
                elif channel == NotificationChannel.WEBHOOK:
                    await self._send_webhook(notification)
            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {e}")
                success = False
        
        # Store in history
        self.notification_history.append(notification)
        
        # Keep only last 1000 notifications
        if len(self.notification_history) > 1000:
            self.notification_history = self.notification_history[-1000:]
        
        return success
    
    def _should_send_notification(self, notification: NotificationMessage) -> bool:
        """Sprawdza czy notification powinien być wysłany"""
        # Check if notifications are enabled
        if not self.config.enabled:
            return False
        
        # Check priority
        if notification.priority < self.config.min_priority:
            return False
        
        # Check rate limiting
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        
        if minute_key not in self.rate_limiter:
            self.rate_limiter[minute_key] = 0
        
        if self.rate_limiter[minute_key] >= self.config.rate_limit:
            return False
        
        self.rate_limiter[minute_key] += 1
        
        # Check quiet hours
        if self.config.quiet_hours:
            start_hour, end_hour = self.config.quiet_hours
            current_hour = now.hour
            
            if start_hour <= end_hour:
                if start_hour <= current_hour < end_hour:
                    return False
            else:  # Quiet hours span midnight
                if current_hour >= start_hour or current_hour < end_hour:
                    return False
        
        return True
    
    async def _send_telegram(self, notification: NotificationMessage):
        """Wysyła notification przez Telegram"""
        if not TELEGRAM_AVAILABLE or not self.telegram_config['bot_token']:
            return
        
        bot = Bot(token=self.telegram_config['bot_token'])
        
        # Format message
        message = self._format_telegram_message(notification)
        
        for chat_id in self.telegram_config['chat_ids']:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Telegram notification sent to {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
    
    def _format_telegram_message(self, notification: NotificationMessage) -> str:
        """Formatuje wiadomość dla Telegram"""
        emoji_map = {
            NotificationType.INFO: "ℹ️",
            NotificationType.WARNING: "⚠️",
            NotificationType.ERROR: "❌",
            NotificationType.SUCCESS: "✅",
            NotificationType.TRADE_SIGNAL: "📊",
            NotificationType.TRADE_EXECUTED: "💹",
            NotificationType.PROFIT_LOSS: "💰",
            NotificationType.SYSTEM_STATUS: "🔧"
        }
        
        emoji = emoji_map.get(notification.notification_type, "📋")
        
        message = f"{emoji} *{notification.title}*\n\n"
        message += f"{notification.message}\n\n"
        message += f"🕐 {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        message += f"📊 Priority: {notification.priority}/5"
        
        if notification.metadata_payload:
            message += "\n\n*Details:*\n"
            for key, value in notification.metadata_payload.items():
                message += f"• {key}: `{value}`\n"
        
        return message
    
    async def _send_discord(self, notification: NotificationMessage):
        """Wysyła notification przez Discord webhook"""
        if not DISCORD_AVAILABLE or not self.discord_config['webhook_urls']:
            return
        
        # Format embed
        embed = self._format_discord_embed(notification)
        
        for webhook_url in self.discord_config['webhook_urls']:
            try:
                webhook = Webhook.from_url(webhook_url, adapter=RequestsWebhookAdapter())
                webhook.send(
                    username=self.discord_config['username'],
                    avatar_url=self.discord_config.get('avatar_url'),
                    embed=embed
                )
                logger.info(f"Discord notification sent to {webhook_url}")
            except Exception as e:
                logger.error(f"Failed to send Discord message: {e}")
    
    def _format_discord_embed(self, notification: NotificationMessage):
        """Formatuje embed dla Discord"""
        color_map = {
            NotificationType.INFO: 0x3498db,
            NotificationType.WARNING: 0xf39c12,
            NotificationType.ERROR: 0xe74c3c,
            NotificationType.SUCCESS: 0x2ecc71,
            NotificationType.TRADE_SIGNAL: 0x9b59b6,
            NotificationType.TRADE_EXECUTED: 0x1abc9c,
            NotificationType.PROFIT_LOSS: 0xf1c40f,
            NotificationType.SYSTEM_STATUS: 0x95a5a6
        }
        
        embed = discord.Embed(
            title=notification.title,
            description=notification.message,
            color=color_map.get(notification.notification_type, 0x3498db),
            timestamp=notification.timestamp
        )
        
        embed.add_field(name="Priority", value=f"{notification.priority}/5", inline=True)
        embed.add_field(name="Type", value=notification.notification_type.value, inline=True)
        
        if notification.metadata_payload:
            for key, value in notification.metadata_payload.items():
                embed.add_field(name=key, value=str(value), inline=True)
        
        return embed
    
    async def _send_slack(self, notification: NotificationMessage):
        """Wysyła notification przez Slack"""
        if not SLACK_AVAILABLE or not self.slack_config['token']:
            return
        
        client = WebClient(token=self.slack_config['token'])
        
        # Format message
        blocks = self._format_slack_blocks(notification)
        
        for channel in self.slack_config['channels']:
            try:
                response = client.chat_postMessage(
                    channel=channel,
                    blocks=blocks,
                    username=self.slack_config['username']
                )
                logger.info(f"Slack notification sent to {channel}")
            except SlackApiError as e:
                logger.error(f"Failed to send Slack message: {e}")
    
    def _format_slack_blocks(self, notification: NotificationMessage) -> List[Dict]:
        """Formatuje blocks dla Slack"""
        emoji_map = {
            NotificationType.INFO: ":information_source:",
            NotificationType.WARNING: ":warning:",
            NotificationType.ERROR: ":x:",
            NotificationType.SUCCESS: ":white_check_mark:",
            NotificationType.TRADE_SIGNAL: ":chart_with_upwards_trend:",
            NotificationType.TRADE_EXECUTED: ":moneybag:",
            NotificationType.PROFIT_LOSS: ":money_with_wings:",
            NotificationType.SYSTEM_STATUS: ":gear:"
        }
        
        emoji = emoji_map.get(notification.notification_type, ":memo:")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.message
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Priority: {notification.priority}/5 | {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            }
        ]
        
        if notification.metadata_payload:
            fields = []
            for key, value in notification.metadata_payload.items():
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:* {value}"
                })
            
            blocks.append({
                "type": "section",
                "fields": fields
            })
        
        return blocks
    
    async def _send_email(self, notification: NotificationMessage):
        """Wysyła notification przez Email"""
        logger.warning("Email notifications temporarily disabled - import conflicts")
        return
    
    def _format_email_body(self, notification: NotificationMessage) -> str:
        """Formatuje HTML body dla email"""
        color_map = {
            NotificationType.INFO: "#3498db",
            NotificationType.WARNING: "#f39c12",
            NotificationType.ERROR: "#e74c3c",
            NotificationType.SUCCESS: "#2ecc71",
            NotificationType.TRADE_SIGNAL: "#9b59b6",
            NotificationType.TRADE_EXECUTED: "#1abc9c",
            NotificationType.PROFIT_LOSS: "#f1c40f",
            NotificationType.SYSTEM_STATUS: "#95a5a6"
        }
        
        color = color_map.get(notification.notification_type, "#3498db")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <div style="border-left: 4px solid {color}; padding-left: 20px;">
                <h2 style="color: {color}; margin-top: 0;">{notification.title}</h2>
                <p style="font-size: 16px; line-height: 1.5;">{notification.message}</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p><strong>Type:</strong> {notification.notification_type.value}</p>
                    <p><strong>Priority:</strong> {notification.priority}/5</p>
                    <p><strong>Timestamp:</strong> {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
        """
        
        if notification.metadata_payload:
            html += """
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px;">
                    <h4>Additional Details:</h4>
                    <ul>
            """
            for key, value in notification.metadata_payload.items():
                html += f"<li><strong>{key}:</strong> {value}</li>"
            html += "</ul></div>"
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html
    
    async def _send_sms(self, notification: NotificationMessage):
        """Wysyła notification przez SMS"""
        if not TWILIO_AVAILABLE or not self.sms_config['twilio_sid']:
            return
        
        try:
            client = TwilioClient(
                self.sms_config['twilio_sid'],
                self.sms_config['twilio_token']
            )
            
            # Format SMS message (limit to 160 characters)
            message = f"{notification.title}: {notification.message}"
            if len(message) > 160:
                message = message[:157] + "..."
            
            for to_number in self.sms_config['to_numbers']:
                client.messages.create(
                    body=message,
                    from_=self.sms_config['from_number'],
                    to=to_number
                )
                logger.info(f"SMS notification sent to {to_number}")
        except Exception as e:
            logger.error(f"Failed to send SMS notification: {e}")
    
    async def _send_webhook(self, notification: NotificationMessage):
        """Wysyła notification przez webhook"""
        if not self.webhook_config['urls']:
            return
        
        payload = {
            'title': notification.title,
            'message': notification.message,
            'type': notification.notification_type.value,
            'priority': notification.priority,
            'timestamp': notification.timestamp.isoformat(),
            'metadata': notification.metadata_payload
        }
        
        for url in self.webhook_config['urls']:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.webhook_config['headers'],
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Webhook notification sent to {url}")
            except Exception as e:
                logger.error(f"Failed to send webhook notification to {url}: {e}")
    
    # Convenience methods for common notifications
    async def notify_trade_signal(self, symbol: str, signal: str, confidence: float, metadata: Dict = None):
        """Wysyła notification o sygnale tradingowym"""
        notification = NotificationMessage(
            title=f"Trade Signal: {signal} {symbol}",
            message=f"Confidence: {confidence:.2%}",
            notification_type=NotificationType.TRADE_SIGNAL,
            priority=4,
            metadata_payload=metadata or {}
        )
        await self.send_notification(notification)
    
    async def notify_trade_executed(self, symbol: str, side: str, quantity: float, price: float):
        """Wysyła notification o wykonanej transakcji"""
        notification = NotificationMessage(
            title=f"Trade Executed: {side} {symbol}",
            message=f"Quantity: {quantity} at {price}",
            notification_type=NotificationType.TRADE_EXECUTED,
            priority=5,
            metadata_payload={
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price
            }
        )
        await self.send_notification(notification)
    
    async def notify_profit_loss(self, symbol: str, pnl: float, pnl_percent: float):
        """Wysyła notification o zysku/stracie"""
        notification = NotificationMessage(
            title=f"P&L Update: {symbol}",
            message=f"PnL: {pnl:.2f} ({pnl_percent:.2%})",
            notification_type=NotificationType.PROFIT_LOSS,
            priority=4,
            metadata_payload={
                'symbol': symbol,
                'pnl': pnl,
                'pnl_percent': pnl_percent
            }
        )
        await self.send_notification(notification)
    
    async def notify_system_status(self, status: str, details: str = ""):
        """Wysyła notification o statusie systemu"""
        notification = NotificationMessage(
            title=f"System Status: {status}",
            message=details,
            notification_type=NotificationType.SYSTEM_STATUS,
            priority=3
        )
        await self.send_notification(notification)
    
    def get_notification_history(self, limit: int = 100) -> List[NotificationMessage]:
        """Zwraca historię notifications"""
        return self.notification_history[-limit:]
    
    def clear_notification_history(self):
        """Czyści historię notifications"""
        self.notification_history.clear()

# Singleton instance
_notification_system = None

def get_notification_system() -> EnhancedNotificationSystem:
    global _notification_system
    if _notification_system is None:
        _notification_system = EnhancedNotificationSystem()
    return _notification_system
