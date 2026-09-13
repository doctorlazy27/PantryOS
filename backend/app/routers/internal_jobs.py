import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

from app.database import SessionLocal
from app.services.expiry import process_expiry
from app.services.intelligence import process_inventory_intelligence

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/jobs", tags=["Internal jobs"])


def require_job_secret(value: str | None) -> None:
    expected = os.getenv("INTERNAL_JOB_SECRET")
    if not expected or not value or not secrets.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="Invalid internal job credentials")


@router.post("/process-expiry")
def process_expiry_job(x_internal_job_secret: str | None = Header(default=None)):
    require_job_secret(x_internal_job_secret)
    started_at = datetime.utcnow()
    logger.info("Starting scheduled expiry job")
    db = SessionLocal()
    try:
        result = process_expiry(db)
        logger.info("Completed scheduled expiry job: %s", result)
        return {"status": "ok", "job": "process-expiry", "started_at": started_at, "result": result}
    except Exception:
        db.rollback()
        logger.exception("Scheduled expiry job failed")
        raise HTTPException(status_code=500, detail="Expiry job failed")
    finally:
        db.close()


@router.post("/process-inventory-intelligence")
def process_inventory_intelligence_job(x_internal_job_secret: str | None = Header(default=None)):
    require_job_secret(x_internal_job_secret)
    started_at = datetime.utcnow()
    logger.info("Starting scheduled inventory intelligence job")
    db = SessionLocal()
    try:
        result = process_inventory_intelligence(db)
        logger.info("Completed scheduled inventory intelligence job: %s", result)
        return {"status": "ok", "job": "process-inventory-intelligence", "started_at": started_at, "result": result}
    except Exception:
        db.rollback()
        logger.exception("Scheduled inventory intelligence job failed")
        raise HTTPException(status_code=500, detail="Inventory intelligence job failed")
    finally:
        db.close()
