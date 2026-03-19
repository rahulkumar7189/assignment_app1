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
from routers import auth_router, requests_router, messages_router, admin_router, users_router

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


# Create DB tables
_initialize_database()

app = FastAPI(title="AcadMate API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "https://acad-mate1-git-main-om156s-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads directory
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include Routers with /api/v1 prefix
app.include_router(auth_router.router, prefix="/api/v1/auth")
app.include_router(users_router.router, prefix="/api/v1/users")
app.include_router(requests_router.router, prefix="/api/v1")
app.include_router(messages_router.router, prefix="/api/v1")
app.include_router(admin_router.admin_router, prefix="/api/v1")

# Socket.io setup
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, app)

@app.get("/")
def read_root():
    return {"message": "Welcome to AcadMate API", "status": "running"}

# Socket Events
@sio.event
async def join_room(sid, data):
    room = data['request_id']
    await sio.enter_room(sid, str(room))

@sio.event
async def send_message(sid, data):
    db = database.SessionLocal()
    try:
        new_msg = models.Message(
            request_id=data['request_id'],
            sender_id=data['sender_id'],
            content=data['content']
        )
        db.add(new_msg)
        db.commit()
    except Exception as e:
        print(f"Error saving message: {e}")
    finally:
        db.close()
    
    await sio.emit('new_message', data, room=str(data['request_id']))

# Run with: uvicorn main:socket_app --reload --port 8000
