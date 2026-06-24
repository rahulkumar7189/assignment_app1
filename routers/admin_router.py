from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from typing import List, Optional
import models, schemas, auth, utils
from beanie.odm.fields import PydanticObjectId
from bson import ObjectId
import datetime
import os, uuid

admin_router = APIRouter(prefix="/admin", tags=["admin"])


# --- OVERVIEW ---
@admin_router.get("/overview", response_model=schemas.AdminOverview)
async def get_overview(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])

    total_users = await models.User.count()
    total_helpers = await models.User.find(models.User.role == "helper").count()
    total_students = await models.User.find(models.User.role == "student").count()
    pending_verifications = await models.User.find(models.User.is_verified == False).count()

    active_requests = await models.HelpRequest.find(models.HelpRequest.status == "in_progress").count()
    completed_requests = await models.HelpRequest.find(models.HelpRequest.status == "completed").count()
    total_transactions = await models.RazorpayOrder.find(models.RazorpayOrder.status == "paid").count()

    # Revenue = posting fees (₹9 each) + platform commission (10%) from assignment payments
    posting_fee_orders = await models.RazorpayOrder.find(
        models.RazorpayOrder.status == "paid",
        models.RazorpayOrder.order_type == "posting_fee",
    ).count()
    assignment_orders = await models.RazorpayOrder.find(
        models.RazorpayOrder.status == "paid",
        models.RazorpayOrder.order_type == "assignment_payment",
    ).to_list()
    posting_fee_revenue = posting_fee_orders * float(os.getenv("POSTING_FEE", "9"))
    commission_revenue = sum(o.platform_fee_amount or 0.0 for o in assignment_orders)
    revenue_summary = round(posting_fee_revenue + commission_revenue, 2)

    return {
        "total_users": total_users,
        "total_helpers": total_helpers,
        "total_students": total_students,
        "pending_verifications": pending_verifications,
        "active_requests": active_requests,
        "completed_requests": completed_requests,
        "total_transactions": total_transactions,
        "revenue_summary": revenue_summary,
    }


# --- USERS ---
@admin_router.get("/users", response_model=List[schemas.AdminUserOut])
async def list_users(role: str = None, verified: bool = None, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    query = models.User.find()
    if role:
        query = query.find(models.User.role == role)
    if verified is not None:
        query = query.find(models.User.is_verified == verified)
    return await query.to_list()


@admin_router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    is_suspended: bool = None,
    is_verified: bool = None,
    current_user: models.User = Depends(auth.get_current_admin),
):
    auth.check_role(current_user, ["admin"])
    user = await models.User.find_one(models.User.id == PydanticObjectId(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if is_suspended is not None:
        user.is_suspended = is_suspended
        await utils.log_admin_action(current_user.id, "suspend_user" if is_suspended else "reactivate_user", f"User ID: {user_id}")

    if is_verified is not None:
        user.is_verified = is_verified
        await utils.log_admin_action(current_user.id, "verify_user" if is_verified else "unverify_user", f"User ID: {user_id}")

    await user.save()
    return {"status": "updated"}


@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])

    if user_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    uid = PydanticObjectId(user_id)
    user = await models.User.find_one(models.User.id == uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # 1. Activity Logs & Notifications
        await models.ActivityLog.find(models.ActivityLog.user_id == uid).delete()
        await models.Notification.find(models.Notification.user_id == uid).delete()

        # 2. As Helper: Unlink from existing requests
        await models.HelpRequest.find(models.HelpRequest.helper_id == uid).update(
            {"$set": {"helper_id": None, "helper_name": None}}
        )

        # 3. As Student: Delete requests and their dependents
        student_requests = await models.HelpRequest.find(models.HelpRequest.student_id == uid).to_list()
        for req in student_requests:
            await models.PaymentDetection.find(models.PaymentDetection.request_id == req.id).delete()
            await models.Review.find(models.Review.request_id == req.id).delete()
            await models.Message.find(models.Message.request_id == req.id).delete()
            await models.Milestone.find(models.Milestone.request_id == req.id).delete()
            await models.Dispute.find(models.Dispute.request_id == req.id).delete()
            await req.delete()

        # 4. Stray messages and payment detections
        await models.Message.find(models.Message.sender_id == uid).delete()
        await models.PaymentDetection.find(models.PaymentDetection.sender_id == uid).delete()

        await utils.log_admin_action(current_user.id, "delete_user", f"Deleted User ID: {user_id} ({user.email})")
        await user.delete()
        return {"status": "deleted", "message": "User permanently deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


# --- REQUESTS ---
@admin_router.get("/requests", response_model=List[schemas.HelpRequestOut])
async def list_all_requests(status: str = None, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    query = models.HelpRequest.find()
    if status:
        query = query.find(models.HelpRequest.status == status)
    return await query.sort("-created_at").to_list()


@admin_router.put("/requests/{request_id}/reassign")
async def reassign_helper(request_id: str, helper_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    helper = await models.User.find_one(models.User.id == PydanticObjectId(helper_id), models.User.role == "helper")

    if not req or not helper:
        raise HTTPException(status_code=404, detail="Request or Helper not found")

    req.helper_id = helper.id
    req.helper_name = helper.name
    await req.save()
    await utils.log_admin_action(current_user.id, "reassign_helper", f"Request ID: {request_id}, New Helper: {helper_id}")
    return {"message": "Helper reassigned"}


# --- CHATS ---
@admin_router.get("/chats/{request_id}", response_model=List[schemas.MessageOut])
async def view_chat_history(request_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return await models.Message.find(
        models.Message.request_id == PydanticObjectId(request_id)
    ).to_list()


@admin_router.delete("/messages/{message_id}")
async def delete_message(message_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    msg = await models.Message.find_one(models.Message.id == PydanticObjectId(message_id))
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    await msg.delete()
    return {"message": "Message deleted"}


# --- PAYMENT DETECTIONS ---
@admin_router.get("/payments", response_model=List[schemas.PaymentDetectionOut])
async def get_payment_detections(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return await models.PaymentDetection.find().sort("-detected_at").to_list()


@admin_router.get("/payments/details")
async def get_payment_details(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    detections = await models.PaymentDetection.find().sort("-detected_at").to_list()
    results = []
    for d in detections:
        sender = await models.User.find_one(models.User.id == d.sender_id)
        request = await models.HelpRequest.find_one(models.HelpRequest.id == d.request_id)
        msg = await models.Message.find_one(models.Message.id == d.message_id)
        results.append({
            "id": str(d.id),
            "request_id": str(d.request_id),
            "request_title": request.title if request else "Unknown",
            "sender_name": sender.name if sender else "Unknown",
            "sender_email": sender.email if sender else "Unknown",
            "message_content": msg.content if msg else "",
            "detected_amount": d.detected_amount,
            "payment_status": d.payment_status,
            "detected_keywords": d.detected_keywords,
            "screenshot_url": d.screenshot_url,
            "detected_at": d.detected_at.isoformat() if d.detected_at else None,
        })
    return results


# --- SETTINGS ---
@admin_router.get("/settings", response_model=schemas.SystemSettingsOut)
async def get_settings(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    settings = await models.SystemSettings.find_one()
    if not settings:
        settings = models.SystemSettings()
        await settings.insert()
    return settings


@admin_router.put("/settings")
async def update_settings(settings: schemas.SystemSettingsUpdate, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    db_settings = await models.SystemSettings.find_one()
    if not db_settings:
        db_settings = models.SystemSettings()
        await db_settings.insert()

    update_data = settings.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_settings, key, value)

    await db_settings.save()
    await utils.log_admin_action(current_user.id, "update_settings", str(update_data))
    return {"message": "Settings updated"}


# --- LOGS ---
@admin_router.get("/logs", response_model=List[schemas.ActivityLogOut])
async def get_logs(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return await models.ActivityLog.find().sort("-timestamp").limit(100).to_list()


@admin_router.get("/logs/detailed")
async def get_detailed_logs(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    logs = await models.ActivityLog.find().sort("-timestamp").limit(200).to_list()
    results = []
    for log in logs:
        user = await models.User.find_one(models.User.id == log.user_id) if log.user_id else None
        results.append({
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "user_name": user.name if user else "Unknown",
            "user_email": user.email if user else "",
            "user_role": user.role if user else "",
            "action": log.action,
            "details": log.details,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        })
    return results


# --- DISPUTES ---
@admin_router.get("/disputes")
async def get_disputes(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    disputes = await models.Dispute.find().sort("-created_at").to_list()
    results = []
    for d in disputes:
        req = await models.HelpRequest.find_one(models.HelpRequest.id == d.request_id)
        raiser = await models.User.find_one(models.User.id == d.raised_by_id)
        results.append({
            "id": str(d.id),
            "request_id": str(d.request_id),
            "request_title": req.title if req else "Unknown",
            "raised_by_name": raiser.name if raiser else "Unknown",
            "reason": d.reason,
            "status": d.status,
            "admin_notes": d.admin_notes,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return results


@admin_router.put("/disputes/{dispute_id}/resolve")
async def resolve_dispute(dispute_id: str, payload: dict, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    dispute = await models.Dispute.find_one(models.Dispute.id == PydanticObjectId(dispute_id))
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    dispute.status = "resolved"
    dispute.admin_notes = payload.get("admin_notes", "")
    await dispute.save()

    await utils.log_admin_action(current_user.id, "resolve_dispute", f"Resolved Dispute ID: {dispute_id}")
    return {"message": "Dispute resolved successfully"}


# --- WORK VERIFICATION QUEUE ---

@admin_router.get("/work-queue")
async def get_work_queue(current_user: models.User = Depends(auth.get_current_admin)):
    """All assignments where helper has submitted work awaiting admin review."""
    auth.check_role(current_user, ["admin"])
    reqs = await models.HelpRequest.find(
        models.HelpRequest.status == "work_submitted"
    ).sort("-work_submitted_at").to_list()
    result = []
    for r in reqs:
        result.append({
            "id": str(r.id),
            "title": r.title,
            "subject": r.subject,
            "budget": r.budget,
            "student_name": r.student_name or "Unknown",
            "helper_name": r.helper_name or "Unknown",
            "work_submitted_at": r.work_submitted_at.isoformat() if r.work_submitted_at else None,
            "work_file": r.work_file,
            "work_rejected_reason": r.work_rejected_reason,
        })
    return result


@admin_router.get("/work/{request_id}/preview")
async def preview_work_file(request_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    """Returns the submitted work file for admin review."""
    from fastapi.responses import FileResponse
    auth.check_role(current_user, ["admin"])
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req or not req.work_file:
        raise HTTPException(status_code=404, detail="No work file found")
    if not os.path.exists(req.work_file):
        raise HTTPException(status_code=404, detail="Work file missing from server")
    return FileResponse(path=req.work_file, filename=os.path.basename(req.work_file))


@admin_router.put("/requests/{request_id}/verify-work")
async def verify_work(
    request_id: str,
    payload: schemas.WorkVerifyRequest,
    current_user: models.User = Depends(auth.get_current_admin),
):
    """Admin approves or rejects submitted work."""
    auth.check_role(current_user, ["admin"])
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "work_submitted":
        raise HTTPException(status_code=400, detail="Request is not in work_submitted state")

    from routers.notifications_router import create_notification

    if payload.action == "approve":
        req.status = "awaiting_payment"
        req.work_verified = True
        req.work_verified_at = datetime.datetime.utcnow()
        await req.save()

        await create_notification(
            req.student_id, "work_approved",
            "Your Assignment is Ready!",
            f"Admin verified the work for '{req.title}'. Please pay ₹{req.budget:.0f} to download it.",
            related_request_id=req.id,
        )
        if req.helper_id:
            await create_notification(
                req.helper_id, "work_approved",
                "Work Approved by Admin",
                f"Your submitted work for '{req.title}' was approved. Waiting for student payment.",
                related_request_id=req.id,
            )
        await utils.log_admin_action(current_user.id, "approve_work", f"Approved work for Request #{request_id}")
        return {"message": "Work approved. Student has been notified to pay."}

    elif payload.action == "reject":
        req.status = "in_progress"
        req.work_verified = False
        req.work_rejected_reason = payload.reason or "Work did not meet requirements"
        req.work_file = None
        req.work_submitted_at = None
        await req.save()

        if req.helper_id:
            await create_notification(
                req.helper_id, "work_rejected",
                "Work Rejected — Please Revise",
                f"Admin rejected your submission for '{req.title}'. Reason: {req.work_rejected_reason}",
                related_request_id=req.id,
            )
        await utils.log_admin_action(current_user.id, "reject_work", f"Rejected work for Request #{request_id}: {payload.reason}")
        return {"message": "Work rejected. Helper has been notified to revise."}

    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")


# --- MARKETPLACE ---
@admin_router.post("/marketplace", response_model=schemas.MarketplaceItemOut)
async def upload_marketplace_item(
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    item_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_admin),
):
    auth.check_role(current_user, ["admin"])

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
        admin_id=current_user.id,
    )
    await new_item.insert()

    await utils.log_admin_action(current_user.id, "upload_marketplace_item", f"Uploaded {item_type}: {title}")
    return new_item


@admin_router.get("/marketplace", response_model=List[schemas.MarketplaceItemOut])
async def get_admin_marketplace_items(current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    return await models.MarketplaceItem.find().sort("-created_at").to_list()


@admin_router.delete("/marketplace/{item_id}")
async def delete_marketplace_item(item_id: str, current_user: models.User = Depends(auth.get_current_admin)):
    auth.check_role(current_user, ["admin"])
    item = await models.MarketplaceItem.find_one(models.MarketplaceItem.id == PydanticObjectId(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await item.delete()
    await utils.log_admin_action(current_user.id, "delete_marketplace_item", f"Deleted item ID {item_id}")
    return {"message": "Item deleted successfully"}
