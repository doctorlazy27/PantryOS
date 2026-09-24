import { FormEvent, useEffect, useRef, useState } from 'react'
import { Barcode, Camera, CheckCircle2, Minus, ScanLine, X } from 'lucide-react'
import { Capacitor } from '@capacitor/core'
import { BarcodeScanner } from '@capacitor-mlkit/barcode-scanning'
import { reduceInventoryByBarcode } from './api'

type Props = { onToast: (message: string) => void; onReduced: () => void }

export default function BarcodeReductionPanel({ onToast, onReduced }: Props) {
  const [code, setCode] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [scanning, setScanning] = useState(false)
  const [cameraBlocked, setCameraBlocked] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const activeRef = useRef(false)

  const stop = () => {
    activeRef.current = false
    setScanning(false)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }
  useEffect(() => () => stop(), [])

  const applyCode = (value: string) => { if (value.trim()) { setCode(value.trim()); onToast('Barcode ready to reduce stock') } }

  async function openScanner() {
    if (Capacitor.isNativePlatform()) {
      try {
        const permission = await BarcodeScanner.requestPermissions()
        if (permission.camera !== 'granted') { setCameraBlocked(true); onToast('Camera permission is required to scan stock'); return }
        setCameraBlocked(false)
        const result = await BarcodeScanner.scan({ autoZoom: true })
        applyCode(result.barcodes[0]?.rawValue ?? '')
      } catch { setCameraBlocked(true); onToast('Scanner unavailable; enter the barcode manually') }
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) { onToast('Camera unavailable; enter the barcode manually'); return }
    try {
      const Detector = (window as unknown as { BarcodeDetector?: new () => { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> } }).BarcodeDetector
      if (!Detector) { onToast('This browser cannot scan barcodes; enter it manually'); return }
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      setScanning(true); activeRef.current = true
      const detector = new Detector()
      const scan = async () => {
        if (!activeRef.current || !videoRef.current) return
        const result = await detector.detect(videoRef.current).catch(() => [])
        if (result[0]?.rawValue) { applyCode(result[0].rawValue); stop() } else window.setTimeout(() => void scan(), 350)
      }
      window.setTimeout(() => { if (videoRef.current) videoRef.current.srcObject = streamRef.current; void scan() }, 250)
    } catch { onToast('Camera unavailable; enter the barcode manually') }
  }

  async function reduce(event: FormEvent) {
    event.preventDefault()
    const amount = Number(quantity)
    if (!code.trim() || !Number.isInteger(amount) || amount < 1) { onToast('Scan a barcode and enter a valid quantity'); return }
    try {
      const result = await reduceInventoryByBarcode({ scanned_code: code.trim(), quantity: amount, scan_event_id: crypto.randomUUID() })
      onToast(`${result.product_name}: ${result.quantity_removed} removed, ${result.remaining_quantity} left`)
      setCode(''); setQuantity('1'); onReduced()
    } catch (error) { onToast(error instanceof Error ? error.message : 'Could not reduce stock') }
  }

  return <section className="panel scan-panel"><div className="scan-heading"><div className="scan-icon"><ScanLine size={20} /></div><div><p className="eyebrow">Stock movement</p><h2>Scan to reduce</h2><p>Scan the product or box barcode when stock leaves the warehouse.</p></div></div><form className="scan-form" onSubmit={reduce}><label><span>Barcode</span><div className="scan-input"><Barcode size={17} /><input autoComplete="off" inputMode="text" value={code} placeholder="Scan or enter barcode" onChange={(event) => setCode(event.target.value)} /><button type="button" aria-label="Open barcode scanner" title="Open barcode scanner" onClick={() => void openScanner()}><Camera size={18} /></button></div></label><label><span>Units leaving</span><input type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><button className="button primary scan-submit" type="submit"><Minus size={16} /> Reduce stock</button></form>{scanning && <div className="scanner-window"><video ref={videoRef} autoPlay playsInline /><button type="button" className="icon-button scanner-close" onClick={stop} aria-label="Close scanner"><X size={18} /></button><span>Point at a product barcode</span></div>}{cameraBlocked && <button className="link-button" type="button" onClick={() => void BarcodeScanner.openSettings()}>Open camera permissions</button>}<div className="scan-note"><CheckCircle2 size={15} />Every reduction is recorded in the warehouse movement history.</div></section>
}