from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from typing import List, Optional
import models, schemas, auth, utils
from routers.notifications_router import create_notification
from beanie.odm.fields import PydanticObjectId
import os, uuid

router = APIRouter(prefix="/requests", tags=["requests"])


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
                content = await file.read()
                buffer.write(content)
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
    )
    await new_req.insert()
    return new_req


@router.get("/", response_model=List[schemas.HelpRequestOut])
async def list_requests(status: str = "open"):
    return await models.HelpRequest.find(
        models.HelpRequest.status == status,
        models.HelpRequest.helper_id == None,
    ).to_list()


@router.get("/my", response_model=List[schemas.HelpRequestOut])
async def list_my_requests(current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role == "student":
        reqs = await models.HelpRequest.find(
            models.HelpRequest.student_id == current_user.id
        ).to_list()
    else:
        reqs = await models.HelpRequest.find(
            models.HelpRequest.helper_id == current_user.id
        ).to_list()

    enriched = []
    for r in reqs:
        req_dict = r.model_dump(by_alias=False)
        req_dict["id"] = str(r.id)
        req_dict["student_id"] = str(r.student_id)
        req_dict["helper_id"] = str(r.helper_id) if r.helper_id else None
        req_dict["peer_phone"]    = None
        req_dict["peer_email"]    = None
        req_dict["peer_whatsapp"] = None
        req_dict["peer_telegram"] = None

        if r.contact_unlocked and r.helper_id and r.student_id:
            if current_user.id == r.student_id:
                peer = await models.User.find_one(models.User.id == r.helper_id)
            else:
                peer = await models.User.find_one(models.User.id == r.student_id)
            if peer:
                req_dict["peer_phone"]    = peer.phone_number
                req_dict["peer_email"]    = peer.email
                req_dict["peer_whatsapp"] = peer.whatsapp_number
                req_dict["peer_telegram"] = peer.telegram_id

        enriched.append(schemas.HelpRequestOut(**req_dict))
    return enriched


@router.put("/{request_id}/pay-advance")
async def pay_advance(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the student can unlock contact details")
    if req.status != "in_progress":
        raise HTTPException(status_code=400, detail="Can only unlock contact for requests in progress")

    req.contact_unlocked = True
    await req.save()
    return {"message": "Contact details unlocked"}


@router.put("/{request_id}/accept")
async def accept_request(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    from main import sio
    auth.check_role(current_user, ["helper"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req or req.status != "open" or req.helper_id is not None:
        raise HTTPException(status_code=400, detail="Request no longer available")

    req.helper_id = current_user.id
    req.helper_name = current_user.name
    req.status = "in_progress"
    await req.save()

    await create_notification(
        req.student_id, "request_accepted",
        "Request Accepted!",
        f"{current_user.name} accepted your request: {req.title}",
        related_request_id=req.id,
    )

    await sio.emit('request_accepted', {'request_id': request_id})
    return {"message": "Request accepted"}


@router.put("/{request_id}/complete")
async def complete_request(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only student can complete the request")

    req.status = "completed"
    await req.save()

    if req.helper_id:
        helper = await models.User.find_one(models.User.id == req.helper_id)
        if helper:
            helper.completed_tasks += 1
            await helper.save()

        await create_notification(
            req.helper_id, "request_completed",
            "Request Completed!",
            f"{current_user.name} marked '{req.title}' as completed.",
            related_request_id=req.id,
        )

    return {"message": "Request marked as completed"}


@router.put("/{request_id}/cancel")
async def cancel_request(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id and req.helper_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not authorized to cancel this request")
    if req.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot cancel a completed request")

    req.status = "cancelled"
    await req.save()
    return {"message": "Request cancelled"}


# --- ESCROW & MILESTONE ENDPOINTS ---

@router.post("/{request_id}/milestones", response_model=schemas.MilestoneOut)
async def create_milestone(request_id: str, milestone: schemas.MilestoneCreate, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if current_user.id not in [req.student_id, req.helper_id]:
        raise HTTPException(status_code=403, detail="Not authorized for this request")

    new_milestone = models.Milestone(
        request_id=req.id,
        amount=milestone.amount,
        description=milestone.description,
    )
    await new_milestone.insert()

    other_user_id = req.helper_id if current_user.id == req.student_id else req.student_id
    if other_user_id:
        await create_notification(
            other_user_id, "milestone_created",
            "New Milestone Added",
            f"A new milestone of ₹{milestone.amount} has been added to '{req.title}'.",
            related_request_id=req.id,
        )
    return new_milestone


@router.get("/{request_id}/milestones", response_model=List[schemas.MilestoneOut])
async def get_milestones(request_id: str, current_user: models.User = Depends(auth.get_current_user)):
    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(request_id))
    if not req or (current_user.id not in [req.student_id, req.helper_id] and current_user.role != "admin"):
        raise HTTPException(status_code=404, detail="Request not found or unauthorized")

    return await models.Milestone.find(
        models.Milestone.request_id == PydanticObjectId(request_id)
    ).to_list()


@router.put("/milestones/{milestone_id}/pay")
async def pay_milestone(milestone_id: str, current_user: models.User = Depends(auth.get_current_user)):
    milestone = await models.Milestone.find_one(models.Milestone.id == PydanticObjectId(milestone_id))
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    req = await models.HelpRequest.find_one(models.HelpRequest.id == milestone.request_id)
    if current_user.id != req.student_id:
        raise HTTPException(status_code=403, detail="Only the student can pay the milestone")
    if milestone.status == "paid":
        raise HTTPException(status_code=400, detail="Milestone is already paid")

    milestone.status = "paid"
    await milestone.save()

    if req.helper_id:
        await create_notification(
            req.helper_id, "milestone_paid",
            "Milestone Paid!",
            f"A milestone of ₹{milestone.amount} on '{req.title}' has been paid/released.",
            related_request_id=req.id,
        )
    return {"message": "Milestone successfully paid"}


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
