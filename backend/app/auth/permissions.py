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
        "view_inventory_recommendations",
        "review_inventory_recommendations",
        "create_purchase_orders",
        "view_counter_inventory",
        "view_counter_sales",
        "request_counter_allocation",
        "approve_counter_allocation",
        "checkout_counter",
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
    "checkout_counter",
},

}


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())