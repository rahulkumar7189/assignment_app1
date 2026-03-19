from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
import database, models, schemas

from dotenv import load_dotenv
import os

# Load .env from the current file's directory
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

import database, models, schemas

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = 7 # Added

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login") # Modified tokenUrl

def get_password_hash(password): # Reordered
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password): # Reordered
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict): # Modified
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict): # Added
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type") # Added
        
        if email is None or token_type != "access": # Modified
            raise credentials_exception
        token_data = schemas.TokenData(email=email) # Added
    except JWTError as e: # Modified
        print(f"Token validation error: {e}") # Added
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == token_data.email).first() # Modified
    if user is None:
        raise credentials_exception
    if user.is_suspended: # Added
        raise HTTPException(status_code=403, detail="User account is suspended")
    return user

def get_current_admin(current_user: models.User = Depends(get_current_user)): # Added
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin only."
        )
    return current_user

def check_role(user: models.User, allowed_roles: List[str]): # Modified signature and content
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"Role {user.role} not authorized for this action")
    return True
