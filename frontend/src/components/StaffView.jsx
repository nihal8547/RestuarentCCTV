import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import { useI18n } from '../i18n.jsx'
import Icon from './Icon.jsx'
import { ALERT_STYLE, ago, alertText } from '../alertText.js'

const DOT = { FREE: 'bg-emerald-500', OCCUPIED: 'bg-red-500', NEEDS_CLEANING: 'bg-amber-400' }

export default function StaffView({ state, alertsOn, onEnable }) {
  const { t } = useI18n()
  const { user } = useAuth()
  const enabled = alertsOn
  const [now, setNow] = useState(Date.now() / 1000)
  const [mine, setMine] = useState({})
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(i)
  }, [])

  const alerts = state?.alerts || []

  const active = alerts.filter((a) => !a.resolved)
  const enable = onEnable
  const onIt = async (a) => {
    setMine((m) => ({ ...m, [a.id]: user?.name }))
    try {
      await api(`/api/alerts/${a.id}/ack`, { method: 'POST', body: { name: user?.name } })
    } catch {
      /* optimistic */
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">{t('staff.title')}</h2>
        <button onClick={enable} disabled={enabled} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-sky-600 hover:bg-sky-500'}`}>
          <Icon id="bell" className="me-1.5 h-4 w-4" />{enabled ? t('staff.enabled') : t('staff.enable')}
        </button>
      </div>

      {active.length === 0 && (
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-5 py-10 text-center text-emerald-300"><Icon id="check" className="me-1.5 h-5 w-5" />{t('staff.none')}</div>
      )}

      {active.map((a) => {
        const k = ALERT_STYLE[a.kind] || ALERT_STYLE.service_wait
        const by = a.ack_by || mine[a.id]
        const isAcked = a.acked || mine[a.id]
        return (
          <div key={a.id} className={`rounded-2xl border p-4 ${k.tone}`}>
            <div className="flex items-center gap-2">
              <Icon id={k.icon} className="h-7 w-7" />
              <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${k.chip}`}>{t(`alerts.${a.kind}`)}</span>
              <span className="ms-auto text-xs text-slate-400">{ago(a.ts, now, t)}</span>
            </div>
            <p className="mt-3 text-base font-medium">{alertText(a, t)}</p>
            {isAcked ? (
              <p className="mt-3 rounded-lg bg-slate-800 px-3 py-3 text-center text-sm text-slate-300"><Icon id="check" className="me-1.5 h-4 w-4" />{by ? t('alerts.ackBy', { n: by }) : t('alerts.ack')}</p>
            ) : (
              <button onClick={() => onIt(a)} className="mt-3 w-full rounded-xl bg-sky-600 py-4 text-lg font-bold active:bg-sky-700">
                {t('staff.onIt')}
              </button>
            )}
          </div>
        )
      })}

      <div>
        <h3 className="mb-2 text-xs font-semibold tracking-[0.25em] text-slate-500">{t('staff.tables').toUpperCase()}</h3>
        <div className="grid grid-cols-3 gap-2">
          {(state?.tables || []).map((tb) => (
            <div key={tb.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-center">
              <div className="flex items-center justify-center gap-1.5 text-sm font-bold">
                <span className={`h-2.5 w-2.5 rounded-full ${DOT[tb.state]}`} />
                {tb.id}
              </div>
              <div className="mt-1 text-[11px] text-slate-400" dir="ltr">
                {tb.state === 'OCCUPIED' ? `${tb.guests} · ${tb.timer}` : tb.state === 'NEEDS_CLEANING' ? `${t('floor.dirty')} · ${tb.timer}` : '—'}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="pb-6 text-center text-[11px] text-slate-600">{t('staff.install')}</p>
    </div>
  )
}
