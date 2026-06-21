from beanie import Document
from beanie.odm.fields import PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from typing import Optional, List
from datetime import datetime


class User(Document):
    name: str
    email: str
    hashed_password: str
    plain_password: Optional[str] = None
    role: str  # student, helper, admin
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    telegram_id: Optional[str] = None
    rating: float = 0.0
    completed_tasks: int = 0
    is_suspended: bool = False
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
        ]


class HelpRequest(Document):
    title: str
    subject: str
    description: str
    deadline: datetime
    budget: Optional[float] = None
    status: str = "open"  # open, in_progress, completed, cancelled
    contact_unlocked: bool = False
    is_urgent_print: bool = False
    attachments: Optional[List[str]] = None
    student_id: PydanticObjectId
    helper_id: Optional[PydanticObjectId] = None
    student_name: Optional[str] = None  # denormalized — avoids N+1 queries
    helper_name: Optional[str] = None   # denormalized
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "help_requests"
        indexes = [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("student_id", ASCENDING)]),
            IndexModel([("helper_id", ASCENDING)]),
        ]


class Message(Document):
    request_id: PydanticObjectId
    sender_id: PydanticObjectId
    content: Optional[str] = None
    attachment: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "messages"
        indexes = [IndexModel([("request_id", ASCENDING)])]


class Review(Document):
    request_id: PydanticObjectId
    rating: int
    feedback: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reviews"


class ActivityLog(Document):
    user_id: Optional[PydanticObjectId] = None
    action: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "activity_logs"
        indexes = [IndexModel([("timestamp", ASCENDING)])]


class Notification(Document):
    user_id: PydanticObjectId
    type: str
    title: str
    message: str
    is_read: bool = False
    related_request_id: Optional[PydanticObjectId] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "notifications"
        indexes = [IndexModel([("user_id", ASCENDING)])]


class PaymentDetection(Document):
    request_id: PydanticObjectId
    message_id: PydanticObjectId
    sender_id: PydanticObjectId
    detected_amount: Optional[float] = None
    payment_status: str = "initiated"
    detected_keywords: Optional[str] = None
    screenshot_url: Optional[str] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payment_detections"


class SystemSettings(Document):
    allowed_email_domain: str = "cvru.ac.in"
    admin_approval_required: bool = False
    commission_percentage: float = 10.0
    payment_system_enabled: bool = True
    platform_notice: Optional[str] = None

    class Settings:
        name = "system_settings"


class Milestone(Document):
    request_id: PydanticObjectId
    amount: float
    description: str
    status: str = "pending"  # pending, paid
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "milestones"


class Dispute(Document):
    request_id: PydanticObjectId
    raised_by_id: PydanticObjectId
    reason: str
    status: str = "open"  # open, resolved
    admin_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "disputes"


class MarketplaceItem(Document):
    title: str
    description: str
    file_path: str
    price: float = 0.0
    item_type: str
    admin_id: PydanticObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "marketplace_items"


class RazorpayOrder(Document):
    request_id: Optional[PydanticObjectId] = None
    student_id: PydanticObjectId
    razorpay_order_id: str
    amount: float  # always 20.0
    status: str = "created"  # created, paid, failed
    razorpay_payment_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None

    class Settings:
        name = "razorpay_orders"
        indexes = [
            IndexModel([("razorpay_order_id", ASCENDING)], unique=True),
        ]
