from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth, database, utils
import datetime
from sqlalchemy import func

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# --- OVERVIEW ---
@admin_router.get("/overview", response_model=schemas.AdminOverview)
def get_overview(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    
    total_users = db.query(models.User).count()
    total_helpers = db.query(models.User).filter(models.User.role == "helper").count()
    total_students = db.query(models.User).filter(models.User.role == "student").count()
    pending_verifications = db.query(models.User).filter(models.User.is_verified == False).count()
    
    active_requests = db.query(models.HelpRequest).filter(models.HelpRequest.status == "in_progress").count()
    completed_requests = db.query(models.HelpRequest).filter(models.HelpRequest.status == "completed").count()
    
    total_transactions = db.query(models.HelpRequest).filter(models.HelpRequest.advance_paid == True).count()
    revenue_sum = db.query(func.sum(models.HelpRequest.budget)).filter(models.HelpRequest.status == "completed").scalar() or 0.0
    
    return {
        "total_users": total_users,
        "total_helpers": total_helpers,
        "total_students": total_students,
        "pending_verifications": pending_verifications,
        "active_requests": active_requests,
        "completed_requests": completed_requests,
        "total_transactions": total_transactions,
        "revenue_summary": revenue_sum * 0.1
    }

# --- USERS ---
@admin_router.get("/users", response_model=List[schemas.UserOut])
def list_users(role: str = None, verified: bool = None, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    query = db.query(models.User)
    if role:
        query = query.filter(models.User.role == role)
    if verified is not None:
        query = query.filter(models.User.is_verified == verified)
    return query.all()

@admin_router.put("/users/{user_id}/status")
def update_user_status(user_id: int, is_suspended: bool = None, is_verified: bool = None, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if is_suspended is not None:
        user.is_suspended = is_suspended
        utils.log_admin_action(db, current_user.id, "suspend_user" if is_suspended else "reactivate_user", f"User ID: {user_id}")
    
    if is_verified is not None:
        user.is_verified = is_verified
        utils.log_admin_action(db, current_user.id, "verify_user" if is_verified else "unverify_user", f"User ID: {user_id}")
        
    db.commit()
    return {"message": "User status updated"}

@admin_router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    utils.log_admin_action(db, current_user.id, "delete_user", f"User ID: {user_id}")
    return {"message": "User deleted"}

# --- REQUESTS ---
@admin_router.get("/requests", response_model=List[schemas.HelpRequestOut])
def list_all_requests(status: str = None, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    query = db.query(models.HelpRequest)
    if status:
        query = query.filter(models.HelpRequest.status == status)
    return query.all()

@admin_router.put("/requests/{request_id}/reassign")
def reassign_helper(request_id: int, helper_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    helper = db.query(models.User).filter(models.User.id == helper_id, models.User.role == "helper").first()
    
    if not req or not helper:
        raise HTTPException(status_code=404, detail="Request or Helper not found")
    
    req.helper_id = helper_id
    db.commit()
    utils.log_admin_action(db, current_user.id, "reassign_helper", f"Request ID: {request_id}, New Helper: {helper_id}")
    return {"message": "Helper reassigned"}

# --- CHATS ---
@admin_router.get("/chats/{request_id}", response_model=List[schemas.MessageOut])
def view_chat_history(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.Message).filter(models.Message.request_id == request_id).all()

@admin_router.delete("/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(msg)
    db.commit()
    return {"message": "Message deleted"}

# --- SETTINGS ---
@admin_router.get("/settings", response_model=schemas.SystemSettingsOut)
def get_settings(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.SystemSettings).first()

@admin_router.put("/settings")
def update_settings(settings: schemas.SystemSettingsUpdate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    db_settings = db.query(models.SystemSettings).first()
    
    update_data = settings.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_settings, key, value)
    
    db.commit()
    utils.log_admin_action(db, current_user.id, "update_settings", str(update_data))
    return {"message": "Settings updated"}

# --- LOGS ---
@admin_router.get("/logs", response_model=List[schemas.ActivityLogOut])
def get_logs(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.ActivityLog).order_by(models.ActivityLog.timestamp.desc()).limit(100).all()
