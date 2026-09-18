export type Role = 'manager' | 'warehouse_worker' | 'salesperson'
export type AuthUser = { user_id: number; username: string; role: Role; warehouse_id: number | null }
export type RegistrationRequest = { request_id: number; username: string; full_name: string; role: Role; status: string; requested_at: string }

export type DashboardData = {
  total_products: number
  total_inventory_records: number
  pending_sales_orders: number
  approved_sales_orders: number
  pending_purchase_orders: number
  unread_notifications: number
  low_stock_products: Array<{
    product_id: number
    name: string
    current_quantity: number
    reorder_level: number
    unit: string
  }>
  expiring_batches: Array<{
    product_name: string
    batch_number: string
    quantity: number
    expiry_date: string
  }>
  inventory_intelligence: Array<{
    product_id: number
    product_name: string
    current_stock: number
    average_daily_demand: number
    estimated_days_remaining: number | null
    stockout_risk: string
    waste_risk: string
    potential_surplus: number
    recommended_reorder: number
    recommendation: string
  }>
}

export type Product = { product_id: number; name: string; category: string; quantity: number; unit: string; price: number; reorder_level: number; units_per_box: number }
export type InventoryRecord = { inventory_id: number; product_id: number; warehouse_id: number; batch_id: number; quantity: number; boxed_units: number; units_per_box: number; unit_price: number; box_unit_cost: number; total_box_cost: number; boxed_unit_ids: string[] }
export type Warehouse = { warehouse_id: number; name: string; location: string }
export type Customer = { customer_id: number; name: string; phone: string; email?: string; address?: string }
export type Supplier = { supplier_id: number; name: string; phone: string; email?: string; address?: string }
export type User = { user_id: number; username: string; full_name: string; role: Role; warehouse_id: number | null }
export type Notification = { notification_id: number; title: string; message: string; notification_type: string; is_read: boolean; created_at: string }
export type MessageContact = { user_id: number; username: string; full_name: string; role: Role }
export type IncomingMessage = { message_id: number; sender_id: number; sender_username: string; sender_role: Role; subject: string; body: string; is_read: boolean; created_at: string; reply_to_id?: number; can_reply: boolean }
export type Invoice = { invoice_id: number; order_id: number; customer_id: number; generated_by?: string; total_amount: number; status: string; created_at?: string; sent_at?: string; confirmed_at?: string }
export type SalesOrder = { order_id: number; customer_id: number; created_by: number; status: string; created_at: string; items: Array<{ product_name: string; quantity: number }> }

export type ProductInput = Omit<Product, 'product_id' | 'reorder_level' | 'units_per_box'> & { reorder_level?: number; units_per_box?: number; boxed_units?: number; unit_price?: number; box_unit_cost?: number; batch_number?: string; manufacturing_date?: string; expiry_date?: string }
export type CustomerInput = Omit<Customer, 'customer_id'>
export type SupplierInput = Omit<Supplier, 'supplier_id'>

const API_URL = import.meta.env.VITE_API_URL ?? '/api'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('pantryos_token')
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail
    if (response.status === 401) {
      localStorage.removeItem('pantryos_token')
      window.dispatchEvent(new Event('pantryos:session-expired'))
    }
    throw new Error(detail ?? (response.status === 401 ? 'Your session has expired. Please sign in again.' : 'Request failed'))
  }
  return response.json() as Promise<T>
}

export async function getDashboard() {
  return api<DashboardData>('/dashboard/')
}

export async function login(username: string, password: string) {
  const result = await api<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  localStorage.setItem('pantryos_token', result.access_token)
  return getCurrentUser()
}

export async function register(input: { username: string; full_name: string; password: string; role: Role; warehouse_id?: number; warehouse_name?: string }) {
  return api<{ message: string; request_id?: number; user_id?: number; username: string; role: Role; warehouse_id?: number; status: string }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
export async function getSignupWarehouses() { return api<{ warehouses: Warehouse[] }>('/auth/warehouses') }

export async function getCurrentUser() {
  return api<AuthUser>('/auth/me')
}

export async function getRegistrationRequests() { return api<{ requests: RegistrationRequest[] }>('/auth/registration-requests') }
export async function approveRegistration(requestId: number) { return api<Record<string, unknown>>(`/auth/registration-requests/${requestId}/approve`, { method: 'PATCH' }) }
export async function rejectRegistration(requestId: number) { return api<Record<string, unknown>>(`/auth/registration-requests/${requestId}/reject`, { method: 'PATCH' }) }

export function logout() {
  localStorage.removeItem('pantryos_token')
}

export async function getProducts() { return api<{ products: Product[] }>('/products/') }
export async function getInventory() { return api<{ inventory: InventoryRecord[] }>('/inventory/') }
export async function getWarehouses() { return api<{ warehouses: Warehouse[] }>('/warehouses/') }
export async function getCustomers() { return api<{ customers: Customer[] }>('/customers/') }
export async function getSuppliers() { return api<{ suppliers: Supplier[] }>('/suppliers/') }
export async function getUsers() { return api<{ users: User[] }>('/users/') }
export async function deleteUser(userId: number, password?: string) { return api<{ message: string; user_id: number }>(`/users/${userId}/remove`, { method: 'POST', ...(password ? { body: JSON.stringify({ password }) } : {}) }) }
export async function getNotifications() { return api<{ notifications: Notification[] }>('/notifications/') }
export async function markNotificationRead(notificationId: number) { return api<{ notification_id: number; is_read: boolean }>(`/notifications/${notificationId}/read`, { method: 'PATCH' }) }
export async function getMessageContacts() { return api<{ contacts: MessageContact[] }>('/notifications/contacts') }
export async function getMessages() { return api<{ messages: IncomingMessage[] }>('/notifications/messages') }
export async function sendMessage(input: { recipient_ids?: number[]; subject: string; body: string; broadcast?: boolean; reply_to_id?: number }) { return api<{ message: string; recipient_count: number }>('/notifications/messages', { method: 'POST', body: JSON.stringify(input) }) }
export async function markMessageRead(messageId: number) { return api<{ message_id: number; is_read: boolean }>(`/notifications/messages/${messageId}/read`, { method: 'PATCH' }) }
export async function getInvoices() { return api<{ invoices: Invoice[] }>('/invoices/') }
export async function getExpiringInventory(days = 7) { return api<{ days: number; items: Array<{ inventory_id: number; product_id: number; product_name: string; warehouse_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string; status: string; days_remaining: number; estimated_value: number }> }>(`/inventory/expiring?days=${days}`) }
export async function getExpiredInventory() { return api<{ items: Array<{ inventory_id: number; product_id: number; product_name: string; batch_id: number; batch_number: string; quantity: number; expiry_date: string; status: string; estimated_value: number }> }>('/inventory/expired') }
export async function getProductInventory(productId: number) { return api<{ product_id: number; inventory: InventoryRecord[] }>(`/inventory/product/${productId}`) }
export async function getFefo(productId: number) { return api<{ product_id: number; batches: Array<{ inventory_id: number; warehouse_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string }> }>(`/inventory/fefo/${productId}`) }
export async function getOrder(orderId: number) { return api<{ order_id: number; customer_id: number; created_by: number; status: string; created_at: string; items: Array<{ product_id: number; product_name: string; quantity: number; unit_price: number }>; fefo_allocations: Array<{ product_id: number; product_name: string; allocations: Array<{ inventory_id: number; batch_id: number; batch_number: string; quantity: number; expiry_date: string }> }> }>(`/orders/${orderId}`) }
export async function getOrders() { return api<{ orders: SalesOrder[] }>('/orders/') }
export async function getWarehouseRequests() { return api<{ requests: Array<{ request_id: number; product_id: number; product_name: string; quantity: number; status: string; requested_by: number; created_at: string }> }>('/orders/warehouse-requests') }
export async function requestWarehouseStock(input: { product_id: number; quantity: number }) { return api<Record<string, unknown>>('/orders/warehouse-requests', { method: 'POST', body: JSON.stringify(input) }) }
export async function approveWarehouseRequest(requestId: number) { return api<Record<string, unknown>>(`/orders/warehouse-requests/${requestId}/approve`, { method: 'PATCH' }) }
export async function rejectWarehouseRequest(requestId: number) { return api<Record<string, unknown>>(`/orders/warehouse-requests/${requestId}/reject`, { method: 'PATCH' }) }
export async function getInvoice(invoiceId: number) { return api<Invoice>(`/invoices/${invoiceId}`) }
export async function getLowStock() { return api<{ low_stock: Array<Product & { current_quantity: number }> }>('/products/low-stock') }
export async function createProduct(input: ProductInput) { return api<Product>('/products/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createCustomer(input: CustomerInput) { return api<Customer>('/customers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createSupplier(input: SupplierInput) { return api<Supplier>('/suppliers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createOrder(input: { customer_id?: number; customer_name?: string; items: Array<{ product_id: number; quantity: number }> }) { return api<Record<string, unknown>>('/orders/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createSale(input: { customer_name: string; items: Array<{ product_id: number; quantity: number }> }) { return api<Record<string, unknown>>('/orders/sales', { method: 'POST', body: JSON.stringify(input) }) }
export async function createPurchaseOrder(input: { supplier_id?: number; supplier_name?: string; items: Array<{ product_id?: number; product_name?: string; quantity: number }> }) { return api<Record<string, unknown>>('/purchase-orders/', { method: 'POST', body: JSON.stringify(input) }) }
export async function createTransfer(input: { product_id: number; batch_id: number; source_warehouse_id: number; destination_warehouse_id: number; quantity: number }) { return api<Record<string, unknown>>('/stock-transfers/', { method: 'POST', body: JSON.stringify(input) }) }
export async function approveOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/approve`, { method: 'PATCH' }) }
export async function rejectOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/reject`, { method: 'PATCH' }) }
export async function fulfillOrder(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/fulfill`, { method: 'PATCH' }) }
export async function confirmOrderReceipt(orderId: number) { return api<Record<string, unknown>>(`/orders/${orderId}/confirm-receipt`, { method: 'PATCH' }) }
export async function getInventoryAdditionRequests() { return api<{ requests: Array<{ request_id: number; product_id: number; product_name: string; quantity: number; boxed_units: number; status: string; requested_by: number; created_at: string }> }>('/inventory/addition-requests') }
export async function createInventoryAdditionRequest(input: { product_name: string; category: string; quantity: number; units_per_box: number; boxed_units: number; unit_price: number; box_unit_cost: number; scanned_codes?: string[]; batch_number: string; manufacturing_date: string; expiry_date: string }) { return api<Record<string, unknown>>('/inventory/addition-requests', { method: 'POST', body: JSON.stringify(input) }) }
export async function approveInventoryAddition(requestId: number) { return api<Record<string, unknown>>(`/inventory/addition-requests/${requestId}/approve`, { method: 'PATCH' }) }
export async function rejectInventoryAddition(requestId: number) { return api<Record<string, unknown>>(`/inventory/addition-requests/${requestId}/reject`, { method: 'PATCH' }) }
export async function receivePurchaseOrder(purchaseOrderId: number, input: { warehouse_id: number; items: Array<{ product_id?: number; product_name?: string; quantity: number; batch_number: string; manufacturing_date: string; expiry_date: string }> }) { return api<Record<string, unknown>>(`/purchase-orders/${purchaseOrderId}/receive`, { method: 'PATCH', body: JSON.stringify(input) }) }
export async function approveTransfer(transferId: number) { return api<Record<string, unknown>>(`/stock-transfers/${transferId}/approve`, { method: 'PATCH' }) }
export async function rejectTransfer(transferId: number) { return api<Record<string, unknown>>(`/stock-transfers/${transferId}/reject`, { method: 'PATCH' }) }
export async function generateInvoice(orderId: number) { return api<Invoice>(`/invoices/generate/${orderId}`, { method: 'POST' }) }
export async function sendInvoice(invoiceId: number) { return api<Record<string, unknown>>(`/invoices/${invoiceId}/send`, { method: 'PATCH' }) }
export async function confirmInvoice(invoiceId: number) { return api<Record<string, unknown>>(`/invoices/${invoiceId}/confirm`, { method: 'PATCH' }) }
