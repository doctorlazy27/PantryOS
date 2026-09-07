from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog


def log_activity(
    db: Session,
    user_id: int | None,
    username: str,
    action: str,
    description: str,
):
    activity = ActivityLog(
        user_id=user_id,
        username=username,
        action=action,
        description=description,
    )

    db.add(activity)