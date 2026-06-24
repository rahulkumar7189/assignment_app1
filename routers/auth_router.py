from fastapi import APIRouter, Depends, HTTPException, Response, status, Cookie
import models, schemas, auth, utils
from typing import Optional
from jose import jwt, JWTError

router = APIRouter(tags=["authentication"])


@router.post("/register", response_model=schemas.UserOut)
async def register(user: schemas.UserCreate):
    import traceback
    try:
        db_user = await models.User.find_one(models.User.email == user.email)
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pwd = auth.get_password_hash(user.password)
        if user.role == "helper" and not user.upi_id:
            raise HTTPException(status_code=400, detail="UPI ID is required for helpers")
        if user.upi_id and "@" not in user.upi_id:
            raise HTTPException(status_code=400, detail="UPI ID must be in format name@upi")

        new_user = models.User(
            name=user.name,
            email=user.email,
            hashed_password=hashed_pwd,
            plain_password=user.password,
            role=user.role,
            phone_number=user.phone_number,
            upi_id=user.upi_id if user.role == "helper" else None,
        )
        await new_user.insert()
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=schemas.Token)
async def login(user_credentials: schemas.UserLogin, response: Response):
    user = await models.User.find_one(models.User.email == user_credentials.email)
    if not user or not auth.verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    refresh_token = auth.create_refresh_token(data={"sub": user.email})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=auth.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        expires=auth.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=False,
    )

    if user.role == "admin":
        await utils.log_admin_action(user.id, "login", "Admin logged into dashboard")

    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}


@router.post("/refresh", response_model=schemas.Token)
async def refresh(refresh_token: Optional[str] = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        payload = jwt.decode(refresh_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")

        if email is None or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user = await models.User.find_one(models.User.email == email)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        new_access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
        return {"access_token": new_access_token, "token_type": "bearer"}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}
