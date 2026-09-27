from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.order import SalesOrder


def period_window(period: str, today: date | None = None) -> tuple[date, date, date, date]:
    current_date = today or datetime.utcnow().date()
    if period == "weekly":
        start = current_date - timedelta(days=current_date.weekday())
        end = start + timedelta(days=7)
        previous_start = start - timedelta(days=7)
    elif period == "monthly":
        start = date(current_date.year, current_date.month, 1)
        end = date(current_date.year + (current_date.month == 12), current_date.month % 12 + 1, 1)
        previous_end = start
        previous_start = date(previous_end.year - (previous_end.month == 1), previous_end.month - 1 or 12, 1)
    elif period == "yearly":
        start = date(current_date.year, 1, 1)
        end = date(current_date.year + 1, 1, 1)
        previous_start = date(current_date.year - 1, 1, 1)
    else:
        raise ValueError("period must be weekly, monthly, or yearly")
    return start, end, previous_start, start


def build_invoice_report(
    db: Session,
    period: str,
    current_user: dict[str, Any],
    today: date | None = None,
) -> dict[str, Any]:
    start, end, previous_start, previous_end = period_window(period, today)

    def aggregate(period_start: date, period_end: date) -> tuple[int, float, dict[str, dict[str, float | int]]]:
        start_at = datetime.combine(period_start, datetime.min.time())
        end_at = datetime.combine(period_end, datetime.min.time())
        query = db.query(
            Invoice.status,
            func.count(Invoice.invoice_id),
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
        ).join(
            SalesOrder, Invoice.order_id == SalesOrder.order_id
        ).filter(
            SalesOrder.warehouse_id == current_user.get("warehouse_id"),
            Invoice.created_at >= start_at,
            Invoice.created_at < end_at,
        )
        rows = query.group_by(Invoice.status).all()
        by_status = {
            status: {"count": count, "amount": round(float(amount), 2)}
            for status, count, amount in rows
        }
        count = sum(int(values["count"]) for values in by_status.values())
        amount = round(sum(float(values["amount"]) for values in by_status.values()), 2)
        return count, amount, by_status

    count, amount, by_status = aggregate(start, end)
    previous_count, previous_amount, _ = aggregate(previous_start, previous_end)
    change_percent = round((amount - previous_amount) / previous_amount * 100, 1) if previous_amount else None
    return {
        "period": period,
        "starts_on": start.isoformat(),
        "ends_on": (end - timedelta(days=1)).isoformat(),
        "invoice_count": count,
        "total_amount": amount,
        "by_status": by_status,
        "previous_period": {"invoice_count": previous_count, "total_amount": previous_amount},
        "change_percent": change_percent,
    }