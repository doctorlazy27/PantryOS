import { FormEvent, useEffect, useState } from 'react'
import { ArrowDownToLine, CheckCircle2, Plus, RefreshCw } from 'lucide-react'
import { createPurchaseOrder, getCurrentUser, getProducts, getPurchaseOrders, Product, PurchaseOrder, receivePurchaseOrder } from './api'

type Props = { role: 'salesperson' | 'warehouse_worker' | 'manager'; onToast: (message: string) => void }

export default function ReceivingPanel({ role, onToast }: Props) {
  const [supplier, setSupplier] = useState('')
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [products, setProducts] = useState<Product[]>([])
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [selectedOrder, setSelectedOrder] = useState<PurchaseOrder | null>(null)
  const [warehouseId, setWarehouseId] = useState<number | null>(null)
  const [batch, setBatch] = useState({ number: '', manufactured: '', expiry: '' })

  const load = async () => {
    try {
      const [orderData, productData, user] = await Promise.all([getPurchaseOrders(), getProducts(), getCurrentUser()])
      setOrders(orderData.purchase_orders)
      setProducts(productData.products)
      setWarehouseId(user.warehouse_id)
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load receiving queue') }
  }
  useEffect(() => { void load() }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await createPurchaseOrder({ supplier_name: supplier.trim(), items: [{ product_id: Number(product), quantity: Number(quantity) }] })
      onToast('Purchase request sent to the warehouse queue')
      setSupplier(''); setProduct(''); setQuantity('1'); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not create purchase request') }
  }

  async function receive(event: FormEvent) {
    event.preventDefault()
    if (!selectedOrder || !warehouseId) return
    const manufactured = new Date(`${batch.manufactured}T00:00:00`)
    const expiry = new Date(`${batch.expiry}T00:00:00`)
    if (!batch.number.trim() || !batch.manufactured || !batch.expiry || expiry <= manufactured) { onToast('Enter a batch number and an expiry date after manufacturing'); return }
    try {
      await receivePurchaseOrder(selectedOrder.purchase_order_id, { warehouse_id: warehouseId, items: selectedOrder.items.map((item) => ({ product_id: item.product_id, quantity: item.quantity, batch_number: batch.number.trim(), manufacturing_date: batch.manufactured, expiry_date: batch.expiry })) })
      onToast(`Purchase order #${selectedOrder.purchase_order_id} received and stock added`)
      setSelectedOrder(null); setBatch({ number: '', manufactured: '', expiry: '' }); await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not receive purchase order') }
  }

  return <>
    <Header eyebrow="Inbound stock" title="Receiving" description="Managers request stock. Workers receive it, assign the physical batch, and put it into the assigned warehouse." />
    {role === 'manager' && <section className="panel workflow-card receiving-card"><div className="workflow-number"><Plus size={17} /></div><p className="eyebrow">Step 1 · Manager</p><h2>Request inbound stock</h2><p>Create a purchase request for the warehouse. No inventory or batch is created until the delivery is physically received.</p><form className="stack-form" onSubmit={create}><label>Supplier name<input required value={supplier} placeholder="e.g. Green Valley Foods" onChange={(event) => setSupplier(event.target.value)} /></label><label>Product<select required value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Select food item</option>{products.map((item) => <option value={item.product_id} key={item.product_id}>{item.name} · {item.category}</option>)}</select></label><label>Expected quantity<input required type="number" min="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><button className="button primary" type="submit"><Plus size={16} /> Send purchase request</button></form></section>}
    {role === 'warehouse_worker' && <><section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Step 2 · Worker</p><h2>Inbound queue</h2><span className="table-count">{orders.filter((item) => item.status === 'pending').length} waiting for receipt</span></div><button className="button subtle" onClick={() => void load()}><RefreshCw size={15} /> Refresh</button></div>{orders.filter((item) => item.status === 'pending').length ? <div className="receiving-queue">{orders.filter((item) => item.status === 'pending').map((item) => <button className={`receiving-order ${selectedOrder?.purchase_order_id === item.purchase_order_id ? 'selected' : ''}`} key={item.purchase_order_id} onClick={() => setSelectedOrder(item)}><span className="order-icon"><ArrowDownToLine size={17} /></span><span><strong>Purchase #{item.purchase_order_id}</strong><small>{item.supplier_name} · {item.items.map((line) => `${line.product_name} x${line.quantity}`).join(', ')}</small></span><span className="pill pending">Pending</span></button>)}</div> : <div className="empty-state"><CheckCircle2 size={27} /><strong>Receiving queue is clear</strong><span>New manager purchase requests will appear here.</span></div>}</section>{selectedOrder && <section className="panel workflow-card receiving-card"><div className="workflow-number"><ArrowDownToLine size={17} /></div><p className="eyebrow">Step 3 · Receive and identify</p><h2>Receive purchase #{selectedOrder.purchase_order_id}</h2><p>Assign the batch from the delivery label now. This batch number follows the stock through expiry and FEFO picking.</p><form className="stack-form" onSubmit={receive}><label>Batch number<input required value={batch.number} placeholder="e.g. MLK-2026-0924-A" onChange={(event) => setBatch({ ...batch, number: event.target.value })} /></label><label>Manufacturing date<input required type="date" value={batch.manufactured} onChange={(event) => setBatch({ ...batch, manufactured: event.target.value })} /></label><label>Expiry date<input required type="date" value={batch.expiry} onChange={(event) => setBatch({ ...batch, expiry: event.target.value })} /></label><button className="button primary" type="submit"><CheckCircle2 size={16} /> Receive into warehouse</button></form></section>}</>}
  </>
}

function Header({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <section className="module-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div></section> }
