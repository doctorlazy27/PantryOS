import { FormEvent, useEffect, useState } from 'react'
import { ArrowDownToLine, Plus } from 'lucide-react'
import { createPurchaseOrder, receivePurchaseOrder } from './api'

type Props = { role: 'salesperson' | 'warehouse_worker' | 'manager'; onToast: (message: string) => void }

export default function ReceivingPanel({ role, onToast }: Props) {
  const [supplierName, setSupplierName] = useState('')
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [purchaseId, setPurchaseId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [batch, setBatch] = useState({ number: '', manufactured: '', expiry: '' })

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await createPurchaseOrder({ supplier_name: supplierName.trim(), items: [{ product_name: product.trim(), quantity }] })
      onToast('Purchase order created')
      setSupplierName('')
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not create purchase order') }
  }

  async function receive(event: FormEvent) {
    event.preventDefault()
    try {
      await receivePurchaseOrder(Number(purchaseId), { warehouse_id: Number(warehouseId), items: [{ product_name: product.trim(), quantity, batch_number: batch.number, manufacturing_date: batch.manufactured, expiry_date: batch.expiry }] })
      onToast('Purchase order received')
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not receive purchase order') }
  }

  return <><Header eyebrow="Inbound stock" title="Receiving" description="Create purchase orders with any supplier and product, then receive them into your assigned warehouse." />{role === 'salesperson' && <section className="panel workflow-card"><p className="eyebrow">Purchase order</p><h2>Create inbound order</h2><form className="stack-form" onSubmit={create}><label>Supplier name<input required value={supplierName} placeholder="Enter any supplier or company" onChange={(event) => setSupplierName(event.target.value)} /></label><label>Product name<input required value={product} placeholder="Enter any product" onChange={(event) => setProduct(event.target.value)} /></label><label>Quantity<input type="number" min="1" value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} /></label><button className="button primary" type="submit"><Plus size={16} /> Create purchase order</button></form></section>}{role === 'warehouse_worker' && <section className="panel workflow-card"><p className="eyebrow">Warehouse receiving</p><h2>Receive purchase order</h2><form className="stack-form" onSubmit={receive}><label>Purchase order ID<input required type="number" min="1" value={purchaseId} onChange={(event) => setPurchaseId(event.target.value)} /></label><label>Warehouse ID<input required type="number" min="1" value={warehouseId} placeholder="Your assigned warehouse ID" onChange={(event) => setWarehouseId(event.target.value)} /></label><label>Product name<input required value={product} placeholder="Enter product from the purchase order" onChange={(event) => setProduct(event.target.value)} /></label><label>Quantity<input type="number" min="1" value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} /></label><label>Batch number<input required value={batch.number} onChange={(event) => setBatch({ ...batch, number: event.target.value })} /></label><label>Manufacturing date<input required type="date" value={batch.manufactured} onChange={(event) => setBatch({ ...batch, manufactured: event.target.value })} /></label><label>Expiry date<input required type="date" value={batch.expiry} onChange={(event) => setBatch({ ...batch, expiry: event.target.value })} /></label><button className="button primary" type="submit"><ArrowDownToLine size={16} /> Receive stock</button></form></section>}</>
}

function Header({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <section className="module-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div></section> }
