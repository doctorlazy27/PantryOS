from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.roles import UserRole
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.models.registration_request import RegistrationRequest
from app.schemas.user import UserLogin, UserRegister
from app.auth.dependencies import get_current_user, require_permission
from app.models.auth_session import AuthSession
from app.models.warehouse import Warehouse


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.get("/me")
def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    return current_user


@router.get("/roles")
def get_roles():
    return {
        "roles": [role.value for role in UserRole]
    }

@router.get("/warehouses")
def get_signup_warehouses(db: Session = Depends(get_db)):
    return {"warehouses": db.query(Warehouse).order_by(Warehouse.name.asc()).all()}


@router.post("/register")
def register_user(
    user: UserRegister,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.username == user.username).first()
    existing_request = db.query(RegistrationRequest).filter(
        RegistrationRequest.username == user.username
    ).first()

    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == user.warehouse_id).first() if user.warehouse_id else None
    if warehouse is None and user.warehouse_name:
        warehouse = db.query(Warehouse).filter(Warehouse.name.ilike(user.warehouse_name.strip())).first()
    if warehouse is None:
        raise HTTPException(status_code=400, detail="Selected warehouse does not exist")

    if existing_user or (existing_request and existing_request.status == "pending"):
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    if existing_request and existing_request.status == "rejected":
        existing_request.full_name = user.full_name
        existing_request.role = user.role.value
        existing_request.warehouse_id = warehouse.warehouse_id
        existing_request.password_hash = hash_password(user.password)
        existing_request.status = "pending"
        existing_request.requested_at = datetime.utcnow()
        existing_request.reviewed_at = None
        existing_request.reviewed_by = None
        db.commit()
        db.refresh(existing_request)
        return {
            "message": "Registration request submitted for manager approval",
            "request_id": existing_request.request_id,
            "username": existing_request.username,
            "full_name": existing_request.full_name,
            "role": existing_request.role,
            "status": existing_request.status
        }

    request = RegistrationRequest(
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
            warehouse_id=warehouse.warehouse_id,
        password_hash=hash_password(user.password),
        status="pending"
    )

    db.add(request)
    db.commit()
    db.refresh(request)

    return {
        "message": "Registration request submitted for manager approval",
        "request_id": request.request_id,
        "username": request.username,
        "full_name": request.full_name,
        "role": request.role,
            "warehouse_id": request.warehouse_id,
        "status": request.status
    }


@router.get("/registration-requests")
def get_registration_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    requests = db.query(RegistrationRequest).filter(
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(RegistrationRequest.requested_at.asc()).all()

    return {
        "requests": [
            {
                "request_id": request.request_id,
                "username": request.username,
                "full_name": request.full_name,
                "role": request.role,
                "warehouse_id": request.warehouse_id,
                "status": request.status,
                "requested_at": request.requested_at,
            }
            for request in requests
        ]
    }


@router.patch("/registration-requests/{request_id}/approve")
def approve_registration_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    request = db.query(RegistrationRequest).filter(
        RegistrationRequest.request_id == request_id,
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if request is None:
        raise HTTPException(status_code=404, detail="Pending registration request not found")

    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=request.username,
        full_name=request.full_name,
        role=request.role,
        password_hash=request.password_hash,
        warehouse_id=request.warehouse_id,
    )
    db.add(user)
    request.status = "approved"
    request.reviewed_at = datetime.utcnow()
    request.reviewed_by = current_user["user_id"]
    db.commit()

    return {
        "message": "Registration approved",
        "request_id": request.request_id,
        "username": user.username,
        "role": user.role,
            "warehouse_id": user.warehouse_id,
        "status": request.status,
    }


@router.patch("/registration-requests/{request_id}/reject")
def reject_registration_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users"))
):
    request = db.query(RegistrationRequest).filter(
        RegistrationRequest.request_id == request_id,
        RegistrationRequest.status == "pending",
        RegistrationRequest.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if request is None:
        raise HTTPException(status_code=404, detail="Pending registration request not found")

    request.status = "rejected"
    request.reviewed_at = datetime.utcnow()
    request.reviewed_by = current_user["user_id"]
    db.commit()

    return {
        "message": "Registration rejected",
        "request_id": request.request_id,
        "username": request.username,
        "status": request.status,
    }


@router.post("/login")
def login_user(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.username == user.username
    ).first()

    if not existing_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(
        user.password,
        existing_user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    session_id = str(uuid4())
    db.add(AuthSession(session_id=session_id, user_id=existing_user.user_id))

    access_token = create_access_token(
        user_id=existing_user.user_id,
        username=existing_user.username,
        role=existing_user.role,
        session_id=session_id,
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }