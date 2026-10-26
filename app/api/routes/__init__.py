from fastapi import APIRouter

from app.api.routes import auth, categories, media, notifications, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(categories.router)
api_router.include_router(media.router)
api_router.include_router(notifications.router)
