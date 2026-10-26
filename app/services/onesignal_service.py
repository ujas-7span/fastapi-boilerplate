import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.localization import supported_locales
from app.db.session import SessionLocal
from app.models.notification import Notification
from app.services import device_service
from app.services.notification_service import render

logger = logging.getLogger(__name__)
settings = get_settings()

_REQUEST_TIMEOUT_SECONDS = 10


async def send_push(notification_id: int) -> None:
   
    if not settings.notification_enabled:
        logger.info("Push skipped for notification %s: NOTIFICATION_ENABLED is off.", notification_id)
        return
    if not settings.onesignal_app_id or not settings.onesignal_api_key:
        logger.info("Push skipped for notification %s: OneSignal app id/API key not set.", notification_id)
        return

    db = SessionLocal()
    try:
        notification = db.get(Notification, notification_id)
        if notification is None:
            logger.info("Push skipped: notification %s no longer exists.", notification_id)
            return

        device = device_service.get_device_for_user(db, notification.user_id)
        if device is None:
            logger.info(
                "Push skipped for notification %s: user %s has no registered device.",
                notification_id,
                notification.user_id,
            )
            return

        payload = _build_payload(notification, device.onesignal_player_id)
    finally:
        db.close()

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            settings.onesignal_api_url,
            json=payload,
            headers={"Authorization": f"Key {settings.onesignal_api_key}"},
        )

    if not response.is_success:
        logger.error(
            "OneSignal rejected the push for notification %s: HTTP %s %s",
            notification_id,
            response.status_code,
            response.text,
        )
        raise RuntimeError(f"OneSignal responded with HTTP {response.status_code}")

    # OneSignal answers 200 even when nothing was delivered, e.g.
    # {"id": "", "errors": ["All included players are not subscribed"]} for an unsubscribed or
    # unknown device. Retrying can't fix that, so it's logged rather than raised.
    errors = _response_errors(response)
    if errors:
        logger.warning("OneSignal did not deliver the push for notification %s: %s", notification_id, errors)
        return

    logger.info("Push sent for notification %s.", notification_id)


def _response_errors(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("errors") if isinstance(body, dict) else None


def _build_payload(notification: Notification, player_id: str) -> dict[str, Any]:
    # Users have no stored locale, so every supported language goes out at once and OneSignal
    # shows each device the one matching its own language setting ("en" is required as fallback).
    locales = supported_locales() | {"en"}
    headings = {locale: render(notification.title, locale, notification.data) for locale in locales}
    body_key = notification.description or notification.title
    contents = {locale: render(body_key, locale, notification.data) for locale in locales}

    return {
        "app_id": settings.onesignal_app_id,
        "target_channel": "push",
        "include_subscription_ids": [player_id],
        "headings": headings,
        "contents": contents,
        # Lets the app open the right screen and send `?notify_id=` to mark it read.
        "data": {
            "notification_id": notification.id,
            "type": notification.type,
            "notifiable_type": notification.notifiable_type,
            "notifiable_id": notification.notifiable_id,
        },
    }
