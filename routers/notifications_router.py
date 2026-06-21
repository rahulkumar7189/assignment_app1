from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import models, schemas, auth
from beanie.odm.fields import PydanticObjectId

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=List[schemas.NotificationOut])
async def get_notifications(current_user: models.User = Depends(auth.get_current_user)):
    return await models.Notification.find(
        models.Notification.user_id == current_user.id
    ).sort("-created_at").limit(50).to_list()


@router.get("/unread-count")
async def get_unread_count(current_user: models.User = Depends(auth.get_current_user)):
    count = await models.Notification.find(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False,
    ).count()
    return {"count": count}


@router.put("/{notification_id}/read")
async def mark_read(notification_id: str, current_user: models.User = Depends(auth.get_current_user)):
    notif = await models.Notification.find_one(
        models.Notification.id == PydanticObjectId(notification_id),
        models.Notification.user_id == current_user.id,
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    await notif.save()
    return {"message": "Marked as read"}


@router.put("/read-all")
async def mark_all_read(current_user: models.User = Depends(auth.get_current_user)):
    await models.Notification.find(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False,
    ).update({"$set": {"is_read": True}})
    return {"message": "All notifications marked as read"}


async def create_notification(
    user_id,
    notif_type: str,
    title: str,
    message: str,
    related_request_id=None,
):
    try:
        notif = models.Notification(
            user_id=user_id,
            type=notif_type,
            title=title,
            message=message,
            related_request_id=related_request_id,
        )
        await notif.insert()
    except Exception as e:
        print(f"Error creating notification: {e}")
