"""
Razorpay payment integration — ₹20 contact-unlock fee model.
  - /payments/config        — public: return key_id for checkout
  - /payments/create-order  — student creates ₹20 Razorpay order
  - /payments/verify        — verify signature, unlock contact details
  - /payments/history       — student sees their payment history
  - /payments/admin/orders  — admin sees all contact-unlock transactions
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import os
import razorpay

import models, schemas, auth, utils
from beanie.odm.fields import PydanticObjectId

payments_router = APIRouter(prefix="/payments", tags=["payments"])

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
CONTACT_UNLOCK_FEE  = 20.0   # ₹20 flat fee


def _rzp():
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Payment gateway not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env")
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ── Config (public) ──────────────────────────────────────────────────────────

@payments_router.get("/config")
def get_config():
    return {"key_id": RAZORPAY_KEY_ID}


# ── Create Order ─────────────────────────────────────────────────────────────

@payments_router.post("/create-order", response_model=schemas.PaymentOrderOut)
async def create_order(
    payload: schemas.PaymentOrderCreate,
    current_user: models.User = Depends(auth.get_current_user),
):
    auth.check_role(current_user, ["student"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(payload.request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if req.status != "in_progress":
        raise HTTPException(status_code=400, detail="Contact can only be unlocked after a helper accepts the request")
    if req.contact_unlocked:
        raise HTTPException(status_code=400, detail="Contact details already unlocked for this request")

    client = _rzp()
    amount_paise = int(CONTACT_UNLOCK_FEE * 100)  # 2000 paise = ₹20

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"unlock_{str(req.id)}_{str(current_user.id)}",
            "notes": {
                "request_id": str(req.id),
                "student_id": str(current_user.id),
                "type": "contact_unlock",
            }
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay order creation failed: {e}")

    db_order = models.RazorpayOrder(
        request_id=req.id,
        student_id=current_user.id,
        razorpay_order_id=order["id"],
        amount=CONTACT_UNLOCK_FEE,
        status="created",
    )
    await db_order.insert()

    return schemas.PaymentOrderOut(
        razorpay_order_id=order["id"],
        amount=amount_paise,
        currency="INR",
        request_title=req.title,
        request_id=str(req.id),
    )


# ── Verify Payment ────────────────────────────────────────────────────────────

@payments_router.post("/verify", response_model=schemas.PaymentVerifyResponse)
async def verify_payment(
    payload: schemas.PaymentVerifyRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    client = _rzp()

    # 1. Verify Razorpay signature
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id":   payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature":  payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Payment signature verification failed — possible tampering")

    # 2. Find the order record
    db_order = await models.RazorpayOrder.find_one(
        models.RazorpayOrder.razorpay_order_id == payload.razorpay_order_id
    )
    if not db_order:
        raise HTTPException(status_code=404, detail="Order record not found")
    if db_order.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Order does not belong to you")
    if db_order.status == "paid":
        raise HTTPException(status_code=400, detail="Payment already verified")

    # 3. Mark order as paid
    db_order.status = "paid"
    db_order.razorpay_payment_id = payload.razorpay_payment_id
    db_order.paid_at = datetime.utcnow()
    await db_order.save()

    # 4. Unlock contact on the help request
    req = await models.HelpRequest.find_one(models.HelpRequest.id == db_order.request_id) if db_order.request_id else None
    if req:
        req.contact_unlocked = True
        await req.save()

    # 5. Notify helper
    if req and req.helper_id:
        helper = await models.User.find_one(models.User.id == req.helper_id)
        if helper:
            await models.Notification(
                user_id=helper.id,
                type="contact_unlock",
                title="Contact Details Unlocked",
                message=f"A student has unlocked your contact details for request '{req.title}'. They can now reach you directly.",
                related_request_id=req.id,
            ).insert()

    # 6. Notify student
    await models.Notification(
        user_id=current_user.id,
        type="contact_unlock",
        title="Contact Details Unlocked!",
        message=f"You have successfully unlocked the helper's contact details for '{req.title if req else 'your request'}'. You can now reach them directly.",
        related_request_id=req.id if req else None,
    ).insert()

    await utils.log_admin_action(
        current_user.id, "contact_unlock_payment",
        f"₹{CONTACT_UNLOCK_FEE} paid — Contact unlocked for Request #{str(db_order.request_id)}"
    )

    return schemas.PaymentVerifyResponse(
        success=True,
        message="Payment verified. Contact details are now unlocked!",
        amount_paid=CONTACT_UNLOCK_FEE,
    )


# ── Payment History ───────────────────────────────────────────────────────────

@payments_router.get("/history")
async def get_history(current_user: models.User = Depends(auth.get_current_user)):
    orders = await models.RazorpayOrder.find(
        models.RazorpayOrder.student_id == current_user.id,
        models.RazorpayOrder.status == "paid",
    ).sort("-paid_at").to_list()
    return [
        {
            "id": str(o.id),
            "request_id": str(o.request_id) if o.request_id else None,
            "amount": o.amount,
            "status": o.status,
            "razorpay_payment_id": o.razorpay_payment_id,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in orders
    ]


# ── Admin: all contact-unlock transactions ────────────────────────────────────

@payments_router.get("/admin/orders")
async def admin_orders(current_user: models.User = Depends(auth.get_current_admin)):
    orders = await models.RazorpayOrder.find(
        models.RazorpayOrder.status == "paid"
    ).sort("-paid_at").to_list()
    result = []
    for o in orders:
        student = await models.User.find_one(models.User.id == o.student_id) if o.student_id else None
        req = await models.HelpRequest.find_one(models.HelpRequest.id == o.request_id) if o.request_id else None
        result.append({
            "id": str(o.id),
            "student_name": student.name if student else "Unknown",
            "student_email": student.email if student else "",
            "request_title": req.title if req else "Unknown",
            "amount": o.amount,
            "razorpay_payment_id": o.razorpay_payment_id,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        })
    return result
