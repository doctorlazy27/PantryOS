import { useEffect, useState } from 'react'
import { Network } from '@capacitor/network'
import { StatusBar, Style } from '@capacitor/status-bar'
import { Wifi, WifiOff } from 'lucide-react'

export function NativeAppEffects() {
  const [online, setOnline] = useState(true)
  const [showState, setShowState] = useState(false)
  useEffect(() => {
    void StatusBar.setOverlaysWebView({ overlay: false }).catch(() => undefined)
    void StatusBar.setStyle({ style: Style.Light }).catch(() => undefined)
    let listener: { remove: () => Promise<void> } | undefined
    void Network.getStatus().then((status) => setOnline(status.connected)).catch(() => undefined)
    void Network.addListener('networkStatusChange', (status) => { setOnline(status.connected); setShowState(true); window.setTimeout(() => setShowState(false), 2400) }).then((handle) => { listener = handle })
    return () => { void listener?.remove() }
  }, [])
  if (online) return null
  return <div className={`connection-pill ${showState ? 'visible' : ''} ${online ? 'connected' : 'offline'}`} aria-live="polite">{online ? <Wifi size={14} /> : <WifiOff size={14} />}<span>{online ? 'Connected' : 'Offline'}</span></div>
}
