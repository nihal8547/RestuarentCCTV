import { useEffect, useRef, useState } from 'react'
import { alertText } from '../alertText.js'

export function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.connect(g)
    g.connect(ctx.destination)
    g.gain.value = 0.2
    o.frequency.value = 880
    o.start()
    setTimeout(() => { o.frequency.value = 660 }, 150)
    setTimeout(() => { o.frequency.value = 880 }, 300)
    setTimeout(() => { o.stop(); ctx.close() }, 480)
  } catch {
    /* audio not available */
  }
}

const KEY = 'alerts_on'

/** App-wide alert signals (any tab): beep + vibrate + system notification + flashing tab title, the moment an alert arrives. */
export default function useAlertNotifier(alerts = [], t) {
  const [enabled, setEnabled] = useState(() => {
    try { return localStorage.getItem(KEY) === '1' } catch { return false }
  })
  const seen = useRef(null)
  const base = useRef(document.title)

  const enable = async () => {
    if ('Notification' in window && Notification.permission === 'default') await Notification.requestPermission()
    try { localStorage.setItem(KEY, '1') } catch { /* private mode */ }
    setEnabled(true)
    beep()
  }
  const disable = () => {
    try { localStorage.setItem(KEY, '0') } catch { /* ignore */ }
    setEnabled(false)
  }

  useEffect(() => {
    const ids = new Set(alerts.map((a) => a.id))
    if (seen.current === null) { seen.current = ids; return }
    const fresh = alerts.filter((a) => !a.resolved && !seen.current.has(a.id))
    seen.current = ids
    if (!fresh.length || !enabled) return
    beep()
    navigator.vibrate?.([200, 100, 200])
    if ('Notification' in window && Notification.permission === 'granted') {
      fresh.forEach((a) => new Notification(t(`alerts.${a.kind}`), { body: alertText(a, t), tag: `alert-${a.id}`, requireInteraction: true }))
    }
  }, [alerts, enabled, t])

  // flash the browser-tab title while any alert is unresolved
  const active = alerts.filter((a) => !a.resolved).length
  useEffect(() => {
    if (!enabled || !active) { document.title = base.current; return }
    let on = false
    const i = setInterval(() => { on = !on; document.title = on ? `(${active}) ALERT` : base.current }, 900)
    return () => { clearInterval(i); document.title = base.current }
  }, [enabled, active])

  return { enabled, enable, disable }
}
