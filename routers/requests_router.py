from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth, database, utils
from routers.notifications_router import create_notification
import os, uuid, json

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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_role(current_user, ["student"])
    
    # Save files
    attachment_paths = []
    if files:
        for file in files:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join("uploads", file_name)
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            # Store relative URL
            attachment_paths.append(f"/uploads/{file_name}")

    new_req = models.HelpRequest(
        title=title,
        subject=subject,
        description=description,
        deadline=utils.parse_datetime(deadline),
        budget=budget,
        student_id=current_user.id,
        is_urgent_print=is_urgent_print,
        attachments=json.dumps(attachment_paths) if attachment_paths else None
    )
    db.add(new_req)
    db.commit()
    db.refresh(new_req)
    
    # Prepare for response
    if new_req.attachments:
        new_req.attachments = json.loads(new_req.attachments)
    
    return new_req

@router.get("/", response_model=List[schemas.HelpRequestOut])
def list_requests(status: str = "open", db: Session = Depends(database.get_db)):
    # Explicitly only show requests with no helper assigned
    reqs = db.query(models.HelpRequest).filter(
        models.HelpRequest.status == status,
        models.HelpRequest.helper_id == None
    ).all()
    
    for r in reqs:
        if r.attachments:
            try:
                r.attachments = json.loads(r.attachments)
            except:
                r.attachments = []
    return reqs

@router.get("/my", response_model=List[schemas.HelpRequestOut])
def list_my_requests(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role == "student":
        reqs = db.query(models.HelpRequest).filter(models.HelpRequest.student_id == current_user.id).all()
    else:
        reqs = db.query(models.HelpRequest).filter(models.HelpRequest.helper_id == current_user.id).all()
    
    # Enrich with names and conditional phone
    enriched_reqs = []
    try:
        for r in reqs:
            # Handle attachments JSON
            attachments_list = []
            if r.attachments:
                try:
                    attachments_list = json.loads(r.attachments)
                except:
                    attachments_list = []

            if hasattr(schemas.HelpRequestOut, "model_validate"):
                schema_req = schemas.HelpRequestOut.model_validate(r)
            else:
                schema_req = schemas.HelpRequestOut.from_orm(r)
            
            schema_req.attachments = attachments_list
            schema_req.student_name = r.student.name if r.student else None
            schema_req.helper_name = r.helper.name if r.helper else None
            
            # Phone reveal logic
            if r.advance_paid and r.helper_id and r.student_id:
                if current_user.id == r.student_id:
                    schema_req.peer_phone = r.helper.phone_number
                else:
                    schema_req.peer_phone = r.student.phone_number
            
            enriched_reqs.append(schema_req)
    except Exception as e:
        print(f"Error in list_my_requests loop: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
    return enriched_reqs

@router.put("/{request_id}/pay-advance")
def pay_advance(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the student can pay the advance")
    
    if req.status != "in_progress":
        raise HTTPException(status_code=400, detail="Can only pay advance for requests in progress")

    req.advance_paid = True
    db.commit()
    return {"message": "Advance payment successful"}

@router.put("/{request_id}/accept")
async def accept_request(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    from main import sio
    auth.check_role(current_user, ["helper"])
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req or req.status != "open" or req.helper_id is not None:
        raise HTTPException(status_code=400, detail="Request no longer available")
    
    req.helper_id = current_user.id
    req.status = "in_progress"
    db.commit()
    
    # Notify student that their request was accepted
    create_notification(
        db, req.student_id, "request_accepted",
        "Request Accepted!",
        f"{current_user.name} accepted your request: {req.title}",
        related_request_id=request_id
    )
    
    # Broadcast to all connected clients that this request is no longer available
    await sio.emit('request_accepted', {'request_id': request_id})
    
    return {"message": "Request accepted"}

@router.put("/{request_id}/complete")
def complete_request(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only student can complete the request")
    
    req.status = "completed"
    if req.helper:
        req.helper.completed_tasks += 1
    
    db.commit()
    
    # Notify helper
    if req.helper_id:
        create_notification(
            db, req.helper_id, "request_completed",
            "Request Completed!",
            f"{current_user.name} marked '{req.title}' as completed.",
            related_request_id=request_id
        )
    
    return {"message": "Request marked as completed"}

@router.put("/{request_id}/cancel")
def cancel_request(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.student_id != current_user.id and (req.helper_id != current_user.id):
        raise HTTPException(status_code=403, detail="You are not authorized to cancel this request")

    if req.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot cancel a completed request")
    
    req.status = "cancelled"
    db.commit()
    return {"message": "Request cancelled"}

# --- ESCROW & MILESTONE ENDPOINTS ---

@router.post("/{request_id}/milestones", response_model=schemas.MilestoneOut)
def create_milestone(request_id: int, milestone: schemas.MilestoneCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if current_user.id not in [req.student_id, req.helper_id]:
        raise HTTPException(status_code=403, detail="Not authorized for this request")
        
    new_milestone = models.Milestone(
        request_id=request_id,
        amount=milestone.amount,
        description=milestone.description
    )
    db.add(new_milestone)
    db.commit()
    db.refresh(new_milestone)
    
    # Notify the other party
    other_user_id = req.helper_id if current_user.id == req.student_id else req.student_id
    if other_user_id:
        create_notification(
            db, other_user_id, "milestone_created",
            "New Milestone Added",
            f"A new milestone of ₹{milestone.amount} has been added to '{req.title}'.",
            related_request_id=request_id
        )
    return new_milestone

@router.get("/{request_id}/milestones", response_model=List[schemas.MilestoneOut])
def get_milestones(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req or (current_user.id not in [req.student_id, req.helper_id] and current_user.role != "admin"):
        raise HTTPException(status_code=404, detail="Request not found or unauthorized")
        
    milestones = db.query(models.Milestone).filter(models.Milestone.request_id == request_id).all()
    return milestones

@router.put("/milestones/{milestone_id}/pay")
def pay_milestone(milestone_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    milestone = db.query(models.Milestone).filter(models.Milestone.id == milestone_id).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
        
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == milestone.request_id).first()
    if current_user.id != req.student_id:
        raise HTTPException(status_code=403, detail="Only the student can pay the milestone")
        
    if milestone.status == "paid":
        raise HTTPException(status_code=400, detail="Milestone is already paid")
        
    milestone.status = "paid"
    db.commit()
    
    if req.helper_id:
        create_notification(
            db, req.helper_id, "milestone_paid",
            "Milestone Paid!",
            f"A milestone of ₹{milestone.amount} on '{req.title}' has been paid/released.",
            related_request_id=req.id
        )
    return {"message": "Milestone successfully paid"}

# --- DISPUTE ENDPOINTS ---

@router.post("/{request_id}/disputes", response_model=schemas.DisputeOut)
def raise_dispute(request_id: int, dispute: schemas.DisputeCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if current_user.id not in [req.student_id, req.helper_id]:
        raise HTTPException(status_code=403, detail="Not authorized to raise a dispute for this request")
        
    new_dispute = models.Dispute(
        request_id=request_id,
        raised_by_id=current_user.id,
        reason=dispute.reason
    )
    db.add(new_dispute)
    db.commit()
    db.refresh(new_dispute)
    
    # Notify admin (Assuming admin has a generalized notification listener or we can add to logs)
    return new_dispute

# --- PUBLIC MARKETPLACE ---
@router.get("/marketplace", response_model=List[schemas.MarketplaceItemOut])
def get_marketplace_items(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.MarketplaceItem).order_by(models.MarketplaceItem.created_at.desc()).all()
