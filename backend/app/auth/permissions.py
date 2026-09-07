from app.auth.roles import UserRole


PERMISSIONS = {
    UserRole.MANAGER: {
        "view_customers",
        "view_suppliers",
        "view_warehouses",
        "view_orders",
        "view_inventory",
        "view_all_warehouses",
        "view_employees",
        "view_activity",
        "manage_users",
        "manage_warehouses",
        "send_messages",
        "approve_requests",
        "approve_orders",
        "approve_stock_transfers",
        "confirm_invoices",
        "approve_inventory_requests",
    },

    UserRole.WAREHOUSE_WORKER: {
    "view_customers",
    "view_suppliers",
    "view_warehouses",
    "view_orders",
    "approve_orders",
    "view_activity",
    "view_inventory",
    "update_inventory",
    "view_assigned_warehouse",
    "receive_stock",
    "pick_stock",
    "dispatch_stock",
    "process_stock_requests",
    "fulfill_orders",
    "receive_purchase_orders",
    "send_messages",
    "submit_inventory_requests",
},

    UserRole.SALESPERSON: {
        "view_suppliers",
        "view_warehouses",
        "view_orders",
        "view_activity",
        "view_inventory",
        "view_customers",
        "create_orders",
        "request_warehouse_stock",
        "request_stock",
        "view_own_orders",
        "view_order_status",
        "create_purchase_orders",
        "request_stock_transfer",
        "process_stock_transfer",
        "send_invoices",
        "send_messages",
        "confirm_order_receipt",
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())