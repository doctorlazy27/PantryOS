import { FormEvent, useEffect, useRef, useState } from 'react'
import { Capacitor } from '@capacitor/core'
import { BarcodeScanner } from '@capacitor-mlkit/barcode-scanning'
import { approveInventoryAddition, createInventoryAdditionRequest, getInventoryAdditionRequests, rejectInventoryAddition, Role } from './api'

type Props = { role: Role; onToast: (message: string) => void }
type FormState = { product_name: string; category: string; units_per_box: string; boxed_units: string; unit_price: string; box_unit_cost: string; scanned_code: string; batch_number: string; manufacturing_date: string; expiry_date: string }
const categories = ['Fruits', 'Vegetables', 'Boxed items', 'Ready made items', 'Raw meat items', 'Poultry', 'Dairy', 'Frozen items', 'Other']
const emptyForm: FormState = { product_name: '', category: 'Fruits', units_per_box: '1', boxed_units: '0', unit_price: '', box_unit_cost: '', scanned_code: '', batch_number: '', manufacturing_date: '', expiry_date: '' }

function parseScannedMetadata(rawValue: string): Partial<FormState> {
  const normalized = rawValue.trim()
  if (!normalized) return {}
  try {
    const parsed = JSON.parse(normalized) as Record<string, unknown>
    const value = (keys: string[]) => keys.map((key) => parsed[key]).find((item) => item !== undefined && item !== null)
    const fields = {
      product_name: String(value(['product_name', 'productName', 'name']) ?? ''),
      category: String(value(['category', 'food_section', 'foodSection']) ?? ''),
      units_per_box: String(value(['units_per_box', 'unitsPerBox']) ?? ''),
      boxed_units: String(value(['boxed_units', 'boxedUnits', 'boxes']) ?? ''),
      unit_price: String(value(['unit_price', 'unitPrice', 'price']) ?? ''),
      box_unit_cost: String(value(['box_unit_cost', 'boxUnitCost']) ?? ''),
      batch_number: String(value(['batch_number', 'batchNumber', 'batch']) ?? ''),
      manufacturing_date: String(value(['manufacturing_date', 'manufacturingDate', 'manufactured']) ?? ''),
      expiry_date: String(value(['expiry_date', 'expiryDate', 'expires']) ?? ''),
    }
    return Object.fromEntries(Object.entries(fields).filter(([, fieldValue]) => fieldValue)) as Partial<FormState>
  } catch {
    const values = Object.fromEntries(normalized.split(/[;\n]/).flatMap((part) => {
      const separator = part.indexOf('=') >= 0 ? '=' : ':'
      const index = part.indexOf(separator)
      return index > 0 ? [[part.slice(0, index).trim().toLowerCase(), part.slice(index + 1).trim()]] : []
    }))
    const fields = {
      product_name: values.product_name ?? values.name ?? '',
      category: values.category ?? '',
      units_per_box: values.units_per_box ?? values.unitsperbox ?? '',
      boxed_units: values.boxed_units ?? values.boxedunits ?? values.boxes ?? '',
      unit_price: values.unit_price ?? values.unitprice ?? values.price ?? '',
      box_unit_cost: values.box_unit_cost ?? values.boxunitcost ?? '',
      batch_number: values.batch_number ?? values.batchnumber ?? values.batch ?? '',
      manufacturing_date: values.manufacturing_date ?? values.manufacturingdate ?? '',
      expiry_date: values.expiry_date ?? values.expirydate ?? '',
    }
    return Object.fromEntries(Object.entries(fields).filter(([, fieldValue]) => fieldValue)) as Partial<FormState>
  }
}

export default function InventoryRequestsPanel({ role, onToast }: Props) {
  const [requests, setRequests] = useState<Awaited<ReturnType<typeof getInventoryAdditionRequests>>['requests']>([])
  const [form, setForm] = useState<FormState>(emptyForm)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraPermissionBlocked, setCameraPermissionBlocked] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const scanActiveRef = useRef(false)
  const load = async () => { try { setRequests((await getInventoryAdditionRequests()).requests) } catch (error) { onToast(error instanceof Error ? error.message : 'Could not load inventory requests') } }
  useEffect(() => { void load(); return () => { scanActiveRef.current = false; streamRef.current?.getTracks().forEach((track) => track.stop()) } }, [])

  function applyScan(rawValue: string) {
    setForm((current) => ({ ...current, ...parseScannedMetadata(rawValue), scanned_code: rawValue }))
    onToast('Barcode scanned and inventory fields filled')
  }

  function stopCamera() {
    scanActiveRef.current = false
    setCameraOpen(false)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  async function openCamera() {
    if (Capacitor.isNativePlatform()) {
      try {
        const permission = await BarcodeScanner.requestPermissions()
        if (permission.camera !== 'granted') {
          setCameraPermissionBlocked(true)
          onToast('Allow camera access in Android permissions before scanning')
          return
        }
        setCameraPermissionBlocked(false)
        const result = await BarcodeScanner.scan({ autoZoom: true })
        const rawValue = result.barcodes[0]?.rawValue
        if (rawValue) applyScan(rawValue)
        else onToast('No barcode was detected')
      } catch {
        setCameraPermissionBlocked(true)
        onToast('Camera access was unavailable; open Android camera permissions')
      }
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) { onToast('Camera is not available; enter the boxed-unit code manually'); return }
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      setCameraOpen(true)
      const Detector = (window as unknown as { BarcodeDetector?: new () => { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> } }).BarcodeDetector
      if (!Detector) { onToast('Barcode scanning is unavailable in this browser'); return }
      const detector = new Detector()
      scanActiveRef.current = true
      const scan = async () => {
        if (!videoRef.current || !scanActiveRef.current) return
        const codes = await detector.detect(videoRef.current).catch(() => [])
        if (codes[0]?.rawValue) {
          applyScan(codes[0].rawValue)
          stopCamera()
        } else window.setTimeout(() => void scan(), 500)
      }
      window.setTimeout(() => { if (videoRef.current) videoRef.current.srcObject = streamRef.current; void scan() }, 700)
    } catch { onToast('Camera access was unavailable; enter the boxed-unit code manually') }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const unitsPerBox = Number(form.units_per_box)
    const boxedUnits = Number(form.boxed_units)
    const unitPrice = Number(form.unit_price)
    const boxCost = form.box_unit_cost ? Number(form.box_unit_cost) : unitPrice * unitsPerBox
    const quantity = boxedUnits * unitsPerBox
    if (!form.product_name.trim() || boxedUnits < 1 || unitsPerBox < 1 || !Number.isFinite(unitPrice) || unitPrice < 0 || !form.batch_number.trim() || !form.manufacturing_date || !form.expiry_date) { onToast('Enter a valid food section, box count, units per box, prices, batch, and dates'); return }
    try {
      await createInventoryAdditionRequest({ product_name: form.product_name.trim(), category: form.category, quantity, units_per_box: unitsPerBox, boxed_units: boxedUnits, unit_price: unitPrice, box_unit_cost: boxCost, scanned_codes: form.scanned_code ? [form.scanned_code] : [], batch_number: form.batch_number.trim(), manufacturing_date: form.manufacturing_date, expiry_date: form.expiry_date })
      onToast('Inventory request sent to manager')
      setForm(emptyForm)
      await load()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not submit inventory request') }
  }

  async function review(id: number, approve: boolean) { try { if (approve) await approveInventoryAddition(id); else await rejectInventoryAddition(id); onToast(approve ? 'Inventory request approved' : 'Inventory request rejected'); await load() } catch (error) { onToast(error instanceof Error ? error.message : 'Could not review inventory request') } }

  return <>
    {role === 'warehouse_worker' && <section className="panel workflow-card">
      <p className="eyebrow">Manager approval</p><h2>Request boxed food stock</h2>
      <form className="stack-form" onSubmit={submit}>
        <label>Product name<input required placeholder="Enter any product" value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })} /></label>
        <label>Food section<select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
        <label>Units per box<input required type="number" min="1" value={form.units_per_box} onChange={(event) => setForm({ ...form, units_per_box: event.target.value })} /></label>
        <label>Boxed units<input required type="number" min="1" value={form.boxed_units} onChange={(event) => setForm({ ...form, boxed_units: event.target.value })} /></label>
        <label>Total individual units<input readOnly value={Number(form.units_per_box || 0) * Number(form.boxed_units || 0)} /></label>
        <label>Price per unit<input required type="number" min="0" step="0.01" value={form.unit_price} onChange={(event) => setForm({ ...form, unit_price: event.target.value })} /></label>
        <label>Total cost per box<input type="number" min="0" step="0.01" placeholder={`Defaults to $${(Number(form.unit_price || 0) * Number(form.units_per_box || 0)).toFixed(2)}`} value={form.box_unit_cost} onChange={(event) => setForm({ ...form, box_unit_cost: event.target.value })} /></label>
        <label>Boxed-unit code<input placeholder="Manual scan/code (optional)" value={form.scanned_code} onChange={(event) => setForm({ ...form, scanned_code: event.target.value })} /></label>
        <button className="button subtle" type="button" onClick={() => void openCamera()}>Camera scan and fill fields</button>
        {cameraPermissionBlocked && <button className="button subtle" type="button" onClick={() => void BarcodeScanner.openSettings()}>Open camera permissions</button>}
        {cameraOpen && <video ref={videoRef} autoPlay playsInline className="camera-preview" />}
        {cameraOpen && <button className="button subtle" type="button" onClick={stopCamera}>Stop camera</button>}
        <label>Batch number<input required value={form.batch_number} onChange={(event) => setForm({ ...form, batch_number: event.target.value })} /></label>
        <label>Manufacturing date<input required type="date" value={form.manufacturing_date} onChange={(event) => setForm({ ...form, manufacturing_date: event.target.value })} /></label>
        <label>Expiry date<input required type="date" value={form.expiry_date} onChange={(event) => setForm({ ...form, expiry_date: event.target.value })} /></label>
        <button className="button primary" type="submit">Send manager request</button>
      </form>
    </section>}
    {role === 'manager' && <section className="panel data-panel"><div className="table-toolbar"><div><p className="eyebrow">Inventory approvals</p><h2>{requests.filter((item) => item.status === 'pending').length} pending requests</h2></div><button className="button subtle" onClick={() => void load()}>Refresh</button></div>{requests.filter((item) => item.status === 'pending').map((item) => <div className="data-row compact" key={item.request_id}><strong>Request #{item.request_id}</strong><span>{item.product_name}</span><span>{item.quantity} units · {item.boxed_units} boxes</span><button className="row-action" onClick={() => void review(item.request_id, true)}>Approve</button><button className="row-action danger" onClick={() => void review(item.request_id, false)}>Reject</button></div>)}</section>}
+  </>
}
