from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth, database, utils
import datetime
import os, uuid
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
@admin_router.get("/users", response_model=List[schemas.AdminUserOut])
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
    return {"status": "updated"}

@admin_router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
        
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Manual cascading delete to avoid Integrity Errors
    try:
        # 1. Activity Logs & Notifications
        db.query(models.ActivityLog).filter(models.ActivityLog.user_id == user_id).delete()
        db.query(models.Notification).filter(models.Notification.user_id == user_id).delete()
        
        # 2. As Helper: Unlink from existing requests
        db.query(models.HelpRequest).filter(models.HelpRequest.helper_id == user_id).update({"helper_id": None})
        
        # 3. As Student: Delete requests and their dependent records
        student_requests = db.query(models.HelpRequest).filter(models.HelpRequest.student_id == user_id).all()
        for req in student_requests:
            db.query(models.PaymentDetection).filter(models.PaymentDetection.request_id == req.id).delete()
            db.query(models.Review).filter(models.Review.request_id == req.id).delete()
            db.query(models.Message).filter(models.Message.request_id == req.id).delete()
            db.delete(req)
            
        # 4. Stray messages and explicit payment detections by this user
        db.query(models.Message).filter(models.Message.sender_id == user_id).delete()
        db.query(models.PaymentDetection).filter(models.PaymentDetection.sender_id == user_id).delete()
        
        # Log action and delete user
        utils.log_admin_action(db, current_user.id, "delete_user", f"Deleted User ID: {user_id} ({user.email})")
        db.delete(user)
        db.commit()
        return {"status": "deleted", "message": "User permanently deleted."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

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

# --- PAYMENT DETECTIONS ---
@admin_router.get("/payments", response_model=List[schemas.PaymentDetectionOut])
def get_payment_detections(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.PaymentDetection).order_by(models.PaymentDetection.detected_at.desc()).all()

@admin_router.get("/payments/details")
def get_payment_details(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    """Get payment detections with enriched details (user names, request titles)."""
    auth.check_role(current_user, ["admin"])
    detections = db.query(models.PaymentDetection).order_by(models.PaymentDetection.detected_at.desc()).all()
    results = []
    for d in detections:
        sender = db.query(models.User).filter(models.User.id == d.sender_id).first()
        request = db.query(models.HelpRequest).filter(models.HelpRequest.id == d.request_id).first()
        msg = db.query(models.Message).filter(models.Message.id == d.message_id).first()
        results.append({
            "id": d.id,
            "request_id": d.request_id,
            "request_title": request.title if request else "Unknown",
            "sender_name": sender.name if sender else "Unknown",
            "sender_email": sender.email if sender else "Unknown",
            "message_content": msg.content if msg else "",
            "detected_amount": d.detected_amount,
            "payment_status": d.payment_status,
            "detected_keywords": d.detected_keywords,
            "screenshot_url": d.screenshot_url,
            "detected_at": d.detected_at.isoformat() if d.detected_at else None
        })
    return results

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

# --- DISPUTES ---
@admin_router.get("/disputes")
def get_disputes(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    disputes = db.query(models.Dispute).order_by(models.Dispute.created_at.desc()).all()
    results = []
    for d in disputes:
        req = db.query(models.HelpRequest).filter(models.HelpRequest.id == d.request_id).first()
        raiser = db.query(models.User).filter(models.User.id == d.raised_by_id).first()
        results.append({
            "id": d.id,
            "request_id": d.request_id,
            "request_title": req.title if req else "Unknown",
            "raised_by_name": raiser.name if raiser else "Unknown",
            "reason": d.reason,
            "status": d.status,
            "admin_notes": d.admin_notes,
            "created_at": d.created_at.isoformat() if d.created_at else None
        })
    return results

@admin_router.put("/disputes/{dispute_id}/resolve")
def resolve_dispute(dispute_id: int, payload: dict, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    dispute = db.query(models.Dispute).filter(models.Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
        
    admin_notes = payload.get("admin_notes", "")
    dispute.status = "resolved"
    dispute.admin_notes = admin_notes
    db.commit()
    
    utils.log_admin_action(db, current_user.id, "resolve_dispute", f"Resolved Dispute ID: {dispute_id}")
    return {"message": "Dispute resolved successfully"}

# --- MARKETPLACE ---
@admin_router.post("/marketplace", response_model=schemas.MarketplaceItemOut)
async def upload_marketplace_item(
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    item_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    auth.check_role(current_user, ["admin"])
    
    # Save file
    file_ext = os.path.splitext(file.filename)[1]
    file_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join("uploads", file_name)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    relative_path = f"/uploads/{file_name}"
    
    new_item = models.MarketplaceItem(
        title=title,
        description=description,
        file_path=relative_path,
        price=price,
        item_type=item_type,
        admin_id=current_user.id
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    utils.log_admin_action(db, current_user.id, "upload_marketplace_item", f"Uploaded {item_type}: {title}")
    return new_item

@admin_router.get("/marketplace", response_model=List[schemas.MarketplaceItemOut])
def get_admin_marketplace_items(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.MarketplaceItem).order_by(models.MarketplaceItem.created_at.desc()).all()

@admin_router.delete("/marketplace/{item_id}")
def delete_marketplace_item(item_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    item = db.query(models.MarketplaceItem).filter(models.MarketplaceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    db.delete(item)
    db.commit()
    utils.log_admin_action(db, current_user.id, "delete_marketplace_item", f"Deleted item ID {item_id}")
    return {"message": "Item deleted successfully"}
