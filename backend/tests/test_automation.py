import os
from datetime import date, timedelta
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-router-registration-secret")

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.auth.dependencies import get_current_user
from app.auth.permissions import has_permission
from app.auth.roles import UserRole
from app.auth.security import create_access_token
from app.auth.router import get_roles
from app.models.auth_session import AuthSession
from app.models.activity_log import ActivityLog
from app.models.batch import Batch
from app.models.boxed_unit import BoxedUnit
from app.models.customer import Customer
from app.models.counter_inventory import CounterInventory
from app.models.counter_sale import CounterSale
from app.models.inventory import Inventory
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.notification import Notification
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.invoice import Invoice
from app.models.product import Product
from app.models.stock_transfer import StockTransfer
from app.models.user import User
from app.models.warehouse import Warehouse
import app.main as main_module
from app.main import app
from app.routers import internal_jobs
from app.routers.internal_jobs import process_expiry_job, require_job_secret
from app.services.inventory_guard import require_available_batch
from app.services.expiry import process_expiry
import app.services.ai_assistant as ai_assistant
import app.services.intelligence as intelligence_module
import app.routers.counter as counter_module
import app.routers.invoices as invoice_module
from app.services.ai_assistant import suggest_inventory_actions
from app.services.intelligence import process_inventory_intelligence
from app.services.invoice_reports import build_invoice_report, period_window
from app.services import ai_provider
from app.routers.orders import _fefo_plan, approve_order, confirm_order_receipt, create_order, fulfill_order
from app.routers.invoices import confirm_invoice, generate_invoice, get_invoice, get_invoices, send_invoice, summarize_invoice_period
from app.routers.inventory import approve_inventory_addition, request_inventory_addition
from app.routers.counter import checkout
from app.routers.counter import warehouse_copilot
from app.routers.stock_transfers import list_stock_transfers
from app.schemas.counter import CheckoutCreate, CheckoutItem
from app.schemas.inventory_addition_approval import InventoryAdditionApproval
from app.schemas.inventory_addition_request import InventoryAdditionRequestCreate
from app.schemas.order import OrderItemCreate, SalesOrderCreate


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


def test_core_workflow_routers_are_registered():
    paths = set(app.openapi()["paths"])
    assert {"/customers/", "/orders/", "/invoices/", "/stock-transfers/"} <= paths


def test_invoice_report_periods_use_calendar_windows():
    current_day = date(2026, 9, 27)
    assert period_window("weekly", current_day) == (date(2026, 9, 21), date(2026, 9, 28), date(2026, 9, 14), date(2026, 9, 21))
    assert period_window("monthly", current_day) == (date(2026, 9, 1), date(2026, 10, 1), date(2026, 8, 1), date(2026, 9, 1))
    assert period_window("yearly", current_day) == (date(2026, 1, 1), date(2027, 1, 1), date(2025, 1, 1), date(2026, 1, 1))


def test_ai_provider_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert ai_provider.complete("system", "user") is None


def test_ai_provider_uses_backend_configuration(monkeypatch):
    monkeypatch.setenv("AI_API_URL", "https://model.example/v1/chat/completions")
    monkeypatch.setenv("AI_API_KEY", "test-only-key")
    monkeypatch.setenv("AI_MODEL", "free-test-model")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "grounded summary"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(ai_provider.httpx, "post", fake_post)

    result = ai_provider.complete("system rule", "warehouse data")

    assert result == "grounded summary"
    assert captured["url"] == "https://model.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-only-key"
    assert captured["json"]["model"] == "free-test-model"


def test_manager_has_sales_workflow_and_signup_hides_legacy_role():
    assert has_permission(UserRole.MANAGER, "create_orders")
    assert has_permission(UserRole.MANAGER, "confirm_order_receipt")
    assert has_permission(UserRole.MANAGER, "send_invoices")
    assert has_permission(UserRole.MANAGER, "confirm_invoices")
    assert has_permission(UserRole.MANAGER, "request_stock_transfer")
    assert has_permission(UserRole.MANAGER, "approve_sales_orders")
    assert has_permission(UserRole.MANAGER, "view_invoices")
    assert set(get_roles()["roles"]) == {UserRole.MANAGER.value, UserRole.WAREHOUSE_WORKER.value}
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "approve_sales_orders")
    assert not has_permission(UserRole.WAREHOUSE_WORKER, "view_invoices")
    assert all(has_permission(role, "view_ai_copilot") for role in UserRole)


def test_ai_copilot_uses_warehouse_fallback_without_provider(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
    warehouse = Warehouse(name="Copilot warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    actor = {"user_id": 1, "username": "Worker", "role": "warehouse_worker", "warehouse_id": warehouse.warehouse_id}

    result = warehouse_copilot("What needs attention?", db, actor)

    assert result["ai_powered"] is False
    assert "0 counter replenishment" in result["answer"]
    assert result["priorities"] == ["No urgent counter or expiry risks are currently reported."]


def test_ai_copilot_uses_provider_answer_when_available(db, monkeypatch):
    warehouse = Warehouse(name="Model copilot warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    monkeypatch.setattr(counter_module, "process_expiry", lambda _db: None)
    monkeypatch.setattr(counter_module, "answer_warehouse_question", lambda question, _context: f"Grounded answer: {question}")
    actor = {"user_id": 1, "username": "Manager", "role": "manager", "warehouse_id": warehouse.warehouse_id}

    result = warehouse_copilot("What should I check?", db, actor)

    assert result["ai_powered"] is True
    assert result["answer"] == "Grounded answer: What should I check?"


def test_invoice_report_summary_uses_model_when_available(db, monkeypatch):
    warehouse = Warehouse(name="Report warehouse", location="Test")
    db.add(warehouse)
    db.commit()
    monkeypatch.setattr(invoice_module, "summarize_invoice_report", lambda _report: "Two invoices are awaiting review.")
    actor = {"user_id": 1, "username": "Manager", "role": "manager", "warehouse_id": warehouse.warehouse_id}

    result = summarize_invoice_period("monthly", db, actor)

    assert result == {"summary": "Two invoices are awaiting review.", "ai_powered": True}


def test_sales_order_completes_role_handoff_loop(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
    warehouse = Warehouse(name="Workflow warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    manager = User(username="workflow-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    worker = User(username="workflow-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    product = Product(name="Workflow rice", category="Dry goods", quantity=0, unit="kg", price=2, units_per_box=1)
    customer = Customer(name="Workflow buyer", phone="000")
    db.add_all([manager, worker, product, customer])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="FLOW-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=20))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=12)
    db.add(inventory)
    db.commit()

    def actor(user):
        return {"user_id": user.user_id, "username": user.full_name, "role": user.role, "warehouse_id": warehouse.warehouse_id}

    request = SalesOrderCreate(customer_id=customer.customer_id, items=[OrderItemCreate(product_id=product.product_id, quantity=5)])
    created = create_order(request, db, actor(manager))
    approved = approve_order(created["order_id"], db, actor(manager))
    fulfilled = fulfill_order(created["order_id"], db, actor(worker))
    with pytest.raises(HTTPException) as repeated_fulfillment:
        fulfill_order(created["order_id"], db, actor(worker))
    confirmed = confirm_order_receipt(created["order_id"], db, actor(manager))
    generated_invoice = generate_invoice(created["order_id"], db, actor(manager))
    sent_invoice = send_invoice(generated_invoice["invoice_id"], db, actor(manager))
    final_invoice = confirm_invoice(generated_invoice["invoice_id"], db, actor(manager))

    other_salesperson = User(username="other-workflow-sales", full_name="Other sales", role="salesperson", password_hash="x", warehouse_id=warehouse.warehouse_id)
    other_customer = Customer(name="Other buyer", phone="111")
    db.add_all([other_salesperson, other_customer])
    db.flush()
    other_order = SalesOrder(customer_id=other_customer.customer_id, created_by=other_salesperson.user_id, warehouse_id=warehouse.warehouse_id, status="confirmed")
    db.add(other_order)
    db.flush()
    db.add(SalesOrderItem(order_id=other_order.order_id, product_id=product.product_id, quantity=1, unit_price=product.price))
    other_invoice = Invoice(order_id=other_order.order_id, customer_id=other_customer.customer_id, generated_by=other_salesperson.username, total_amount=product.price, status="generated")
    db.add(other_invoice)
    db.commit()
    manager_invoices = get_invoices(db, actor(manager))["invoices"]
    manager_report = build_invoice_report(db, "weekly", actor(manager))
    local_summary = summarize_invoice_period("weekly", db, actor(manager))

    assert created["status"] == "pending"
    assert approved["status"] == "approved"
    assert fulfilled["status"] == "fulfilled"
    assert repeated_fulfillment.value.status_code == 400
    assert confirmed["status"] == "confirmed"
    assert generated_invoice["status"] == "generated"
    assert sent_invoice["status"] == "sent"
    assert final_invoice["status"] == "confirmed"
    assert len(manager_invoices) == 2
    assert manager_report["invoice_count"] == 2
    assert local_summary["ai_powered"] is False
    assert inventory.quantity == 7
    assert db.query(InventoryMovement).filter(InventoryMovement.movement_type == "SOLD").count() == 1
    assert db.query(Invoice).filter(Invoice.order_id == created["order_id"]).count() == 1


def test_worker_inventory_request_approval_has_consistent_audit(db):
    warehouse = Warehouse(name="Receiving warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    worker = User(username="receiving-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    manager = User(username="receiving-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    db.add_all([worker, manager])
    db.commit()

    def actor(user):
        return {"user_id": user.user_id, "username": user.full_name, "role": user.role, "warehouse_id": warehouse.warehouse_id}

    request = InventoryAdditionRequestCreate(product_name="Beans", quantity=12, category="Canned", unit_price=2)
    created = request_inventory_addition(request, db, actor(worker))
    approval = InventoryAdditionApproval(
        batch_number="BEANS-1",
        manufacturing_date=date.today() - timedelta(days=1),
        expiry_date=date.today() + timedelta(days=100),
        aisle="A1",
        shelf_number="S1",
    )
    result = approve_inventory_addition(created["request_id"], approval, db, actor(manager))
    addition = db.query(InventoryAdditionRequest).filter_by(request_id=created["request_id"]).one()
    inventory = db.query(Inventory).filter_by(warehouse_id=warehouse.warehouse_id).one()
    actions = {entry.action for entry in db.query(ActivityLog).all()}

    assert result["status"] == "approved"
    assert addition.status == "approved"
    assert inventory.quantity == 12
    assert "INVENTORY_REQUEST_APPROVED" in actions
    assert "INVENTORY_REQUEST_REJECTED" not in actions


def test_counter_checkout_rejects_multiple_lines_that_overdraw_same_stock(db):
    warehouse = Warehouse(name="Counter warehouse", location="Test")
    worker = User(username="counter-worker", full_name="Worker", role="warehouse_worker", password_hash="x")
    product = Product(name="Counter product", category="General", quantity=0, unit="units", price=3, units_per_box=1)
    db.add_all([warehouse, worker, product])
    db.flush()
    worker.warehouse_id = warehouse.warehouse_id
    batch = Batch(product_id=product.product_id, batch_number="COUNTER-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    inventory = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=10)
    db.add(inventory)
    db.flush()
    counter = CounterInventory(warehouse_id=warehouse.warehouse_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=5, minimum_level=1, unit_price=product.price)
    db.add_all([
        counter,
        BoxedUnit(inventory_id=inventory.inventory_id, scanned_code="COUNTER-A", units=5, remaining_units=5, unit_cost=product.price),
        BoxedUnit(inventory_id=inventory.inventory_id, scanned_code="COUNTER-B", units=5, remaining_units=5, unit_cost=product.price),
    ])
    db.commit()

    request = CheckoutCreate(items=[
        CheckoutItem(scanned_code="COUNTER-A", quantity=3),
        CheckoutItem(scanned_code="COUNTER-B", quantity=3),
    ])
    actor = {"user_id": worker.user_id, "username": worker.full_name, "role": worker.role, "warehouse_id": warehouse.warehouse_id}
    with pytest.raises(HTTPException) as error:
        checkout(request, db, actor)

    assert error.value.status_code == 400
    assert counter.quantity == 5
    assert db.query(CounterSale).count() == 0


def test_transfer_queue_is_scoped_to_manager_warehouse_and_salesperson_requests(db):
    source = Warehouse(name="Source", location="Test")
    destination = Warehouse(name="Destination", location="Test")
    unrelated = Warehouse(name="Unrelated", location="Test")
    db.add_all([source, destination, unrelated])
    db.flush()
    manager = User(username="transfer-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=source.warehouse_id)
    salesperson = User(username="transfer-sales", full_name="Sales", role="salesperson", password_hash="x", warehouse_id=source.warehouse_id)
    other_salesperson = User(username="other-transfer-sales", full_name="Other sales", role="salesperson", password_hash="x", warehouse_id=unrelated.warehouse_id)
    product = Product(name="Transfer product", category="General", quantity=0, unit="units", price=1, units_per_box=1)
    db.add_all([manager, salesperson, other_salesperson, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="TRANSFER-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=10))
    db.add(batch)
    db.flush()
    owned_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=source.warehouse_id, destination_warehouse_id=destination.warehouse_id, quantity=2, created_by=salesperson.user_id)
    incoming_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=unrelated.warehouse_id, destination_warehouse_id=source.warehouse_id, quantity=1, created_by=other_salesperson.user_id)
    unrelated_request = StockTransfer(product_id=product.product_id, batch_id=batch.batch_id, source_warehouse_id=destination.warehouse_id, destination_warehouse_id=unrelated.warehouse_id, quantity=1, created_by=other_salesperson.user_id)
    db.add_all([owned_request, incoming_request, unrelated_request])
    db.commit()

    manager_rows = list_stock_transfers(db, {"user_id": manager.user_id, "role": "manager", "warehouse_id": source.warehouse_id})["transfers"]
    salesperson_rows = list_stock_transfers(db, {"user_id": salesperson.user_id, "role": "salesperson", "warehouse_id": source.warehouse_id})["transfers"]

    assert {row["transfer_id"] for row in manager_rows} == {owned_request.transfer_id, incoming_request.transfer_id}
    assert [row["transfer_id"] for row in salesperson_rows] == [owned_request.transfer_id]


def test_local_expiry_job_contains_database_failures(monkeypatch):
    class FakeSession:
        rolled_back = False
        closed = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()

    def fail_processing(_db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(main_module, "process_expiry", fail_processing)

    main_module.run_expiry_job()

    assert session.rolled_back
    assert session.closed


def test_local_inventory_job_contains_database_failures(monkeypatch):
    class FakeSession:
        rolled_back = False
        closed = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()

    def fail_processing(_db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(main_module, "process_inventory_intelligence", fail_processing)

    main_module.run_inventory_intelligence_job()

    assert session.rolled_back
    assert session.closed


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


def test_intelligence_creates_actionable_recommendations(db, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("AI_MODEL", "")
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


def test_ai_inventory_suggestions_reject_unknown_and_ineligible_products(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: '{"suggestions":['
        '{"product_id":1,"action":"ORDER_REVIEW","priority":"HIGH"},'
        '{"product_id":2,"action":"ORDER_REVIEW","priority":"HIGH"},'
        '{"product_id":999,"action":"INVENTORY_CHECK","priority":"HIGH"}]}')
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
        {"product_id": 2, "product_name": "Beans", "current_stock": 50, "recommended_reorder": 0, "stockout_risk": "LOW", "waste_risk": "LOW", "estimated_days_remaining": None},
    ])
    assert suggestions == [{"product_id": 1, "action": "ORDER_REVIEW", "priority": "HIGH"}]


def test_ai_inventory_suggestions_parse_json_embedded_in_provider_text(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: (
        'Here are the suggestions:\n```json\n'
        '{"suggestions":[{"product_id":1,"action":"ORDER_REVIEW","priority":"HIGH"}]}\n'
        '```'
    ))
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
    ])
    assert suggestions == [{"product_id": 1, "action": "ORDER_REVIEW", "priority": "HIGH"}]


def test_ai_inventory_suggestions_ignore_invalid_provider_json(monkeypatch):
    monkeypatch.setattr(ai_assistant, "complete", lambda *_args, **_kwargs: "not JSON")
    suggestions = suggest_inventory_actions([
        {"product_id": 1, "product_name": "Rice", "current_stock": 2, "recommended_reorder": 8, "stockout_risk": "HIGH", "waste_risk": "LOW", "estimated_days_remaining": 2},
    ])
    assert suggestions == []


def test_ai_inventory_notifications_are_deduplicated_and_role_scoped(db, monkeypatch):
    warehouse = Warehouse(name="AI warehouse", location="Test")
    db.add(warehouse)
    db.flush()
    manager = User(username="ai-manager", full_name="Manager", role="manager", password_hash="x", warehouse_id=warehouse.warehouse_id)
    worker = User(username="ai-worker", full_name="Worker", role="warehouse_worker", password_hash="x", warehouse_id=warehouse.warehouse_id)
    product = Product(name="AI rice", category="Dry goods", quantity=0, unit="kg", price=2, units_per_box=1, reorder_level=10)
    db.add_all([manager, worker, product])
    db.flush()
    batch = Batch(product_id=product.product_id, batch_number="AI-1", manufacturing_date=date.today(), expiry_date=date.today() + timedelta(days=30))
    db.add(batch)
    db.flush()
    db.add(Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch.batch_id, quantity=2))
    db.commit()
    suggestion = {"product_id": product.product_id, "action": "ORDER_REVIEW", "priority": "HIGH"}
    monkeypatch.setattr(intelligence_module, "suggest_inventory_actions", lambda _results: [suggestion])

    process_inventory_intelligence(db)
    process_inventory_intelligence(db)

    notifications = db.query(Notification).filter(Notification.notification_type == "ai_inventory_suggestion").all()
    assert len(notifications) == 1
    assert notifications[0].user_id == manager.user_id


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
