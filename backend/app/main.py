import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.routers.products import router as products_router
from sqlalchemy import text
from app.database import engine
from app.database import Base, engine
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.routers.warehouses import router as warehouses_router
from app.models.inventory import Inventory
from app.routers.inventory import router as inventory_router
from app.models.batch import Batch
from app.routers.batches import router as batches_router
from app.models.user import User
from app.routers.users import router as users_router
from app.models.customer import Customer
from app.routers.customers import router as customers_router
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.routers.orders import router as orders_router
from app.models.supplier import Supplier
from app.routers.suppliers import router as suppliers_router
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.routers.purchase_orders import router as purchase_orders_router
from app.models.activity_log import ActivityLog
from app.routers.activity import router as activity_router
from app.models.notification import Notification
from app.models.message import Message
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.models.warehouse_request import WarehouseRequest
from app.models.salesperson_inventory import SalespersonInventory
from app.routers.notifications import router as notifications_router
from app.models.invoice import Invoice
from app.models.auth_session import AuthSession
from app.routers.invoices import router as invoices_router
if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)
from app.routers.dashboard import router as dashboard_router


def ensure_warehouse_assignment_columns():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)"))
        connection.execute(text("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)"))
        connection.execute(text("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)"))
        connection.execute(text("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(warehouse_id)"))
        connection.execute(text("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS confirmed_by INTEGER REFERENCES users(user_id)"))
        connection.execute(text("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS warehouse_requests (request_id SERIAL PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL, warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id), requested_by INTEGER NOT NULL REFERENCES users(user_id), approved_by INTEGER REFERENCES users(user_id), status VARCHAR(30) NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL DEFAULT NOW(), approved_at TIMESTAMP)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS salesperson_inventory (inventory_id SERIAL PRIMARY KEY, salesperson_id INTEGER NOT NULL REFERENCES users(user_id), product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL DEFAULT 0)"))
        connection.execute(text("UPDATE users SET warehouse_id = (SELECT MIN(warehouse_id) FROM warehouses) WHERE warehouse_id IS NULL AND (SELECT COUNT(*) FROM warehouses) = 1"))
        connection.execute(text("UPDATE registration_requests SET warehouse_id = (SELECT MIN(warehouse_id) FROM warehouses) WHERE warehouse_id IS NULL AND (SELECT COUNT(*) FROM warehouses) = 1"))
        connection.execute(text("UPDATE sales_orders SET warehouse_id = (SELECT warehouse_id FROM users WHERE users.user_id = sales_orders.created_by) WHERE warehouse_id IS NULL"))
        connection.execute(text("UPDATE purchase_orders SET warehouse_id = (SELECT warehouse_id FROM users WHERE users.user_id = purchase_orders.created_by) WHERE warehouse_id IS NULL"))


ensure_warehouse_assignment_columns()

app = FastAPI(
    title="Food Warehouse Management System",
    description="Backend API for managing food warehouse operations.",
    version="1.0.0",
)

cors_origins = os.getenv("CORS_ORIGINS") or (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8081,http://127.0.0.1:8081"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(products_router)
app.include_router(warehouses_router)
app.include_router(inventory_router)
app.include_router(batches_router)
app.include_router(users_router)
app.include_router(customers_router)
app.include_router(orders_router)
app.include_router(suppliers_router)
app.include_router(purchase_orders_router)
app.include_router(activity_router)
app.include_router(notifications_router)
app.include_router(invoices_router)
app.include_router(dashboard_router)

@app.get("/")
def root():
    return {
        "message": "Food Warehouse Management System API is running"
    }


@app.get("/health")
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unavailable"},
        )

    return {"status": "healthy", "database": "connected"}

@app.get("/database-test", include_in_schema=False)
def database_test():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "result": result.scalar()
        }