"""
Razorpay payment integration — anonymous escrow model.
  - /payments/config                  — public: return key_id for checkout
  - /payments/create-posting-fee-order — student creates ₹9 order to publish assignment
  - /payments/verify-posting-fee       — verify ₹9 payment, set request open
  - /payments/create-assignment-order  — student creates order for full budget (after admin verifies work)
  - /payments/verify-assignment-payment — verify full payment, auto-payout 90% to helper UPI
  - /payments/history                  — student payment history
  - /payments/admin/orders             — admin sees all transactions
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import os
import razorpay

import models, schemas, auth, utils
from beanie.odm.fields import PydanticObjectId

payments_router = APIRouter(prefix="/payments", tags=["payments"])

RAZORPAY_KEY_ID      = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET  = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_ACCOUNT_NUM = os.getenv("RAZORPAY_ACCOUNT_NUMBER", "")
POSTING_FEE          = float(os.getenv("POSTING_FEE", "9"))
COMMISSION_PERCENT   = float(os.getenv("PLATFORM_COMMISSION_PERCENT", "10"))


def _rzp():
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Payment gateway not configured")
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


async def _notify(user_id, notif_type, title, message, request_id=None):
    await models.Notification(
        user_id=user_id, type=notif_type, title=title,
        message=message, related_request_id=request_id,
    ).insert()


# ── Config (public) ──────────────────────────────────────────────────────────

@payments_router.get("/config")
def get_config():
    return {"key_id": RAZORPAY_KEY_ID}


# ── Posting Fee (₹9) — Payment Button verify ────────────────────────────────

@payments_router.post("/verify-button-posting-fee", response_model=schemas.PaymentVerifyResponse)
async def verify_button_posting_fee(
    payload: schemas.ButtonPaymentVerifyRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Verify the ₹9 Razorpay Payment Button payment and publish the assignment."""
    auth.check_role(current_user, ["student"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(payload.request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if req.posting_fee_paid:
        raise HTTPException(status_code=400, detail="Posting fee already paid for this request")

    # Verify Razorpay Payment Button signature
    client = _rzp()
    try:
        client.utility.verify_payment_link_signature({
            "payment_link_id":               payload.razorpay_payment_link_id,
            "payment_link_reference_id":     payload.razorpay_payment_link_reference_id,
            "payment_id":                    payload.razorpay_payment_id,
            "signature":                     payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    # Record payment
    db_order = models.RazorpayOrder(
        request_id=req.id,
        student_id=current_user.id,
        razorpay_order_id=payload.razorpay_payment_link_id,
        order_type="posting_fee",
        amount=POSTING_FEE,
        status="paid",
        razorpay_payment_id=payload.razorpay_payment_id,
        paid_at=datetime.utcnow(),
    )
    await db_order.insert()

    # Publish the request
    req.posting_fee_paid = True
    req.status = "open"
    await req.save()

    await _notify(
        current_user.id, "posting_fee_paid",
        "Assignment Published!",
        f"Your assignment '{req.title}' is now live. Helpers can see and accept it.",
        req.id,
    )

    return schemas.PaymentVerifyResponse(
        success=True,
        message="Posting fee paid. Your assignment is now live!",
        amount_paid=POSTING_FEE,
    )


# ── Posting Fee (₹9) — create order (custom checkout fallback) ──────────────

@payments_router.post("/create-posting-fee-order", response_model=schemas.PaymentOrderOut)
async def create_posting_fee_order(
    payload: schemas.PaymentOrderCreate,
    current_user: models.User = Depends(auth.get_current_user),
):
    auth.check_role(current_user, ["student"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(payload.request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if req.posting_fee_paid:
        raise HTTPException(status_code=400, detail="Posting fee already paid for this request")

    client = _rzp()
    amount_paise = int(POSTING_FEE * 100)

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"post_{str(req.id)}",
            "notes": {"request_id": str(req.id), "type": "posting_fee"},
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay order creation failed: {e}")

    db_order = models.RazorpayOrder(
        request_id=req.id,
        student_id=current_user.id,
        razorpay_order_id=order["id"],
        order_type="posting_fee",
        amount=POSTING_FEE,
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


# ── Posting Fee — verify ─────────────────────────────────────────────────────

@payments_router.post("/verify-posting-fee", response_model=schemas.PaymentVerifyResponse)
async def verify_posting_fee(
    payload: schemas.PaymentVerifyRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    client = _rzp()

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id":   payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature":  payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    db_order = await models.RazorpayOrder.find_one(
        models.RazorpayOrder.razorpay_order_id == payload.razorpay_order_id
    )
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if db_order.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Order does not belong to you")
    if db_order.status == "paid":
        raise HTTPException(status_code=400, detail="Payment already verified")

    db_order.status = "paid"
    db_order.razorpay_payment_id = payload.razorpay_payment_id
    db_order.paid_at = datetime.utcnow()
    await db_order.save()

    req = await models.HelpRequest.find_one(models.HelpRequest.id == db_order.request_id) if db_order.request_id else None
    if req:
        req.posting_fee_paid = True
        req.status = "open"
        await req.save()

    await _notify(
        current_user.id, "posting_fee_paid",
        "Assignment Published!",
        f"Your assignment '{req.title if req else ''}' is now live. Helpers can see and accept it.",
        req.id if req else None,
    )

    return schemas.PaymentVerifyResponse(
        success=True,
        message="Posting fee paid. Your assignment is now live!",
        amount_paid=POSTING_FEE,
    )


# ── Assignment Payment — create order ────────────────────────────────────────

@payments_router.post("/create-assignment-order", response_model=schemas.PaymentOrderOut)
async def create_assignment_order(
    payload: schemas.PaymentOrderCreate,
    current_user: models.User = Depends(auth.get_current_user),
):
    auth.check_role(current_user, ["student"])

    req = await models.HelpRequest.find_one(models.HelpRequest.id == PydanticObjectId(payload.request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if req.status != "awaiting_payment":
        raise HTTPException(status_code=400, detail="Assignment work has not been verified by admin yet")
    if not req.budget or req.budget <= 0:
        raise HTTPException(status_code=400, detail="Request has no valid budget set")

    client = _rzp()
    amount_paise = int(req.budget * 100)

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"assign_{str(req.id)}",
            "notes": {"request_id": str(req.id), "type": "assignment_payment"},
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay order creation failed: {e}")

    db_order = models.RazorpayOrder(
        request_id=req.id,
        student_id=current_user.id,
        razorpay_order_id=order["id"],
        order_type="assignment_payment",
        amount=req.budget,
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


# ── Assignment Payment — verify + auto-payout ────────────────────────────────

@payments_router.post("/verify-assignment-payment", response_model=schemas.AssignmentPaymentVerifyResponse)
async def verify_assignment_payment(
    payload: schemas.PaymentVerifyRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    client = _rzp()

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id":   payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature":  payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    db_order = await models.RazorpayOrder.find_one(
        models.RazorpayOrder.razorpay_order_id == payload.razorpay_order_id
    )
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if db_order.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Order does not belong to you")
    if db_order.status == "paid":
        raise HTTPException(status_code=400, detail="Payment already verified")

    req = await models.HelpRequest.find_one(models.HelpRequest.id == db_order.request_id) if db_order.request_id else None
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Calculate split
    platform_fee   = round(db_order.amount * (COMMISSION_PERCENT / 100), 2)
    helper_amount  = round(db_order.amount - platform_fee, 2)

    # Initiate payout to helper's UPI
    payout_id = None
    helper = await models.User.find_one(models.User.id == req.helper_id) if req.helper_id else None
    if helper and helper.upi_id and RAZORPAY_ACCOUNT_NUM:
        payout_id = await _initiate_payout(client, helper, helper_amount)

    # Mark order paid
    db_order.status = "paid"
    db_order.razorpay_payment_id = payload.razorpay_payment_id
    db_order.paid_at = datetime.utcnow()
    db_order.platform_fee_amount = platform_fee
    db_order.helper_payout_amount = helper_amount
    db_order.razorpay_payout_id = payout_id
    await db_order.save()

    # Mark request completed
    req.status = "completed"
    req.payout_initiated = payout_id is not None
    await req.save()

    if helper:
        helper.completed_tasks += 1
        await helper.save()

    # Notifications
    await _notify(
        current_user.id, "payment_confirmed",
        "Payment Confirmed!",
        f"Your payment of ₹{db_order.amount:.0f} is confirmed. Your assignment is ready to download.",
        req.id,
    )
    if helper:
        upi_display = helper.upi_id if helper.upi_id else "your registered UPI"
        await _notify(
            helper.id, "payout_initiated",
            "Payment Received!",
            f"The student paid ₹{db_order.amount:.0f} for '{req.title}'. ₹{helper_amount:.0f} is being transferred to {upi_display}.",
            req.id,
        )

    await utils.log_admin_action(
        current_user.id, "assignment_payment",
        f"₹{db_order.amount:.0f} paid for Request #{str(req.id)} — platform ₹{platform_fee:.0f}, helper ₹{helper_amount:.0f}"
    )

    return schemas.AssignmentPaymentVerifyResponse(
        success=True,
        message="Payment confirmed. Your assignment is ready to download!",
        amount_paid=db_order.amount,
        platform_fee=platform_fee,
        helper_payout=helper_amount,
    )


async def _initiate_payout(client: razorpay.Client, helper: models.User, amount_rupees: float) -> str | None:
    try:
        contact = client.contact.create({
            "name": helper.name,
            "email": helper.email,
            "contact": helper.phone_number or "",
            "type": "vendor",
        })
        fund_account = client.fund_account.create({
            "contact_id": contact["id"],
            "account_type": "vpa",
            "vpa": {"address": helper.upi_id},
        })
        payout = client.payout.create({
            "account_number": RAZORPAY_ACCOUNT_NUM,
            "fund_account_id": fund_account["id"],
            "amount": int(amount_rupees * 100),
            "currency": "INR",
            "mode": "UPI",
            "purpose": "payout",
            "queue_if_low_balance": True,
        })
        return payout["id"]
    except Exception as e:
        # Log but don't fail the payment — admin can manual-transfer
        await utils.log_admin_action(
            helper.id, "payout_failed",
            f"Auto-payout of ₹{amount_rupees:.0f} to {helper.upi_id} failed: {e}"
        )
        return None


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
            "order_type": o.order_type,
            "amount": o.amount,
            "platform_fee": o.platform_fee_amount,
            "helper_payout": o.helper_payout_amount,
            "status": o.status,
            "razorpay_payment_id": o.razorpay_payment_id,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in orders
    ]


# ── Admin: all transactions ───────────────────────────────────────────────────

@payments_router.get("/admin/orders")
async def admin_orders(current_user: models.User = Depends(auth.get_current_admin)):
    orders = await models.RazorpayOrder.find(
        models.RazorpayOrder.status == "paid"
    ).sort("-paid_at").to_list()
    result = []
    for o in orders:
        student = await models.User.find_one(models.User.id == o.student_id) if o.student_id else None
        req     = await models.HelpRequest.find_one(models.HelpRequest.id == o.request_id) if o.request_id else None
        result.append({
            "id": str(o.id),
            "order_type": o.order_type,
            "student_name": student.name if student else "Unknown",
            "student_email": student.email if student else "",
            "request_title": req.title if req else "Unknown",
            "amount": o.amount,
            "platform_fee": o.platform_fee_amount,
            "helper_payout": o.helper_payout_amount,
            "razorpay_payout_id": o.razorpay_payout_id,
            "razorpay_payment_id": o.razorpay_payment_id,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        })
    return result
