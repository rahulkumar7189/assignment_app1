from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base
import datetime
import enum

class UserRole(str, enum.Enum):
    STUDENT = "student"
    HELPER = "helper"
    ADMIN = "admin"

class RequestStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String) # student, helper, admin
    phone_number = Column(String, nullable=True)
    rating = Column(Float, default=0.0)
    completed_tasks = Column(Integer, default=0)
    is_suspended = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    requests_as_student = relationship("HelpRequest", foreign_keys="HelpRequest.student_id", back_populates="student")
    requests_as_helper = relationship("HelpRequest", foreign_keys="HelpRequest.helper_id", back_populates="helper")

class HelpRequest(Base):
    __tablename__ = "help_requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    subject = Column(String)
    description = Column(Text)
    deadline = Column(DateTime)
    budget = Column(Float, nullable=True)
    status = Column(String, default="open") # open, in_progress, completed, cancelled
    advance_paid = Column(Boolean, default=False)
    attachments = Column(Text, nullable=True) # JSON list of file paths
    
    student_id = Column(Integer, ForeignKey("users.id"))
    helper_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    student = relationship("User", foreign_keys=[student_id], back_populates="requests_as_student")
    helper = relationship("User", foreign_keys=[helper_id], back_populates="requests_as_helper")
    messages = relationship("Message", back_populates="request")
    reviews = relationship("Review", back_populates="request")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("help_requests.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    request = relationship("HelpRequest", back_populates="messages")

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("help_requests.id"))
    rating = Column(Integer)
    feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    request = relationship("HelpRequest", back_populates="reviews")

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    allowed_email_domain = Column(String, default="cvru.ac.in")
    admin_approval_required = Column(Boolean, default=False)
    commission_percentage = Column(Float, default=10.0)
    payment_system_enabled = Column(Boolean, default=True)
    platform_notice = Column(String, nullable=True)
