from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List
import socketio
import os

# Important: Core imports before routers to avoid initialization order issues
import models, schemas, auth, database, utils

# Router imports
from routers import auth_router, requests_router, messages_router, admin_router, users_router, notifications_router

def _initialize_database() -> None:
    try:
        models.Base.metadata.create_all(bind=database.engine)
    except SQLAlchemyError:
        database_url = os.getenv("DATABASE_URL", "<not set>")
        # Avoid printing credentials while still showing the target host/db.
        safe_target = database_url.split("@")[-1] if "@" in database_url else database_url
        raise RuntimeError(
            "Database initialization failed. Ensure PostgreSQL is running and "
            f"`DATABASE_URL` is correct. Current target: {safe_target}"
        ) from None


def _run_migrations() -> None:
    """Add new columns to existing tables that create_all() won't handle."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS plain_password VARCHAR",
    ]
    try:
        with database.engine.connect() as conn:
            for sql in migrations:
                conn.execute(text(sql))
            conn.commit()
        print("Database migrations applied successfully.")
    except Exception as e:
        print(f"Migration warning (non-fatal): {e}")


# Create DB tables + run migrations
_initialize_database()
_run_migrations()

def _create_default_admins() -> None:
    """Create default admin accounts if they don't already exist."""
    admins = [
        {"name": "Platform Administrator", "email": "admin@cvru.ac.in", "password": "admin@123"},
        {"name": "Platform Administrator 82", "email": "admin82@cvrcp.ac.in", "password": "admin82@cgu"},
    ]
    db = database.SessionLocal()
    try:
        for admin_info in admins:
            existing = db.query(models.User).filter(models.User.email == admin_info["email"]).first()
            if not existing:
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
                db.add(new_admin)
                db.commit()
                print(f"Admin user created: {admin_info['email']}")
    except Exception as e:
        db.rollback()
        print(f"Error creating admin users: {e}")
    finally:
        db.close()

_create_default_admins()

# Ensure upload directories exist
os.makedirs("uploads/chat", exist_ok=True)

fastapi_app = FastAPI(title="AcadMate API")

# Configure CORS
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

# Mount uploads directory
fastapi_app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Mount frontend static files
fastapi_app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Include Routers with /api/v1 prefix
fastapi_app.include_router(auth_router.router, prefix="/api/v1/auth")
fastapi_app.include_router(users_router.router, prefix="/api/v1/users")
fastapi_app.include_router(requests_router.router, prefix="/api/v1")
fastapi_app.include_router(messages_router.router, prefix="/api/v1")
fastapi_app.include_router(admin_router.admin_router, prefix="/api/v1")
fastapi_app.include_router(notifications_router.router, prefix="/api/v1")

# Socket.io setup — wraps FastAPI so `/socket.io/` is handled
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = socketio.ASGIApp(sio, fastapi_app)

@fastapi_app.get("/")
def read_root():
    return {"message": "Welcome to AcadMate API", "status": "running"}

# Socket Events
@sio.event
async def join_room(sid, data):
    room = str(data['request_id'])
    await sio.enter_room(sid, room)
    print(f"[Socket.IO] {sid} joined room {room}")

@sio.event
async def send_message(sid, data):
    room = str(data['request_id'])
    # Relay to all OTHER users in the room (skip sender to avoid duplicates)
    await sio.emit('new_message', data, room=room, skip_sid=sid)
    print(f"[Socket.IO] Message relayed in room {room} (skipped {sid})")

# Run with: uvicorn main:app --reload --port 8000
