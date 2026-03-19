from fastapi import APIRouter, Depends
import models, schemas, auth

router = APIRouter(tags=["users"])

@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user
