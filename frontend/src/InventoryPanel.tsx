import { FormEvent, useEffect, useState } from 'react'
import { createProduct, getProducts, Product, Role } from './api'

type Props = { role: Role; onToast: (message: string) => void }
type FormState = { name: string; category: string; storage_section: string; shelf_number: string; quantity: string; unit: string; price: string; batch_number: string; manufacturing_date: string; expiry_date: string }
const emptyForm: FormState = { name: '', category: '', storage_section: '', shelf_number: '', quantity: '', unit: '', price: '', batch_number: '', manufacturing_date: '', expiry_date: '' }

export default function InventoryPanel({ role, onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm)

  async function load() {
    try { setProducts((await getProducts()).products) }
    catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory') }
  }

  useEffect(() => { void load() }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const quantity = Number(form.quantity)
    const price = Number(form.price)
    if (!form.name.trim() || !form.category.trim() || !form.storage_section.trim() || !form.shelf_number.trim() || !form.unit.trim() || !Number.isFinite(quantity) || !Number.isFinite(price) || quantity < 0 || price < 0) { onToast('Enter a valid product, section, shelf, quantity, unit, and price'); return }
    try {
      await createProduct({ name: form.name.trim(), category: form.category.trim(), storage_section: form.storage_section.trim(), shelf_number: form.shelf_number.trim(), quantity, unit: form.unit.trim(), price, batch_number: form.batch_number.trim(), manufacturing_date: form.manufacturing_date, expiry_date: form.expiry_date })
      setForm(emptyForm); setOpen(false); await load(); onToast('Product and inventory batch added')
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not add product') }
  }

  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Stock control</p><h2>Inventory locations</h2></div>{role === 'warehouse_worker' && <button className="button primary" onClick={() => setOpen(true)}>Add product</button>}</div>{products.length ? <div className="data-table"><div className="data-head"><span>Product</span><span>Section</span><span>Shelf</span><span>Quantity</span><span>Unit</span><span>Price</span></div>{products.map((product) => <div className="data-row" key={product.product_id}><strong>{product.name}</strong><span>{product.storage_section || product.category}</span><span>{product.shelf_number || 'Unassigned'}</span><span>{product.quantity}</span><span>{product.unit}</span><span>${Number(product.price).toFixed(2)}</span></div>)}</div> : <p className="field-hint">No products have been added yet.</p>}{open && <div className="modal-backdrop" onMouseDown={() => setOpen(false)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><p className="eyebrow">Warehouse stock</p><h2>Add product batch</h2></div></div><form className="form-grid" onSubmit={submit}><label>Name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Category<input required value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} /></label><label>Storage section<input required placeholder="Fruits, Dairy, Dry goods..." value={form.storage_section} onChange={(event) => setForm({ ...form, storage_section: event.target.value })} /></label><label>Shelf number<input required placeholder="A-03" value={form.shelf_number} onChange={(event) => setForm({ ...form, shelf_number: event.target.value })} /></label><label>Quantity<input required type="number" min="0" placeholder="Enter quantity" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label><label>Unit<input required placeholder="kg, box, litre..." value={form.unit} onChange={(event) => setForm({ ...form, unit: event.target.value })} /></label><label>Price<input required type="number" min="0" step="0.01" placeholder="Enter price" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} /></label><label>Batch number<input required value={form.batch_number} onChange={(event) => setForm({ ...form, batch_number: event.target.value })} /></label><label>Manufacturing date<input required type="date" value={form.manufacturing_date} onChange={(event) => setForm({ ...form, manufacturing_date: event.target.value })} /></label><label>Expiry date<input required type="date" value={form.expiry_date} onChange={(event) => setForm({ ...form, expiry_date: event.target.value })} /></label><div className="form-actions"><button className="button subtle" type="button" onClick={() => setOpen(false)}>Cancel</button><button className="button primary" type="submit">Add to inventory</button></div></form></div></div>}</section>
}