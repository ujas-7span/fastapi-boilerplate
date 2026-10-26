from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user_device import UserDevice
from app.schemas.device import OneSignalDeviceRequest, UserDeviceRead


def get_device_for_user(db: Session, user_id: int) -> UserDevice | None:
    return db.scalar(select(UserDevice).where(UserDevice.user_id == user_id))


def upsert_device(db: Session, user_id: int, payload: OneSignalDeviceRequest) -> UserDevice:
    device = get_device_for_user(db, user_id)
    if device is None:
        device = UserDevice(user_id=user_id)
        db.add(device)

    device.onesignal_player_id = payload.onesignal_player_id
    device.device_id = payload.device_id
    device.device_type = payload.device_type

    db.commit()
    db.refresh(device)
    return device


def delete_device(db: Session, user_id: int, onesignal_player_id: str) -> None:
    """Scoped to `user_id` as well as the player id, so one user's logout can never remove a
    device registered to someone else.
    """
    db.execute(
        delete(UserDevice).where(
            UserDevice.user_id == user_id, UserDevice.onesignal_player_id == onesignal_player_id
        )
    )
    db.commit()


def to_user_device_read(device: UserDevice) -> UserDeviceRead:
    return UserDeviceRead(
        id=device.id,
        user_id=device.user_id,
        onesignal_player_id=device.onesignal_player_id,
        device_id=device.device_id,
        device_type=device.device_type,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )
