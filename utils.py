from sqlalchemy.orm import Session
from datetime import datetime
import models

def parse_datetime(dt_str: str) -> datetime:
    if not dt_str:
        return datetime.utcnow()
    try:
        # Handle common ISO formats
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except Exception:
        return datetime.utcnow()

def log_admin_action(db: Session, user_id: int, action: str, details: str = None):
    try:
        log = models.ActivityLog(user_id=user_id, action=action, details=details)
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"Error logging admin action: {e}")
        db.rollback()
