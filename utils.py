from datetime import datetime


def parse_datetime(dt_str: str) -> datetime:
    if not dt_str:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except Exception:
        return datetime.utcnow()


async def log_admin_action(user_id, action: str, details: str = None):
    try:
        import models
        log = models.ActivityLog(user_id=user_id, action=action, details=details)
        await log.insert()
    except Exception as e:
        print(f"Error logging admin action: {e}")
