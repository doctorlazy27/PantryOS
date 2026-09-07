from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
    )

    db.add(notification)

    return notification


def notify_roles(
    db: Session,
    roles: set[str],
    title: str,
    message: str,
    notification_type: str,
    warehouse_id: int | None = None,
):
    query = db.query(User).filter(User.role.in_(roles))
    if warehouse_id is not None:
        query = query.filter(User.warehouse_id == warehouse_id)
    users = query.all()
    for user in users:
        create_notification(
            db=db,
            user_id=user.user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )