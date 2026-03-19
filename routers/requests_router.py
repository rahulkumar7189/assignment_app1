from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth, database, utils
import os, uuid, json

router = APIRouter(prefix="/requests", tags=["requests"])

@router.post("/", response_model=schemas.HelpRequestOut)
async def create_request(
    title: str = Form(...),
    subject: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...),
    budget: Optional[float] = Form(None),
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
    # Local import to avoid circularity if possible, though utils and separate sio would be better
    from main import sio
    auth.check_role(current_user, ["helper"])
    req = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not req or req.status != "open" or req.helper_id is not None:
        raise HTTPException(status_code=400, detail="Request no longer available")
    
    req.helper_id = current_user.id
    req.status = "in_progress"
    db.commit()
    
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
