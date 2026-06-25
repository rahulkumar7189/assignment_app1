from fastapi import APIRouter, Depends
from bson import ObjectId
import models, schemas, auth
import database

router = APIRouter(tags=["users"])


@router.get("/me", response_model=schemas.UserOut)
async def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("/me/stats")
async def get_my_stats(current_user: models.User = Depends(auth.get_current_user)):
    uid = ObjectId(str(current_user.id))

    import os
    db = database.motor_client[os.getenv("MONGO_DB_NAME", "acadmate")]
    col = db["help_requests"]

    if current_user.role == "student":
        total_requests = await models.HelpRequest.find(
            models.HelpRequest.student_id == current_user.id
        ).count()
        completed = await models.HelpRequest.find(
            models.HelpRequest.student_id == current_user.id,
            models.HelpRequest.status == "completed",
        ).count()
        ongoing = await models.HelpRequest.find(
            models.HelpRequest.student_id == current_user.id,
            models.HelpRequest.status == "in_progress",
        ).count()
        pipeline = [
            {"$match": {"student_id": uid, "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$budget"}}},
        ]
        result = await col.aggregate(pipeline).to_list(length=None)
        spent = result[0]["total"] if result else 0.0
        return {
            "total_requests": total_requests,
            "completed": completed,
            "ongoing": ongoing,
            "total_spent": spent,
            "wallet_balance": 0.0,
        }
    else:
        total_requests = await models.HelpRequest.find(
            models.HelpRequest.helper_id == current_user.id
        ).count()
        completed = await models.HelpRequest.find(
            models.HelpRequest.helper_id == current_user.id,
            models.HelpRequest.status == "completed",
        ).count()
        ongoing = await models.HelpRequest.find(
            models.HelpRequest.helper_id == current_user.id,
            models.HelpRequest.status == "in_progress",
        ).count()
        pipeline = [
            {"$match": {"helper_id": uid, "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$budget"}}},
        ]
        result = await col.aggregate(pipeline).to_list(length=None)
        earned = result[0]["total"] if result else 0.0
        return {
            "total_requests": total_requests,
            "completed": completed,
            "ongoing": ongoing,
            "total_earned": earned,
            "wallet_balance": 0.0,
        }
