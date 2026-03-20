from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth, database
import uuid, os

router = APIRouter(tags=["messages"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"}

def _verify_chat_access(request_id: int, db: Session, current_user: models.User):
    """Verify the request exists and the user is part of it."""
    help_request = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not help_request:
        raise HTTPException(status_code=404, detail="Request not found")
    if current_user.id != help_request.student_id and current_user.id != help_request.helper_id:
        raise HTTPException(status_code=403, detail="Not authorized for this chat")
    return help_request

@router.get("/requests/{request_id}/messages", response_model=List[schemas.MessageOut])
def get_messages(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Message).filter(models.Message.request_id == request_id).all()

@router.post("/requests/{request_id}/messages", response_model=schemas.MessageOut)
def create_message(request_id: int, message: schemas.MessageBase, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    _verify_chat_access(request_id, db, current_user)
    
    new_msg = models.Message(
        request_id=request_id,
        sender_id=current_user.id,
        content=message.content
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg

@router.post("/requests/{request_id}/messages/upload", response_model=schemas.MessageOut)
async def create_message_with_attachment(
    request_id: int,
    file: UploadFile = File(...),
    content: Optional[str] = Form(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    _verify_chat_access(request_id, db, current_user)

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed.")

    # Save file
    unique_name = f"{uuid.uuid4()}{ext}"
    save_path = os.path.join("uploads", "chat", unique_name)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    file_bytes = await file.read()
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    attachment_url = f"/uploads/chat/{unique_name}"

    new_msg = models.Message(
        request_id=request_id,
        sender_id=current_user.id,
        content=content,
        attachment=attachment_url
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg
