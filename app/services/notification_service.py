import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import Select, delete, func, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.localization import request_locale, translate
from app.core.queue import get_or_create_redis_pool
from app.db.base import QB
from app.db.pagination import paginate
from app.models.notification import Notification
from app.schemas.notification import NotificationPage, NotificationRead, NotificationSender

logger = logging.getLogger(__name__)
settings = get_settings()


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: str | None,
    title_key: str,
    description_key: str | None = None,
    data: dict[str, Any] | None = None,
    sent_by: int | None = None,
    notifiable_type: str | None = None,
    notifiable_id: int | None = None,
) -> Notification:
    """
        Stores one in-app notification — the equivalent of Laravel's custom `DatabaseChannel`.
        
    """
    notification = Notification(
        user_id=user_id,
        sent_by=sent_by,
        title=title_key,
        description=description_key,
        type=type,
        notifiable_type=notifiable_type,
        notifiable_id=notifiable_id,
        data=data,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


async def notify(
    db: Session,
    *,
    user_id: int,
    type: str | None,
    title_key: str,
    description_key: str | None = None,
    data: dict[str, Any] | None = None,
    sent_by: int | None = None,
    notifiable_type: str | None = None,
    notifiable_id: int | None = None,
) -> Notification:
    """The one entry point for sending a notification: stores it, then queues the OneSignal push
    when `NOTIFICATION_ENABLED` is on. The push job itself skips users with no registered device.

    The row is committed before Redis is touched, so a queue outage raises *after* the in-app
    notification already exists — callers that must not fail on that should catch and log.
    """
    notification = create_notification(
        db,
        user_id=user_id,
        type=type,
        title_key=title_key,
        description_key=description_key,
        data=data,
        sent_by=sent_by,
        notifiable_type=notifiable_type,
        notifiable_id=notifiable_id,
    )

    if settings.notification_enabled:
        redis = await get_or_create_redis_pool()
        await redis.enqueue_job("send_push_notification", notification_id=notification.id)

    return notification


def list_for_user(
    db: Session, user_id: int, qb: QB, request: Request, is_read: bool | None = None
) -> NotificationPage:
    base_stmt = _scoped_to_read_state(select(Notification).where(Notification.user_id == user_id), is_read)
    locale = request_locale(request)
    return paginate(db, base_stmt, request, qb, lambda notification: to_notification_read(notification, locale))


def unread_count(db: Session, user_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return db.scalar(stmt) or 0


def mark_read(db: Session, user_id: int, ids: list[int] | None = None) -> None:
    """Marks the caller's unread notifications read — only `ids` if given, otherwise all of them."""
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=datetime.now(UTC)))
    db.commit()


def mark_unread(db: Session, user_id: int, ids: list[int] | None = None) -> None:
    """Marks the caller's read notifications unread — only `ids` if given, otherwise all of them."""
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_not(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=None))
    db.commit()


def mark_one_read(db: Session, user_id: int, notification_id: int) -> None:
    """Backs the `?notify_id=` auto-read dependency (Laravel's MarkNotificationsAsRead middleware)."""
    mark_read(db, user_id, [notification_id])


def prune_old_notifications(db: Session) -> int:
    """Deletes notifications older than `NOTIFICATION_RETENTION_DAYS`, read or not."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.notification_retention_days)
    result = db.execute(delete(Notification).where(Notification.created_at < cutoff))
    db.commit()

    deleted = result.rowcount
    logger.info(
        "Notification cleanup: removed %d notification(s) older than %d day(s).",
        deleted,
        settings.notification_retention_days,
    )
    return deleted


def render(key: str | None, locale: str, data: dict[str, Any] | None) -> str | None:
    """Translates a stored key with its `data` params. A row whose `data` is missing a placeholder
    still renders (unformatted) instead of breaking the whole listing with a 500.
    """
    if key is None:
        return None
    try:
        return translate(key, locale, **(data or {}))
    except (KeyError, IndexError, ValueError):
        logger.warning("Notification key %r could not be formatted with its data params.", key)
        return translate(key, locale)


def to_notification_read(notification: Notification, locale: str) -> NotificationRead:
    # Same unloaded-check as to_user_read: `sender` is only serialized when ?include=sender
    # eager-loaded it, so a page never lazy-loads one sender per row.
    sender = None
    if "sender" not in sa_inspect(notification).unloaded and notification.sender is not None:
        sender = NotificationSender(id=notification.sender.id, name=notification.sender.name)

    return NotificationRead(
        id=notification.id,
        user_id=notification.user_id,
        sent_by=notification.sent_by,
        title=render(notification.title, locale, notification.data) or "",
        description=render(notification.description, locale, notification.data),
        type=notification.type,
        notifiable_type=notification.notifiable_type,
        notifiable_id=notification.notifiable_id,
        data=notification.data,
        read_at=notification.read_at,
        created_at=notification.created_at,
        sender=sender,
    )


def _scoped_to_read_state(stmt: Select, is_read: bool | None) -> Select:
    if is_read is True:
        return stmt.where(Notification.read_at.is_not(None))
    if is_read is False:
        return stmt.where(Notification.read_at.is_(None))
    return stmt
