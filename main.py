from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import socketio

import auth
import database
import models
import schemas
import utils

from routers import (
    admin_router,
    auth_router,
    messages_router,
    notifications_router,
    payments_router,
    requests_router,
    users_router,
)


def _ensure_runtime_directories() -> None:
    os.makedirs("uploads/chat", exist_ok=True)


async def _create_default_admins() -> None:
    admins = [
        {"name": "Platform Administrator", "email": "admin@cvru.ac.in", "password": "admin@123"},
        {"name": "Platform Administrator 82", "email": "admin82@cvrcp.ac.in", "password": "admin82@cgu"},
    ]
    for admin_info in admins:
        existing = await models.User.find_one(models.User.email == admin_info["email"])
        if existing:
            continue
        new_admin = models.User(
            name=admin_info["name"],
            email=admin_info["email"],
            hashed_password=auth.get_password_hash(admin_info["password"]),
            plain_password=admin_info["password"],
            role="admin",
            phone_number="0000000000",
            is_verified=True,
            is_suspended=False,
        )
        await new_admin.insert()
        print(f"Admin user created: {admin_info['email']}")


async def _on_startup() -> None:
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "acadmate")
    try:
        await database.init_db()
        # Create default system settings if none exist
        if await models.SystemSettings.find_one() is None:
            await models.SystemSettings().insert()
        await _create_default_admins()
        print(f"Startup completed. MongoDB: {db_name}")
    except Exception as exc:
        raise RuntimeError(
            f"Database initialization failed. Ensure MONGO_URL is set correctly. "
            f"Current: {mongo_url} / {db_name}\n{exc}"
        ) from exc


_ensure_runtime_directories()
fastapi_app = FastAPI(title="AcadMate API")

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://acadmate-xi.vercel.app",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
fastapi_app.mount("/static", StaticFiles(directory="frontend"), name="static")

fastapi_app.include_router(auth_router.router, prefix="/api/v1/auth")
fastapi_app.include_router(users_router.router, prefix="/api/v1/users")
fastapi_app.include_router(requests_router.router, prefix="/api/v1")
fastapi_app.include_router(messages_router.router, prefix="/api/v1")
fastapi_app.include_router(admin_router.admin_router, prefix="/api/v1")
fastapi_app.include_router(notifications_router.router, prefix="/api/v1")
fastapi_app.include_router(payments_router.payments_router, prefix="/api/v1")


@fastapi_app.api_route("/", methods=["GET", "HEAD", "OPTIONS"])
async def read_root():
    return {"message": "Welcome to AcadMate API", "status": "running"}


@fastapi_app.api_route("/healthz", methods=["GET", "HEAD", "OPTIONS"])
async def healthcheck():
    return {"status": "ok"}


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = socketio.ASGIApp(sio, fastapi_app, on_startup=_on_startup)


@sio.event
async def join_room(sid, data):
    room = str(data["request_id"])
    await sio.enter_room(sid, room)
    print(f"[Socket.IO] {sid} joined room {room}")


@sio.event
async def send_message(sid, data):
    room = str(data["request_id"])
    await sio.emit("new_message", data, room=room, skip_sid=sid)
    print(f"[Socket.IO] Message relayed in room {room} (skipped {sid})")
