import { FormEvent, useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, CheckCircle2, PackageCheck } from 'lucide-react'
import { getSignupWarehouses, login, register, Role, Warehouse } from './api'

type Props = { onLogin: (user: Awaited<ReturnType<typeof login>>) => void }

export default function AuthAccess({ onLogin }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('salesperson')
  const [warehouseInput, setWarehouseInput] = useState('')
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => { if (mode === 'signup') void getSignupWarehouses().then((data) => setWarehouses(data.warehouses)).catch(() => setError('Could not load warehouses')) }, [mode])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')
    try {
      if (mode === 'login') onLogin(await login(username, password))
      else {
        const numericWarehouseId = Number(warehouseInput)
        const result = await register({ username, full_name: fullName, password, role, warehouse_id: numericWarehouseId > 0 ? numericWarehouseId : undefined, warehouse_name: numericWarehouseId > 0 ? undefined : warehouseInput.trim() })
        setMessage(result.message)
        setPassword('')
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Request failed')
    } finally { setLoading(false) }
  }

  return <div className="auth-shell"><div className="auth-visual"><div className="auth-brand"><div className="brand-mark"><PackageCheck size={19} /></div><strong>PantryOS</strong></div><div className="auth-visual-copy"><p className="eyebrow">Food warehouse management</p><h1>Every batch accounted for.</h1><p>Inventory, orders, receiving, transfers, and invoices in one focused workspace.</p></div></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}><div className="auth-tabs"><button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Sign in</button><button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Sign up</button></div><p className="eyebrow">{mode === 'login' ? 'Secure access' : 'Request access'}</p><h2>{mode === 'login' ? 'Sign in to PantryOS' : 'Create an account'}</h2>{mode === 'signup' && <><label>Full name<input required value={fullName} onChange={(event) => setFullName(event.target.value)} /></label><label>Warehouse ID or name<input required list="warehouse-options" placeholder="Example: 1 or Mumbai Central Warehouse" value={warehouseInput} onChange={(event) => setWarehouseInput(event.target.value)} /><datalist id="warehouse-options">{warehouses.map((warehouse) => <option key={warehouse.warehouse_id} value={String(warehouse.warehouse_id)}>{warehouse.name}</option>)}</datalist></label><label>Requested role<select value={role} onChange={(event) => setRole(event.target.value as Role)}><option value="salesperson">Salesperson</option><option value="warehouse_worker">Warehouse worker</option><option value="manager">Manager</option></select></label></>}<label>Username<input required minLength={3} value={username} onChange={(event) => setUsername(event.target.value)} /></label><label>Password<input required minLength={8} type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <div className="auth-error"><AlertTriangle size={15} />{error}</div>}{message && <div className="auth-success"><CheckCircle2 size={15} />{message}</div>}<button className="button primary" type="submit" disabled={loading}>{loading ? 'Please wait...' : mode === 'login' ? 'Continue' : 'Submit request'} <ArrowRight size={16} /></button></form></div></div>
}
