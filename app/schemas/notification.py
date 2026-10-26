from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class NotificationSender(BaseModel):
    id: int
    name: str


class NotificationRead(BaseModel):
    id: int
    user_id: int
    sent_by: int | None
    # Already translated into the request's `locale` — the stored values are translation keys.
    title: str
    description: str | None
    type: str | None
    notifiable_type: str | None
    notifiable_id: int | None
    data: dict[str, Any] | None
    read_at: datetime | None
    created_at: datetime
    # Only populated with `?include=sender`.
    sender: NotificationSender | None = None


class NotificationIdsRequest(BaseModel):
    ids: list[int] | None = None


class UnreadCountRead(BaseModel):
    unread_count: int


NotificationPage = PaginatedResponse[NotificationRead]
