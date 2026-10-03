import { useState } from 'react'
import { getTemperatureLogs, TemperatureLog } from './api'
import { LoadingState } from './LoadingState'
import { useLiveRefresh } from './useLiveRefresh'

type Props = { onToast: (message: string) => void; onNavigate: (view: 'Inventory') => void }

export default function ColdChainDashboardPanel({ onToast, onNavigate }: Props) {
  const [logs, setLogs] = useState<TemperatureLog[]>([])
  const load = async () => { try { setLogs((await getTemperatureLogs()).logs) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load cold-chain status') } }
  const { initialLoading } = useLiveRefresh(load)
  if (initialLoading) return <LoadingState label="Loading cold-chain status" />
  const exceptions = logs.filter((log) => !log.within_range)
  return <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Cold-chain health</p><h2>{exceptions.length ? `${exceptions.length} recent exception${exceptions.length === 1 ? '' : 's'}` : 'No recent temperature exceptions'}</h2></div><button className="link-button" onClick={() => onNavigate('Inventory')}>Open inventory</button></div>{logs.length ? <div className="data-table"><div className="data-head"><span>Batch</span><span>Zone</span><span>Reading</span><span>Range</span><span>Recorded</span></div>{logs.slice(0, 5).map((log) => <div className="data-row compact" key={log.temperature_log_id}><strong>#{log.batch_id}</strong><span>{log.storage_zone}</span><span className={log.within_range ? '' : 'warning-text'}>{log.temperature_c} C</span><span>{log.minimum_c} to {log.maximum_c ?? 'no max'} C</span><span>{new Date(log.recorded_at).toLocaleString()}</span></div>)}</div> : <p className="field-hint">Temperature readings appear here after a delivery QC check or storage check.</p>}</section>
}