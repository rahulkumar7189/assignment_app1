from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: str
    phone_number: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(UserBase):
    id: int
    rating: float
    completed_tasks: int
    is_suspended: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True
        from_attributes = True

# Admin Schemas
class AdminOverview(BaseModel):
    total_users: int
    total_helpers: int
    total_students: int
    pending_verifications: int
    active_requests: int
    completed_requests: int
    total_transactions: int
    revenue_summary: float

class SystemSettingsOut(BaseModel):
    allowed_email_domain: str
    admin_approval_required: bool
    commission_percentage: float
    payment_system_enabled: bool
    platform_notice: Optional[str] = None

    class Config:
        from_attributes = True
        from_attributes = True

class SystemSettingsUpdate(BaseModel):
    allowed_email_domain: Optional[str] = None
    admin_approval_required: Optional[bool] = None
    commission_percentage: Optional[float] = None
    payment_system_enabled: Optional[bool] = None
    platform_notice: Optional[str] = None

class ActivityLogOut(BaseModel):
    id: int
    user_id: int
    action: str
    details: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class HelpRequestBase(BaseModel):
    title: str
    subject: str
    description: str
    deadline: datetime
    budget: Optional[float] = None
    is_urgent_print: Optional[bool] = False

class HelpRequestCreate(HelpRequestBase):
    pass

class HelpRequestOut(HelpRequestBase):
    id: int
    student_id: int
    helper_id: Optional[int] = None
    status: str
    advance_paid: bool = False
    attachments: Optional[List[str]] = None
    created_at: datetime
    
    # We will compute these in the response manually to ensure security
    student_name: Optional[str] = None
    helper_name: Optional[str] = None
    peer_phone: Optional[str] = None

    class Config:
        from_attributes = True
        from_attributes = True

class MessageBase(BaseModel):
    content: Optional[str] = None

class MessageCreate(MessageBase):
    request_id: int

class MessageOut(BaseModel):
    id: int
    request_id: int
    sender_id: int
    content: Optional[str] = None
    attachment: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True

class ReviewCreate(BaseModel):
    request_id: int
    rating: int
    feedback: str

class ReviewOut(ReviewCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
        from_attributes = True

class NotificationOut(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str
    is_read: bool
    related_request_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AdminUserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    phone_number: Optional[str] = None
    plain_password: Optional[str] = None
    is_verified: bool
    is_suspended: bool
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentDetectionOut(BaseModel):
    id: int
    request_id: int
    message_id: int
    sender_id: int
    detected_amount: Optional[float] = None
    payment_status: str
    detected_keywords: Optional[str] = None
    screenshot_url: Optional[str] = None
    detected_at: datetime

    class Config:
        from_attributes = True

class MilestoneCreate(BaseModel):
    amount: float
    description: str

class MilestoneOut(MilestoneCreate):
    id: int
    request_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class DisputeCreate(BaseModel):
    request_id: int
    reason: str

class DisputeOut(DisputeCreate):
    id: int
    raised_by_id: int
    status: str
    admin_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class MarketplaceItemCreate(BaseModel):
    title: str
    description: str
    price: float
    item_type: str

class MarketplaceItemOut(MarketplaceItemCreate):
    id: int
    file_path: str
    admin_id: int
    created_at: datetime

    class Config:
        from_attributes = True
