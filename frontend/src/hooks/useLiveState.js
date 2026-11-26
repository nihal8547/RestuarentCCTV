import { useEffect, useRef, useState } from 'react'
import { getToken } from '../api.js'

/** Subscribes to the backend WebSocket (/ws, authenticated via ?token=) and auto-reconnects. */
export default function useLiveState(enabled = true) {
  const [state, setState] = useState(null)
  const [connected, setConnected] = useState(false)
  const retry = useRef(0)

  useEffect(() => {
    if (!enabled) return undefined
    let ws
    let timer
    let closed = false

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const tok = getToken()
      ws = new WebSocket(`${proto}://${window.location.host}/ws${tok ? `?token=${encodeURIComponent(tok)}` : ''}`)
      ws.onopen = () => {
        retry.current = 0
        setConnected(true)
      }
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data && data.tables) setState(data)
        } catch {
          /* ignore malformed frame */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        retry.current += 1
        timer = setTimeout(connect, Math.min(1000 * retry.current, 5000))
      }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => {
      closed = true
      clearTimeout(timer)
      ws && ws.close()
    }
  }, [enabled])

  return { state, connected }
}
