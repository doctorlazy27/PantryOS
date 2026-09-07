from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


def allowed_recipient_roles(role: str) -> set[str]:
    if role == "warehouse_worker":
        return {"salesperson"}
    if role in {"salesperson", "manager"}:
        return {"manager", "warehouse_worker"} if role == "salesperson" else {"salesperson", "warehouse_worker"}
    return set()


@router.get("/contacts")
def get_message_contacts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    roles = allowed_recipient_roles(current_user["role"])
    contacts = db.query(User).filter(
        User.role.in_(roles),
        User.user_id != current_user["user_id"],
        User.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(User.full_name.asc()).all()
    return {
        "contacts": [
            {"user_id": user.user_id, "username": user.username, "full_name": user.full_name, "role": user.role}
            for user in contacts
        ]
    }


@router.get("/messages")
def get_my_messages(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    messages = db.query(Message, User).join(User, Message.sender_id == User.user_id).filter(
        Message.recipient_id == current_user["user_id"]
    ).order_by(Message.created_at.desc()).all()
    return {
        "messages": [
            {
                "message_id": message.message_id,
                "sender_id": message.sender_id,
                "sender_username": sender.username,
                "sender_role": sender.role,
                "subject": message.subject,
                "body": message.body,
                "is_read": message.is_read,
                "created_at": message.created_at,
                "reply_to_id": message.reply_to_id,
                "can_reply": current_user["role"] == "salesperson" and sender.role == "warehouse_worker",
            }
            for message, sender in messages
        ]
    }


@router.post("/messages")
def send_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if message.reply_to_id is not None:
        original = db.query(Message, User).join(User, Message.sender_id == User.user_id).filter(
            Message.message_id == message.reply_to_id,
            Message.recipient_id == current_user["user_id"],
        ).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Message to reply to was not found")
        original_message, original_sender = original
        if current_user["role"] != "salesperson" or original_sender.role != "warehouse_worker":
            raise HTTPException(status_code=403, detail="Only a salesperson can reply to a worker message")
        recipient_ids = [original_message.sender_id]
    elif message.broadcast:
        if current_user["role"] != "manager":
            raise HTTPException(status_code=403, detail="Only managers can send broadcast messages")
        recipient_ids = [user.user_id for user in db.query(User).filter(
            User.role.in_({"salesperson", "warehouse_worker"}),
            User.user_id != current_user["user_id"],
            User.warehouse_id == current_user.get("warehouse_id"),
        ).all()]
    else:
        recipient_ids = list(dict.fromkeys(message.recipient_ids))

    recipients = db.query(User).filter(User.user_id.in_(recipient_ids)).all() if recipient_ids else []
    if not recipients or len(recipients) != len(set(recipient_ids)):
        raise HTTPException(status_code=400, detail="Select at least one valid recipient")

    roles = allowed_recipient_roles(current_user["role"])
    if any(recipient.role not in roles for recipient in recipients):
        raise HTTPException(status_code=403, detail="You cannot message one or more selected recipients")
    if any(recipient.warehouse_id != current_user.get("warehouse_id") for recipient in recipients):
        raise HTTPException(status_code=403, detail="You can only message people in your warehouse")

    for recipient in recipients:
        db.add(Message(
            sender_id=current_user["user_id"],
            recipient_id=recipient.user_id,
            reply_to_id=message.reply_to_id,
            subject=message.subject,
            body=message.body,
        ))
    db.commit()
    return {"message": "Message sent", "recipient_count": len(recipients)}


@router.patch("/messages/{message_id}/read")
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    item = db.query(Message).filter(
        Message.message_id == message_id,
        Message.recipient_id == current_user["user_id"],
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Message not found")
    item.is_read = True
    db.commit()
    return {"message_id": message_id, "is_read": True}


@router.get("/")
def get_my_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["user_id"])
        .order_by(Notification.created_at.desc())
        .all()
    )

    return {
        "notifications": notifications
    }


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    notification = db.query(Notification).filter(
        Notification.notification_id == notification_id,
        Notification.user_id == current_user["user_id"],
    ).first()

    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()
    return {"notification_id": notification.notification_id, "is_read": True}