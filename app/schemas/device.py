from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OneSignalDeviceRequest(BaseModel):
    onesignal_player_id: str = Field(min_length=1, max_length=255)
    device_id: str | None = Field(default=None, max_length=255)
    device_type: Literal["android", "ios", "web"] | None = None


class UserDeviceRead(BaseModel):
    id: int
    user_id: int
    onesignal_player_id: str
    device_id: str | None
    device_type: str | None
    created_at: datetime
    updated_at: datetime


class UserDeviceResponse(BaseModel):
    message: str
    data: UserDeviceRead
