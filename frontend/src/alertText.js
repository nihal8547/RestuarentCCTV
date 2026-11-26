import { mmss } from './i18n.jsx'

/** Localised alert sentence built from structured params (falls back to the server's English message). */
export function alertText(a, t) {
  const p = a.params || {}
  if (a.kind === 'service_wait' && p.number != null)
    return t('alerts.msg.service_wait', { n: String(p.number).padStart(2, '0'), g: p.guests, m: mmss(p.secs) })
  if (a.kind === 'uncleaned_table' && p.number != null)
    return t('alerts.msg.uncleaned_table', { n: String(p.number).padStart(2, '0'), m: mmss(p.secs) })
  if (a.kind === 'camera_offline' && p.camera) return t('alerts.msg.camera_offline', { c: p.camera })
  return a.message
}

export function ago(ts, now, t) {
  const s = Math.max(0, Math.floor(now - ts))
  if (s < 60) return t('ago.s', { n: s })
  if (s < 3600) return t('ago.m', { n: Math.floor(s / 60) })
  return t('ago.h', { n: Math.floor(s / 3600) })
}

export const ALERT_STYLE = {
  service_wait: { icon: '🕔', tone: 'border-red-500/40 bg-red-500/5', chip: 'bg-red-500/20 text-red-300' },
  uncleaned_table: { icon: '🧹', tone: 'border-amber-500/40 bg-amber-500/5', chip: 'bg-amber-500/20 text-amber-300' },
  camera_offline: { icon: '📷', tone: 'border-fuchsia-500/40 bg-fuchsia-500/5', chip: 'bg-fuchsia-500/20 text-fuchsia-300' },
}
