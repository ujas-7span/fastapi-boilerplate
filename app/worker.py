from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import email_service, notification_service, onesignal_service, token_cleanup_service

settings = get_settings()


async def send_password_reset_email(
    _ctx: dict[str, Any], *, name: str, email: str, reset_link: str, locale: str
) -> None:
    await email_service.send_password_reset_email(name=name, email=email, reset_link=reset_link, locale=locale)


async def send_push_notification(_ctx: dict[str, Any], *, notification_id: int) -> None:
    await onesignal_service.send_push(notification_id)


async def cleanup_expired_tokens(_ctx: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        token_cleanup_service.cleanup_expired_tokens(db)
    finally:
        db.close()


async def prune_old_notifications(_ctx: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        notification_service.prune_old_notifications(db)
    finally:
        db.close()


class WorkerSettings:
    functions = [send_password_reset_email, send_push_notification]
    # The arq worker process itself is the scheduler here — same one-cron-entry-drives-everything
    # model as Laravel's `schedule:run`, except the "entry" is just this worker staying up.
    cron_jobs = [
        cron(cleanup_expired_tokens, hour=3, minute=0),
        cron(prune_old_notifications, hour=3, minute=30),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
