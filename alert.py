"""
告警通知 — 發送到 Google Chat
"""

import json
import urllib.request
from datetime import datetime
from config import AlertConfig
from logger_setup import setup_logger

logger = setup_logger("alert")


def send_google_chat_alert(service_name: str, error_message: str, response_time_ms: int = 0):
    """發送告警到 Google Chat"""
    webhook_url = AlertConfig.GOOGLE_CHAT_WEBHOOK
    if not webhook_url or webhook_url == "":
        logger.warning("Google Chat Webhook 未設定，跳過告警")
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = {
        "text": (
            f"🚨 *Server Monitor 告警*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ 時間: {now}\n"
            f"🖥️ 服務: {service_name}\n"
            f"❌ 錯誤: {error_message}\n"
            f"⏱️ 回應時間: {response_time_ms}ms\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ 已連續失敗達閾值，請立即檢查！"
        )
    }

    try:
        data = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=UTF-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"告警已發送到 Google Chat: {service_name}")
                return True
            else:
                logger.error(f"Google Chat 回應異常: {response.status}")
                return False
    except Exception as e:
        logger.error(f"發送 Google Chat 告警失敗: {e}")
        return False
