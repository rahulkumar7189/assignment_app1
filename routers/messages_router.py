from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth, database

router = APIRouter(tags=["messages"])

@router.get("/requests/{request_id}/messages", response_model=List[schemas.MessageOut])
def get_messages(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Message).filter(models.Message.request_id == request_id).all()

@router.post("/requests/{request_id}/messages", response_model=schemas.MessageOut)
def create_message(request_id: int, message: schemas.MessageBase, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    # Verify the request exists
    help_request = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not help_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Verify user is part of this request
    if current_user.id != help_request.student_id and current_user.id != help_request.helper_id:
        raise HTTPException(status_code=403, detail="Not authorized for this chat")
    
    new_msg = models.Message(
        request_id=request_id,
        sender_id=current_user.id,
        content=message.content
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg
