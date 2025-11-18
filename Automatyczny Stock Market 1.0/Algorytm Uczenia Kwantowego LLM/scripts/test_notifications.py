#!/usr/bin/env python
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.enhanced_notifications import (
    EnhancedNotificationSystem,
    NotificationMessage,
    NotificationChannel,
    NotificationType,
)

# The unique webhook URL generated for this test.
# You can view notifications sent to it here: https://webhook.site/#!/a6a3e14c-1d7a-4b9e-8b1a-9f4a9b9a6b9a
TEST_WEBHOOK_URL = "https://webhook.site/a6a3e14c-1d7a-4b9e-8b1a-9f4a9b9a6b9a"

async def main():
    print("--- Testing Enhanced Notification System ---")
    
    # 1. Initialize the notification system
    notifier = EnhancedNotificationSystem()
    print("Notifier initialized.")

    # 2. Configure it programmatically for this test
    # This simulates loading a configuration file.
    notifier.webhook_config['urls'] = [TEST_WEBHOOK_URL]
    print(f"Notifier configured to send to webhook: {TEST_WEBHOOK_URL}")

    # 3. Create a test notification message
    test_notification = NotificationMessage(
        title="System Test: Successful Connection",
        message="This is a test message to confirm the notification system is working.",
        notification_type=NotificationType.SYSTEM_STATUS,
        priority=5,
        channels=[NotificationChannel.WEBHOOK],
        metadata_payload={"test_id": "12345", "status": "OK"},
    )
    print("Test notification message created.")

    # 4. Send the notification
    print("Sending notification...")
    success = await notifier.send_notification(test_notification)

    if success:
        print("\n✅ [SUCCESS] Notification sent successfully!")
        print("Please check the webhook URL to see the received data:")
        print(f"https://webhook.site/#!/a6a3e14c-1d7a-4b9e-8b1a-9f4a9b9a6b9a")
    else:
        print("\n❌ [FAILURE] Failed to send notification.")

if __name__ == "__main__":
    asyncio.run(main())

