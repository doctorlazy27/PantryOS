import { useEffect, useState } from 'react'
import { confirmOrderReceipt, generateInvoice, getOrders } from './api'

type Props = { onToast: (message: string) => void }

export default function ReceiptPanel({ onToast }: Props) {
  const [orders, setOrders] = useState<Awaited<ReturnType<typeof getOrders>>['orders']>([])
  const load = async () => { try { setOrders((await getOrders()).orders.filter((order) => order.status === 'fulfilled' || order.status === 'confirmed')) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load fulfilled orders') } }
  useEffect(() => { void load() }, [])
  async function confirm(orderId: number) { try { await confirmOrderReceipt(orderId); onToast(`Order #${orderId} marked received`); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Could not confirm order receipt') } }
  async function invoice(orderId: number) { try { await generateInvoice(orderId); onToast(`Sales invoice created for order #${orderId}`); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Could not create sales invoice') } }
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Sales completion</p><h2>Delivered orders</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{orders.length ? orders.map((order) => <div className="data-row compact" key={order.order_id}><strong>Order #{order.order_id}</strong><span>Customer #{order.customer_id}</span><span className={`pill ${order.status === 'confirmed' ? 'ready' : 'pending'}`}>{order.status}</span>{order.status === 'fulfilled' ? <button className="row-action" onClick={() => void confirm(order.order_id)}>Confirm received</button> : <button className="row-action" onClick={() => void invoice(order.order_id)}>Create sales invoice</button>}</div>) : <p className="field-hint">No delivered orders are waiting for action.</p>}</section>
}
