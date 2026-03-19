from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth, database

router = APIRouter(tags=["messages"])

@router.get("/requests/{request_id}/messages", response_model=List[schemas.MessageOut])
def get_messages(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Message).filter(models.Message.request_id == request_id).all()
