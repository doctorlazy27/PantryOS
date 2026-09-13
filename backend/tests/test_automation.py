import os
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.notification import Notification
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.product import Product
from app.models.user import User
from app.models.warehouse import Warehouse
from app.routers import internal_jobs
from app.routers.internal_jobs import process_expiry_job, require_job_secret
from app.services.inventory_guard import require_available_batch
from app.services.expiry import process_expiry
from app.services.intelligence import process_inventory_intelligence
from app.routers.orders import _fefo_plan


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def seed_expiring_inventory(db):
    warehouse = Warehouse(name="Test warehouse", location="Test")
    worker = User(username="worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=1)
    manager = User(username="manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=1)
    product = Product(name="Milk", category="Dairy", quantity=0, unit="units", price=2, units_per_box=1)
    db.add(warehouse)
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    manager.warehouse_id = warehouse.warehouse_id
    db.add_all([worker, manager, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="EXPIRED-1", manufacturing_date=date.today() - timedelta(days=8), expiry_date=date.today() - timedelta(days=1))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=100)
    db.add(inventory)
    db.commit()
    return warehouse, product, batch, inventory


def test_expiry_is_idempotent_and_deduplicates_notifications(db):
    _, _, batch, inventory = seed_expiring_inventory(db)
    first = process_expiry(db, date.today())
    second = process_expiry(db, date.today())
    db.refresh(inventory)
    db.refresh(batch)
    assert first["expired_units"] == 100
    assert second["expired_units"] == 0
    assert inventory.quantity == 0
    assert inventory.expired_quantity == 100
    assert batch.status == "expired"
    assert db.query(InventoryMovement).filter(InventoryMovement.movement_type == "EXPIRED").count() == 1
    assert db.query(Notification).count() == 2


def test_active_batch_is_untouched_and_warning_is_created(db):
    warehouse = Warehouse(name="Warning warehouse", location="Test")
    worker = User(username="warning-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    product = Product(name="Yogurt", category="Dairy", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([warehouse, worker, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="WARN-7", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=7))
    active_batch = Batch(product_id=product.product_id, batch_number="ACTIVE-8", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=8))
    db.add_all([batch, active_batch])
    db.flush()
    active_inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=active_batch.batch_id, quantity=20)
    warning_inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=30)
    db.add_all([active_inventory, warning_inventory])
    db.commit()
    result = process_expiry(db, date.today())
    db.refresh(active_inventory)
    assert active_inventory.quantity == 20
    assert result["expired_units"] == 0
    assert db.query(Notification).filter(Notification.notification_type == "inventory_expiry_warning").count() == 1


def test_intelligence_creates_actionable_recommendations(db):
    warehouse, product, batch, inventory = seed_expiring_inventory(db)
    inventory.quantity = 10
    batch.expiry_date = date.today() + timedelta(days=1)
    customer = Customer(name="Test customer", phone="000")
    db.add(customer)
    db.flush()
    order = SalesOrder(customer_id=customer.customer_id, created_by=1, warehouse_id=warehouse.warehouse_id, status="confirmed")
    db.add(order)
    db.flush()
    db.add(SalesOrderItem(order_id=order.order_id, product_id=product.product_id, quantity=150, unit_price=product.price))
    db.commit()
    result = process_inventory_intelligence(db)
    assert isinstance(result["evaluated"], int)
    assert result["notifications"] > 0
    assert db.query(InventoryRecommendation).count() == 1
    notification_count = db.query(Notification).count()
    process_inventory_intelligence(db)
    assert db.query(Notification).count() == notification_count


def test_expired_batch_is_rejected_by_shared_inventory_guard(db):
    _, _, batch, _ = seed_expiring_inventory(db)
    with pytest.raises(HTTPException) as error:
        require_available_batch(db, batch.batch_id)
    assert error.value.status_code == 400


def test_fefo_plan_skips_expired_batches(db):
    warehouse, product, batch, _ = seed_expiring_inventory(db)
    assert _fefo_plan(db, product.product_id, warehouse.warehouse_id, 1) == []


def test_fefo_plan_allocates_across_valid_batches(db):
    warehouse = Warehouse(name="FEFO warehouse", location="Test")
    product = Product(name="Rice", category="Boxed items", quantity=0, unit="kg", price=2, units_per_box=1)
    db.add_all([warehouse, product])
    db.flush()
    first = Batch(product_id=product.product_id, batch_number="FEFO-A", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=2))
    second = Batch(product_id=product.product_id, batch_number="FEFO-B", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add_all([first, second])
    db.flush()
    db.add_all([Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=first.batch_id, quantity=100), Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=second.batch_id, quantity=300)])
    db.commit()
    plan = _fefo_plan(db, product.product_id, warehouse.warehouse_id, 120)
    assert [(item["batch_number"], item["quantity"]) for item in plan] == [("FEFO-A", 100), ("FEFO-B", 20)]


def test_internal_job_secret_rejects_unauthorized_requests(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    with pytest.raises(HTTPException) as error:
        require_job_secret("wrong-secret")
    assert error.value.status_code == 401


def test_internal_expiry_job_requires_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    with pytest.raises(HTTPException):
        process_expiry_job(None)


def test_internal_expiry_job_authorized_request_is_safe(monkeypatch, db):
    monkeypatch.setenv("INTERNAL_JOB_SECRET", "test-secret")
    monkeypatch.setattr(internal_jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(internal_jobs, "process_expiry", lambda _db: {"expired_batches": 0, "expired_units": 0, "warnings": 0})
    response = process_expiry_job("test-secret")
    assert response["status"] == "ok"
