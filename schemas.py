from pydantic import BaseModel, EmailStr, BeforeValidator
from typing import Optional, List, Annotated
from datetime import datetime

# Converts PydanticObjectId / ObjectId to str automatically in all response schemas
PyObjectId = Annotated[str, BeforeValidator(str)]


class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: str
    phone_number: Optional[str] = None


class UserCreate(UserBase):
    password: str
    whatsapp_number: Optional[str] = None
    telegram_id: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(UserBase):
    id: PyObjectId
    rating: float
    completed_tasks: int
    is_suspended: bool
    is_verified: bool
    created_at: datetime
    whatsapp_number: Optional[str] = None
    telegram_id: Optional[str] = None

    class Config:
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


class SystemSettingsUpdate(BaseModel):
    allowed_email_domain: Optional[str] = None
    admin_approval_required: Optional[bool] = None
    commission_percentage: Optional[float] = None
    payment_system_enabled: Optional[bool] = None
    platform_notice: Optional[str] = None


class ActivityLogOut(BaseModel):
    id: PyObjectId
    user_id: Optional[PyObjectId] = None
    action: str
    details: Optional[str] = None
    timestamp: datetime

    class Config:
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
    id: PyObjectId
    student_id: PyObjectId
    helper_id: Optional[PyObjectId] = None
    status: str
    contact_unlocked: bool = False
    attachments: Optional[List[str]] = None
    created_at: datetime
    student_name: Optional[str] = None
    helper_name: Optional[str] = None
    peer_phone: Optional[str] = None
    peer_email: Optional[str] = None
    peer_whatsapp: Optional[str] = None
    peer_telegram: Optional[str] = None

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    content: Optional[str] = None


class MessageCreate(MessageBase):
    request_id: str


class MessageOut(BaseModel):
    id: PyObjectId
    request_id: PyObjectId
    sender_id: PyObjectId
    content: Optional[str] = None
    attachment: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class ReviewCreate(BaseModel):
    request_id: str
    rating: int
    feedback: str


class ReviewOut(ReviewCreate):
    id: PyObjectId
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationOut(BaseModel):
    id: PyObjectId
    user_id: PyObjectId
    type: str
    title: str
    message: str
    is_read: bool
    related_request_id: Optional[PyObjectId] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserOut(BaseModel):
    id: PyObjectId
    name: str
    email: str
    role: str
    phone_number: Optional[str] = None
    plain_password: Optional[str] = None
    rating: float
    completed_tasks: int
    is_verified: bool
    is_suspended: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentDetectionOut(BaseModel):
    id: PyObjectId
    request_id: PyObjectId
    message_id: PyObjectId
    sender_id: PyObjectId
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
    id: PyObjectId
    request_id: PyObjectId
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DisputeCreate(BaseModel):
    request_id: str
    reason: str


class DisputeOut(DisputeCreate):
    id: PyObjectId
    raised_by_id: PyObjectId
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
    id: PyObjectId
    file_path: str
    admin_id: PyObjectId
    created_at: datetime

    class Config:
        from_attributes = True


# ── Payment schemas ──────────────────────────────────────────────────────────

class PaymentOrderCreate(BaseModel):
    request_id: str


class PaymentOrderOut(BaseModel):
    razorpay_order_id: str
    amount: int        # in paise
    currency: str
    request_title: str
    request_id: str


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    request_id: str


class PaymentVerifyResponse(BaseModel):
    success: bool
    message: str
    amount_paid: float


class PaymentButtonVerifyRequest(BaseModel):
    razorpay_payment_link_id: str
    razorpay_payment_link_reference_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    request_id: str


class RazorpayOrderOut(BaseModel):
    id: PyObjectId
    request_id: Optional[PyObjectId] = None
    amount: float
    status: str
    razorpay_payment_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
