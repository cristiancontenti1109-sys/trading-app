import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# In-memory dedup cache: {user_id+symbol+condition: datetime}
_dedup_cache: dict[str, datetime] = {}
# Daily notification count: {user_id+date: int}
_daily_counts: dict[str, int] = {}


async def send_push_notification(
    expo_push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """Send a push notification via Expo Push API."""
    if not expo_push_token or not expo_push_token.startswith("ExponentPushToken"):
        return False

    payload = {
        "to": expo_push_token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": data or {},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.json()
                if result.get("data", {}).get("status") == "ok":
                    return True
                logger.warning(f"Push notification failed: {result}")
                return False
    except Exception as e:
        logger.error(f"Push notification error: {e}")
        return False


def should_send_notification(user_id: str, symbol: str, condition: str, daily_cap: int = 20) -> bool:
    """Check dedup and daily cap before sending."""
    dedup_key = f"{user_id}:{symbol}:{condition}"
    daily_key = f"{user_id}:{datetime.utcnow().date()}"

    # Check deduplication (60 min suppression)
    if dedup_key in _dedup_cache:
        if datetime.utcnow() - _dedup_cache[dedup_key] < timedelta(minutes=60):
            return False

    # Check daily cap
    count = _daily_counts.get(daily_key, 0)
    if count >= daily_cap:
        return False

    return True


def mark_notification_sent(user_id: str, symbol: str, condition: str):
    """Record that a notification was sent."""
    dedup_key = f"{user_id}:{symbol}:{condition}"
    daily_key = f"{user_id}:{datetime.utcnow().date()}"
    _dedup_cache[dedup_key] = datetime.utcnow()
    _daily_counts[daily_key] = _daily_counts.get(daily_key, 0) + 1


def is_in_quiet_hours(quiet_start: str, quiet_end: str) -> bool:
    """Check if current time is in the user's quiet hours window."""
    try:
        now = datetime.utcnow().time()
        start_h, start_m = map(int, quiet_start.split(":"))
        end_h, end_m = map(int, quiet_end.split(":"))
        from datetime import time
        start = time(start_h, start_m)
        end = time(end_h, end_m)
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end
    except Exception:
        return False


def build_hot_notification(signal: dict) -> tuple[str, str]:
    """Build notification title and body from a HOT signal."""
    symbol = signal["symbol"]
    rec = signal["recommendation"]
    confidence = int(signal["confidence"] * 100)
    target = signal.get("target_price", 0)

    if signal.get("is_hot_confluence"):
        title = f"🔥 HOT-CONFLUENCE: {symbol}"
        body = f"{rec} signal ({confidence}% confidence) · Target: {target:,.2f}"
    else:
        title = f"⚡ HOT: {symbol}"
        body = f"{rec} signal ({confidence}% confidence) · Target: {target:,.2f}"

    return title, body
