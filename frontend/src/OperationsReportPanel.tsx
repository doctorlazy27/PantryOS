import { useState } from 'react'
import { getOperationalMetrics, OperationalMetrics } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void }
const empty: OperationalMetrics = { period_days: 30, sold_units: 0, current_saleable_stock: 0, stock_turn_rate: null, fefo_verified_units: 0, fulfilled_units: 0, fefo_compliance_percent: null, expired_units: 0, disposed_units: 0, donated_units: 0, waste_units: 0 }

export default function OperationsReportPanel({ onToast }: Props) {
  const [metrics, setMetrics] = useState(empty)
  const load = async () => { try { setMetrics(await getOperationalMetrics()) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load operational metrics') } }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading warehouse performance" />
  const cards = [
    ['FEFO verified', metrics.fefo_compliance_percent === null ? 'No completed orders' : `${metrics.fefo_compliance_percent}%`, `${metrics.fefo_verified_units} of ${metrics.fulfilled_units} fulfilled units were scanned`],
    ['Stock turn', metrics.stock_turn_rate === null ? 'N/A' : `${metrics.stock_turn_rate}x`, `${metrics.sold_units} sold units against ${metrics.current_saleable_stock} saleable on hand`],
    ['Food waste', `${metrics.waste_units} units`, `${metrics.expired_units} expired · ${metrics.disposed_units} disposed`],
    ['Donation saved', `${metrics.donated_units} units`, `Recorded as donated in the last ${metrics.period_days} days`],
  ]
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Operations · last {metrics.period_days} days</p><h2>Food waste and FEFO performance</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div><div className="stat-grid">{cards.map(([label, value, detail]) => <article className="stat-card sage" key={label}><div className="stat-card-top"><span>{label}</span></div><div className="stat-value">{value}</div><div className="stat-foot">{detail}</div></article>)}</div></section>
}