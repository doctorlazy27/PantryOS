import { FormEvent, useState } from 'react'
import { Truck } from 'lucide-react'
import { approveTransfer, createTransfer, rejectTransfer, Role } from './api'

type Props = { onToast: (message: string) => void; role: Role }

export default function TransferPanel({ onToast, role }: Props) {
  const [form, setForm] = useState({ product: '', batch: '', source: '', destination: '', quantity: '1' })

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      await createTransfer({ product_id: Number(form.product), batch_id: Number(form.batch), source_warehouse_id: Number(form.source), destination_warehouse_id: Number(form.destination), quantity: Number(form.quantity) })
      onToast('Transfer requested')
      setForm({ product: '', batch: '', source: '', destination: '', quantity: '1' })
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Transfer request failed')
    }
  }

  async function review(approve: boolean) { const id = Number(form.batch); try { if (approve) await approveTransfer(id); else await rejectTransfer(id); onToast(approve ? 'Transfer approved' : 'Transfer rejected') } catch (error) { onToast(error instanceof Error ? error.message : 'Transfer review failed') } }

  return <>{role === 'salesperson' && <section className="panel workflow-card"><p className="eyebrow">Stock movement</p><h2>Request a warehouse transfer</h2><p className="panel-intro">Enter the product, batch, source warehouse ID, and destination warehouse ID.</p><form className="form-grid" onSubmit={submit}><label>Product ID<input required type="number" min="1" value={form.product} onChange={(event) => setForm({ ...form, product: event.target.value })} /></label><label>Batch ID<input required type="number" min="1" value={form.batch} onChange={(event) => setForm({ ...form, batch: event.target.value })} /></label><label>Source warehouse ID<input required type="number" min="1" value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })} /></label><label>Destination warehouse ID<input required type="number" min="1" value={form.destination} onChange={(event) => setForm({ ...form, destination: event.target.value })} /></label><label>Quantity<input required type="number" min="1" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label><div className="form-actions"><button className="button primary" type="submit"><Truck size={16} /> Request transfer</button></div></form></section>}{role === 'manager' && <section className="panel workflow-card"><p className="eyebrow">Transfer review</p><h2>Approve or reject transfer</h2><label>Transfer ID<input required type="number" min="1" value={form.batch} onChange={(event) => setForm({ ...form, batch: event.target.value })} /></label><div className="form-actions"><button className="button primary" onClick={() => void review(true)}>Approve</button><button className="button subtle" onClick={() => void review(false)}>Reject</button></div></section>}</>
}
