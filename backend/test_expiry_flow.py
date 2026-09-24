import datetime
import sys

if "pytest" in sys.modules:
    import pytest
    pytest.skip("Manual destructive database script; run explicitly only against a disposable database.", allow_module_level=True)

from sqlalchemy import create_engine
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.user import User
from app.models.notification import Notification
from app.models.inventory_movement import InventoryMovement
from app.services.expiry import process_expiry

engine = create_engine('postgresql+psycopg://postgres:2JI23CS123@localhost:5432/warehouse_db')
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# Cleanup
db.execute(sqlalchemy.text("TRUNCATE TABLE inventory_movements, notifications, inventory, batches, warehouses, products, users CASCADE;"))
db.commit()

# Seed User
user = User(username='testuser', full_name='Test User', password_hash='foo', role='manager')
db.add(user)
db.commit()
db.refresh(user)

# Seed Product
product = Product(name='Test Product', category='Test', quantity=0, unit='kg', price=10.0)
db.add(product)
db.commit()
db.refresh(product)

# Seed Warehouse
warehouse = Warehouse(name='Test Warehouse', location='Test Loc')
db.add(warehouse)
db.commit()
db.refresh(warehouse)

# Seed Batch 1 (Active)
batch_active = Batch(product_id=product.product_id, batch_number='B_ACTIVE', manufacturing_date=datetime.date.today() - datetime.timedelta(days=10), expiry_date=datetime.date.today() + datetime.timedelta(days=10), status='active')
db.add(batch_active)
# Seed Batch 2 (Expired)
batch_expired = Batch(product_id=product.product_id, batch_number='B_EXPIRED', manufacturing_date=datetime.date.today() - datetime.timedelta(days=20), expiry_date=datetime.date.today() - datetime.timedelta(days=5), status='active')
db.add(batch_expired)
db.commit()
db.refresh(batch_active)
db.refresh(batch_expired)

# Seed Inventory
inv_active = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch_active.batch_id, quantity=100)
db.add(inv_active)
inv_expired = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, batch_id=batch_expired.batch_id, quantity=50)
db.add(inv_expired)
db.commit()

print(f"Before expiry job:")
print(f"  Active Inv qty: {inv_active.quantity}, exp_qty: {inv_active.expired_quantity}")
print(f"  Expired Inv qty: {inv_expired.quantity}, exp_qty: {inv_expired.expired_quantity}")
print(f"  Expired Batch status: {batch_expired.status}")

# Run process_expiry
process_expiry(db)

# Check state
db.refresh(inv_active)
db.refresh(inv_expired)
db.refresh(batch_expired)

print(f"\nAfter first expiry job:")
print(f"  Active Inv qty: {inv_active.quantity}, exp_qty: {inv_active.expired_quantity}")
print(f"  Expired Inv qty: {inv_expired.quantity}, exp_qty: {inv_expired.expired_quantity}")
print(f"  Expired Batch status: {batch_expired.status}")

# Check movements and notifications
movements = db.query(InventoryMovement).filter_by(batch_id=batch_expired.batch_id).all()
print(f"  Movements for expired batch: {len(movements)}")
for m in movements:
    print(f"    - Type: {m.movement_type}, Qty: {m.quantity}, Reason: {m.reason}")

notifications = db.query(Notification).filter_by(user_id=user.user_id).all()
print(f"  Notifications: {len(notifications)}")

# Run process_expiry again to test idempotency
process_expiry(db)
db.refresh(inv_expired)
movements2 = db.query(InventoryMovement).filter_by(batch_id=batch_expired.batch_id).all()
notifications2 = db.query(Notification).filter_by(user_id=user.user_id).all()

print(f"\nAfter second expiry job (idempotency check):")
print(f"  Expired Inv qty: {inv_expired.quantity}, exp_qty: {inv_expired.expired_quantity}")
print(f"  Movements for expired batch: {len(movements2)}")
print(f"  Notifications: {len(notifications2)}")
