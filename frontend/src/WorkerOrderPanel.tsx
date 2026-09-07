import { useEffect, useState } from 'react'
import { approveOrder, fulfillOrder, getOrders, rejectOrder } from './api'

type Props = { onToast: (message: string) => void }

export default function WorkerOrderPanel({ onToast }: Props) {
  const [orders, setOrders] = useState<Awaited<ReturnType<typeof getOrders>>['orders']>([])
  const load = async () => { try { setOrders((await getOrders()).orders.filter((order) => order.status === 'pending' || order.status === 'approved')) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load warehouse orders') } }
  useEffect(() => { void load() }, [])
  async function action(orderId: number, operation: 'approve' | 'reject' | 'fulfill') { try { if (operation === 'approve') await approveOrder(orderId); if (operation === 'reject') await rejectOrder(orderId); if (operation === 'fulfill') await fulfillOrder(orderId); onToast(operation === 'approve' ? 'Order accepted' : operation === 'reject' ? 'Order rejected' : 'Product dispatched'); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Order action failed') } }
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Warehouse order desk</p><h2>Sales requests</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{orders.length ? orders.map((order) => <div className="data-row compact" key={order.order_id}><strong>Sales request #{order.order_id}</strong><span>Customer #{order.customer_id}</span><span className={`pill ${order.status === 'approved' ? 'ready' : 'pending'}`}>{order.status}</span>{order.status === 'pending' ? <><button className="row-action" onClick={() => void action(order.order_id, 'approve')}>Approve</button><button className="row-action danger" onClick={() => void action(order.order_id, 'reject')}>Reject</button></> : <button className="row-action" onClick={() => void action(order.order_id, 'fulfill')}>Dispatch product</button>}</div>) : <p className="field-hint">No sales requests are waiting for warehouse action.</p>}</section>
}
