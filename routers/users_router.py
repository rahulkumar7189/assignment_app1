from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
import models, schemas, auth, database

router = APIRouter(tags=["users"])

@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@router.get("/me/stats")
def get_my_stats(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role == "student":
        total_requests = db.query(models.HelpRequest).filter(models.HelpRequest.student_id == current_user.id).count()
        completed = db.query(models.HelpRequest).filter(models.HelpRequest.student_id == current_user.id, models.HelpRequest.status == "completed").count()
        ongoing = db.query(models.HelpRequest).filter(models.HelpRequest.student_id == current_user.id, models.HelpRequest.status == "in_progress").count()
        spent = db.query(func.sum(models.HelpRequest.budget)).filter(
            models.HelpRequest.student_id == current_user.id,
            models.HelpRequest.status == "completed"
        ).scalar() or 0.0
        return {
            "total_requests": total_requests,
            "completed": completed,
            "ongoing": ongoing,
            "total_spent": spent,
            "wallet_balance": 0.0 # Placeholder for wallet feature
        }
    else:
        total_requests = db.query(models.HelpRequest).filter(models.HelpRequest.helper_id == current_user.id).count()
        completed = db.query(models.HelpRequest).filter(models.HelpRequest.helper_id == current_user.id, models.HelpRequest.status == "completed").count()
        ongoing = db.query(models.HelpRequest).filter(models.HelpRequest.helper_id == current_user.id, models.HelpRequest.status == "in_progress").count()
        earned = db.query(func.sum(models.HelpRequest.budget)).filter(
            models.HelpRequest.helper_id == current_user.id,
            models.HelpRequest.status == "completed"
        ).scalar() or 0.0
        return {
            "total_requests": total_requests,
            "completed": completed,
            "ongoing": ongoing,
            "total_earned": earned,
            "wallet_balance": 0.0 # Placeholder for wallet feature
        }
