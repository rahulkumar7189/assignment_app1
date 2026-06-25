from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Optional
import models, schemas, auth, utils
from routers.notifications_router import create_notification
from beanie.odm.fields import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
from datetime import datetime
import os, uuid, io

router = APIRouter(prefix="/requests", tags=["requests"])

WORK_UPLOAD_DIR = os.path.join("uploads", "work")
os.makedirs(WORK_UPLOAD_DIR, exist_ok=True)


def _gridfs_bucket() -> AsyncIOMotorGridFSBucket:
    """Return a GridFS bucket from the live Motor client."""
    import database
    db = database.motor_client[os.getenv("MONGO_DB_NAME", "acadmate")]
    return AsyncIOMotorGridFSBucket(db, bucket_name="work_files")


@router.post("/", response_model=schemas.HelpRequestOut)
async def create_request(
    title: str = Form(...),
    subject: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...),
    budget: Optional[float] = Form(None),
    is_urgent_print: Optional[bool] = Form(False),
    files: List[UploadFile] = File(None),
    current_user: models.User = Depends(auth.get_current_user),
):
    auth.check_role(current_user, ["student"])

    attachment_paths = []
    if files:
        for file in files:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join("uploads", file_name)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            attachment_paths.append(f"/uploads/{file_name}")

    new_req = models.HelpRequest(
        title=title,
        subject=subject,
        description=description,
        deadline=utils.parse_datetime(deadline),
        budget=budget,
        student_id=current_user.id,
        student_name=current_user.name,
        is_urgent_print=is_urgent_print,
        attachments=attachment_paths if attachment_paths else None,
        status="pending_posting_fee",
    )
    await new_req.insert()
    return _to_out(new_req, is_student=True, is_completed=False)


@router.get("/", response_model=List[schemas.HelpRequestOut])
async def list_requests():
    """Public listing of open assignments (no contact info ever exposed)."""
    reqs = await models.HelpRequest.find(
        models.HelpRequest.status == "open",
    ).to_list()
    return [_to_out(r) for r in reqs]


@router.get("/my", response_model=List[schemas.HelpRequestOut])
async def list_my_requests(current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role == "student":
        reqs = await models.HelpRequest.find(
            models.HelpRequest.student_id == current_user.id
        ).sort("-created_at").to_list()
    else:
        reqs = await models.HelpRequest.find(
            models.HelpRequest.helper_id == current_user.id
        ).sort("-created_at").to_list()

    result = []
    for r in reqs:
        is_student = (current_user.role == "student")
        is_completed = (r.status == "completed")
        result.append(_to_out(r, is_student=is_student, is_completed=is_completed))
    return result


def _to_out(r: models.HelpRequest, is_student: bool = False, is_completed: bool = False) -> schemas.HelpRequestOut:
    """Build HelpRequestOut — contact info is NEVER included."""
    return schemas.HelpRequestOut(
        id=str(r.id),
        title=r.title,
        subject=r.subject,
        description=r.description,
        deadline=r.deadline,
        budget=r.budget,
        is_urgent_print=r.is_urgent_print,
        student_id=str(r.student_id),
        helper_id=str(r.helper_id) if r.helper_id else None,
        status=r.status,
        posting_fee_paid=r.posting_fee_paid,
        attachments=r.attachments,
        created_at=r.created_at,
        student_name=r.student_name if not is_student else r.student_name,
        helper_name=r.helper_name,
        work_file_available=(is_student and is_completed and bool(r.work_file)),
        work_verified=r.work_verified,
        work_rejected_reason=r.work_rejected_reason,
        payout_initiated=r.payout_initiated,
    )


@router.put("/{request_id}/accept")
async def accept_request(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    from main import sio
    auth.check_role(current_user, ["helper"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req or req.status != "open" or req.helper_id is not None:
        raise HTTPException(status_code=400, detail="Request no longer available")

    # Store only first name to keep helper somewhat anonymous to student in UI
    req.helper_id = current_user.id
    req.helper_name = current_user.name.split()[0]
    req.status = "in_progress"
    await req.save()

    await create_notification(
        req.student_id, "request_accepted",
        "A Helper Accepted Your Assignment!",
        f"A helper accepted your assignment '{req.title}'. They will upload the completed work once done.",
        related_request_id=req.id,
    )

    await sio.emit('request_accepted', {'request_id': request_id})
    return {"message": "Request accepted"}


@router.post("/{request_id}/submit-work")
async def submit_work(
    request_id: str,
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Helper uploads completed assignment file. Admin must verify before student can pay/download."""
    auth.check_role(current_user, ["helper"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.helper_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the helper for this request")
    if req.status not in ("in_progress", "work_submitted"):
        raise HTTPException(status_code=400, detail="Work can only be submitted while the request is in progress")

    # Upload file to MongoDB GridFS — survives server restarts on Render
    file_data = await file.read()
    original_filename = file.filename or f"work{os.path.splitext(file.filename or '')[1]}"
    bucket = _gridfs_bucket()
    # Delete previous GridFS file for this request if it exists
    if req.work_file and req.work_file.startswith("gridfs:"):
        try:
            old_id = ObjectId(req.work_file[7:])
            await bucket.delete(old_id)
        except Exception:
            pass
    file_id = await bucket.upload_from_stream(
        original_filename,
        io.BytesIO(file_data),
        metadata={"request_id": request_id, "content_type": file.content_type or "application/octet-stream"},
    )
    req.work_file = f"gridfs:{str(file_id)}"
    req.work_submitted_at = datetime.utcnow()
    req.status = "work_submitted"
    req.work_verified = False
    req.work_rejected_reason = None
    await req.save()

    # Notify all admins
    admins = await models.User.find(models.User.role == "admin").to_list()
    for admin in admins:
        await create_notification(
            admin.id, "work_submitted",
            "Work Submitted — Needs Verification",
            f"A helper submitted work for assignment '{req.title}'. Please review and approve or reject.",
            related_request_id=req.id,
        )

    return {"message": "Work submitted successfully. Admin will review it shortly."}


@router.get("/{request_id}/download-work")
async def download_work(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    """Student downloads work file only after payment (status=completed)."""
    auth.check_role(current_user, ["student"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if req.status != "completed":
        raise HTTPException(status_code=403, detail="Payment must be completed before downloading")
    if not req.work_file:
        raise HTTPException(status_code=404, detail="Work file not found")

    return await _stream_work_file(req)


async def _stream_work_file(req: models.HelpRequest):
    """Stream the work file from GridFS (or local disk as fallback)."""
    if req.work_file and req.work_file.startswith("gridfs:"):
        file_id = ObjectId(req.work_file[7:])
        bucket = _gridfs_bucket()
        try:
            grid_out = await bucket.open_download_stream(file_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Work file not found in storage")
        filename = grid_out.filename or "assignment"
        data = await grid_out.read()
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # Fallback: legacy local-filesystem path (pre-migration uploads)
    if req.work_file and os.path.exists(req.work_file):
        return FileResponse(
            path=req.work_file,
            filename=os.path.basename(req.work_file),
            media_type="application/octet-stream",
        )
    raise HTTPException(status_code=404, detail="Work file not found")


@router.put("/{request_id}/cancel")
async def cancel_request(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id and req.helper_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this request")
    if req.status in ("completed", "awaiting_payment"):
        raise HTTPException(status_code=400, detail="Cannot cancel at this stage")

    req.status = "cancelled"
    await req.save()
    return {"message": "Request cancelled"}


# --- DISPUTE ENDPOINTS ---

@router.post("/{request_id}/disputes", response_model=schemas.DisputeOut)
async def raise_dispute(request_id: str, dispute: schemas.DisputeCreate, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if current_user.id not in [req.student_id, req.helper_id]:
        raise HTTPException(status_code=403, detail="Not authorized to raise a dispute for this request")

    new_dispute = models.Dispute(
        request_id=req.id,
        raised_by_id=current_user.id,
        reason=dispute.reason,
    )
    await new_dispute.insert()
    return new_dispute


# --- PUBLIC MARKETPLACE ---

@router.get("/marketplace", response_model=List[schemas.MarketplaceItemOut])
async def get_marketplace_items(current_user: models.User = Depends(auth.get_current_user)):
    return await models.MarketplaceItem.find().sort("-created_at").to_list()
