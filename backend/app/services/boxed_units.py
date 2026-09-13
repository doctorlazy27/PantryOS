from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.boxed_unit import BoxedUnit


def create_boxed_units(
    db: Session,
    inventory_id: int,
    box_count: int,
    units_per_box: int,
    unit_cost: float,
    scanned_codes: list[str] | None = None,
) -> None:
    codes = scanned_codes or []
    for index in range(box_count):
        db.add(BoxedUnit(
            inventory_id=inventory_id,
            box_code=str(uuid4()),
            scanned_code=codes[index] if index < len(codes) else None,
            units=units_per_box,
            unit_cost=unit_cost,
        ))