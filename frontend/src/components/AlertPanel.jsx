import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import { useI18n } from '../i18n.jsx'
import { ALERT_STYLE, ago, alertText } from '../alertText.js'

export default function AlertPanel({ alerts = [] }) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [now, setNow] = useState(Date.now() / 1000)
  const [acked, setAcked] = useState({})
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(i)
  }, [])

  const active = alerts.filter((a) => !a.resolved).length
  const ack = async (id) => {
    setAcked((m) => ({ ...m, [id]: user?.name || true }))
    try {
      await api(`/api/alerts/${id}/ack`, { method: 'POST', body: { name: user?.name } })
    } catch {
      /* keep optimistic state */
    }
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <h3 className="text-sm font-bold tracking-[0.2em]">{t('alerts.title')}</h3>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${active ? 'bg-red-500/20 text-red-300' : 'bg-emerald-500/15 text-emerald-300'}`}>
          {active ? t('alerts.active', { n: active }) : t('alerts.clear')}
        </span>
      </div>
      <ul className="max-h-[300px] divide-y divide-slate-800 overflow-y-auto">
        {alerts.length === 0 && <li className="px-4 py-8 text-center text-sm text-slate-500">{t('alerts.empty')}</li>}
        {alerts.map((a) => {
          const k = ALERT_STYLE[a.kind] || ALERT_STYLE.service_wait
          const by = a.ack_by || (typeof acked[a.id] === 'string' ? acked[a.id] : null)
          const isAcked = a.acked || acked[a.id]
          return (
            <li key={a.id} className={`flex items-start gap-3 px-4 py-3 ${a.resolved ? 'opacity-50' : ''}`}>
              <div className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border ${k.tone}`}>{k.icon}</div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${k.chip}`}>{t(`alerts.${a.kind}`)}</span>
                  <span className="text-xs font-semibold text-slate-300">{a.table}</span>
                  {!a.resolved && <span className="h-2 w-2 rounded-full bg-red-500 pulse-soft" />}
                  <span className="ms-auto text-[11px] text-slate-500">{ago(a.ts, now, t)}</span>
                </div>
                <p className="mt-1 text-sm text-slate-200">{alertText(a, t)}</p>
                <div className="mt-1.5 flex items-center gap-3 text-[11px]">
                  <span className={a.resolved ? 'text-emerald-400' : 'text-red-300'}>{a.resolved ? t('alerts.resolved') : t('alerts.needsAction')}</span>
                  {!a.resolved && !isAcked && (
                    <button onClick={() => ack(a.id)} className="rounded bg-slate-800 px-2 py-0.5 text-slate-300 hover:bg-slate-700">
                      {t('alerts.ack')}
                    </button>
                  )}
                  {!a.resolved && isAcked && <span className="text-slate-400">{by ? t('alerts.ackBy', { n: by }) : t('alerts.ack') + ' ✓'}</span>}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
