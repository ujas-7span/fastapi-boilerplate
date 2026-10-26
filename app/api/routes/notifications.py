from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import QB, get_current_user, get_db, get_qb, mark_notification_read
from app.core.config import get_settings
from app.core.localization import request_locale, translate
from app.models.notification import Notification
from app.models.user import User
from app.schemas.device import OneSignalDeviceRequest, UserDeviceResponse
from app.schemas.notification import NotificationIdsRequest, NotificationPage, UnreadCountRead
from app.services import device_service, notification_service

# No prefix: `/onesignal-player-id` sits at the API root, matching the Laravel route contract.
router = APIRouter(tags=["Notifications"], dependencies=[Depends(mark_notification_read)])

settings = get_settings()
notification_qb = get_qb(Notification)


@router.get("/notifications", response_model=NotificationPage)
def list_notifications(
    request: Request,
    # Declared here only so /docs documents and validates them — paginate() re-reads the actual
    # values straight off `request` itself (same as users.py).
    page: int = Query(default=1, ge=1, description="Ignored once `cursor` is present"),
    per_page: int = Query(
        default=settings.pagination_limit, ge=-1, le=100, description="-1 returns every record, unpaginated"
    ),
    cursor: str | None = Query(
        default=None,
        description="Opt into cursor pagination instead of page-based — use the `next_cursor`/"
        "`prev_cursor` from a previous response, not something to construct by hand.",
    ),
    direction: str | None = Query(default=None, description="'next' or 'prev', used together with `cursor`"),
    is_read: bool | None = Query(default=None, description="true = only read, false = only unread"),
    qb: QB = Depends(notification_qb),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationPage:
    return notification_service.list_for_user(db, current_user.id, qb, request, is_read)


@router.get("/notifications/unread-count", response_model=UnreadCountRead)
def unread_count(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> UnreadCountRead:
    return UnreadCountRead(unread_count=notification_service.unread_count(db, current_user.id))


@router.post("/notifications/read")
def mark_read(
    request: Request,
    payload: NotificationIdsRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    notification_service.mark_read(db, current_user.id, payload.ids if payload else None)
    return {"message": translate("notification.read_success", locale=request_locale(request))}


@router.post("/notifications/unread")
def mark_unread(
    request: Request,
    payload: NotificationIdsRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    notification_service.mark_unread(db, current_user.id, payload.ids if payload else None)
    return {"message": translate("notification.unread_success", locale=request_locale(request))}


@router.post("/onesignal-player-id", response_model=UserDeviceResponse)
def set_onesignal_device(
    payload: OneSignalDeviceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserDeviceResponse:
    device = device_service.upsert_device(db, current_user.id, payload)
    return UserDeviceResponse(
        message=translate("device.onesignal_saved", locale=request_locale(request)),
        data=device_service.to_user_device_read(device),
    )
