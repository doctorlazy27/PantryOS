import { useEffect, useState } from 'react'
import { getProducts, Product, Role } from './api'

type Props = { role: Role; onToast: (message: string) => void }

export default function InventoryOverview({ role, onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const load = async () => { try { setProducts((await getProducts()).products) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory') } }
  useEffect(() => { void load() }, [])
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Warehouse inventory</p><h2>Available products</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{role === 'warehouse_worker' && <p className="field-hint">To add stock, submit an inventory request below. A manager must approve it first.</p>}{products.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Category</span><span>Quantity</span><span>Unit</span><span>Price</span></div>{products.map((product) => <div className="data-row" key={product.product_id}><strong>{product.name}</strong><span>{product.category}</span><span>{product.quantity}</span><span>{product.unit}</span><span>${Number(product.price).toFixed(2)}</span></div>)}</div> : <p className="field-hint">No products have been added yet.</p>}</section>
}
