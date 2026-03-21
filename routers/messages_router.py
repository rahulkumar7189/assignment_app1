from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth, database
from routers.notifications_router import create_notification
import uuid, os, re

router = APIRouter(tags=["messages"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"}

PAYMENT_KEYWORDS = [
    "paid", "payment", "pay", "upi", "transferred", "transfer",
    "gpay", "google pay", "phonepe", "paytm", "bhim",
    "transaction", "receipt", "screenshot", "sent money",
    "received money", "bank transfer", "neft", "imps", "rtgs",
    "advance payment", "advance paid", "payment done", "payment confirmed",
    "payment successful", "payment completed", "amount sent", "money sent"
]

AMOUNT_PATTERNS = [
    r'₹\s*(\d+[\d,]*\.?\d*)',
    r'Rs\.?\s*(\d+[\d,]*\.?\d*)',
    r'INR\s*(\d+[\d,]*\.?\d*)',
    r'(\d+[\d,]*\.?\d*)\s*(?:rupees|rs|inr)',
    r'(\d+[\d,]*\.?\d*)\s*₹',
]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

def _detect_payment(content: str, attachment: str = None):
    """Check message for payment-related content. Returns (is_payment, amount, keywords, is_screenshot)."""
    found_keywords = []
    amount = None
    is_screenshot = False

    if content:
        content_lower = content.lower()
        for kw in PAYMENT_KEYWORDS:
            if kw in content_lower:
                found_keywords.append(kw)

        # Extract amount
        for pattern in AMOUNT_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                try:
                    amount = float(match.group(1).replace(',', ''))
                except ValueError:
                    pass
                break

    if attachment:
        ext = os.path.splitext(attachment)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            # Check if filename or content suggests payment screenshot
            attachment_lower = attachment.lower()
            if any(kw in attachment_lower for kw in ["payment", "screenshot", "upi", "gpay", "transaction", "receipt"]):
                is_screenshot = True
                found_keywords.append("payment_screenshot")
            # If message content has payment keywords and there's an image, likely a screenshot
            elif found_keywords:
                is_screenshot = True
                found_keywords.append("image_with_payment_context")

    # Determine payment status
    confirmed_keywords = ["payment done", "payment confirmed", "payment successful", "payment completed", "transferred", "paid"]
    status = "initiated"
    if content:
        content_lower = content.lower()
        for ck in confirmed_keywords:
            if ck in content_lower:
                status = "confirmed"
                break

    return len(found_keywords) > 0, amount, ", ".join(found_keywords), is_screenshot, status


def _save_payment_detection(db: Session, request_id: int, message_id: int, sender_id: int, amount, keywords, screenshot_url, status):
    """Save a payment detection record."""
    try:
        detection = models.PaymentDetection(
            request_id=request_id,
            message_id=message_id,
            sender_id=sender_id,
            detected_amount=amount,
            payment_status=status,
            detected_keywords=keywords,
            screenshot_url=screenshot_url
        )
        db.add(detection)
        db.commit()
    except Exception as e:
        print(f"Error saving payment detection: {e}")
        db.rollback()


def _verify_chat_access(request_id: int, db: Session, current_user: models.User):
    """Verify the request exists and the user is part of it."""
    help_request = db.query(models.HelpRequest).filter(models.HelpRequest.id == request_id).first()
    if not help_request:
        raise HTTPException(status_code=404, detail="Request not found")
    if current_user.id != help_request.student_id and current_user.id != help_request.helper_id:
        raise HTTPException(status_code=403, detail="Not authorized for this chat")
    return help_request

@router.get("/requests/{request_id}/messages", response_model=List[schemas.MessageOut])
def get_messages(request_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    _verify_chat_access(request_id, db, current_user)
    return db.query(models.Message).filter(models.Message.request_id == request_id).order_by(models.Message.timestamp.asc()).all()

@router.post("/requests/{request_id}/messages", response_model=schemas.MessageOut)
def create_message(request_id: int, message: schemas.MessageBase, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    help_request = _verify_chat_access(request_id, db, current_user)
    
    new_msg = models.Message(
        request_id=request_id,
        sender_id=current_user.id,
        content=message.content
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Create notification for the other user
    recipient_id = help_request.helper_id if current_user.id == help_request.student_id else help_request.student_id
    if recipient_id:
        create_notification(
            db, recipient_id, "message",
            f"New message in: {help_request.title}",
            f"{current_user.name}: {(message.content or '')[:100]}",
            related_request_id=request_id
        )

    # Payment detection
    is_payment, amount, keywords, is_screenshot, pay_status = _detect_payment(message.content)
    if is_payment:
        _save_payment_detection(db, request_id, new_msg.id, current_user.id, amount, keywords, None, pay_status)

    return new_msg

@router.post("/requests/{request_id}/messages/upload", response_model=schemas.MessageOut)
async def create_message_with_attachment(
    request_id: int,
    file: UploadFile = File(...),
    content: Optional[str] = Form(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    help_request = _verify_chat_access(request_id, db, current_user)

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed.")

    # Save file
    unique_name = f"{uuid.uuid4()}{ext}"
    save_path = os.path.join("uploads", "chat", unique_name)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    file_bytes = await file.read()
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    attachment_url = f"/uploads/chat/{unique_name}"

    new_msg = models.Message(
        request_id=request_id,
        sender_id=current_user.id,
        content=content,
        attachment=attachment_url
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Create notification for the other user
    recipient_id = help_request.helper_id if current_user.id == help_request.student_id else help_request.student_id
    if recipient_id:
        msg_preview = content[:100] if content else "Sent an attachment"
        create_notification(
            db, recipient_id, "message",
            f"New message in: {help_request.title}",
            f"{current_user.name}: {msg_preview}",
            related_request_id=request_id
        )

    # Payment detection
    is_payment, amount, keywords, is_screenshot, pay_status = _detect_payment(content, attachment_url)
    if is_payment:
        screenshot = attachment_url if is_screenshot else None
        _save_payment_detection(db, request_id, new_msg.id, current_user.id, amount, keywords, screenshot, pay_status)

    return new_msg
