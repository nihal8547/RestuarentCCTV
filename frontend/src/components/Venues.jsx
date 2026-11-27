import React, { useEffect, useState } from 'react'
import Icon from './Icon.jsx'
import { api } from '../api.js'
import { ago } from '../alertText.js'
import { useI18n } from '../i18n.jsx'

const DOT = { FREE: 'bg-emerald-400', OCCUPIED: 'bg-red-500', NEEDS_CLEANING: 'bg-amber-400' }

export default function Venues() {
  const { t } = useI18n()
  const [venues, setVenues] = useState([])
  const [form, setForm] = useState({ name: '', city: '' })
  const [created, setCreated] = useState(null)
  const [err, setErr] = useState('')
  const [now, setNow] = useState(Date.now() / 1000)

  const load = () => api('/api/hub/venues').then(setVenues).catch((e) => setErr(e.message))
  useEffect(() => {
    load()
    const i = setInterval(() => {
      load()
      setNow(Date.now() / 1000)
    }, 5000)
    return () => clearInterval(i)
  }, [])

  const online = venues.filter((v) => v.online)
  const guests = online.reduce((n, v) => n + (v.summary?.restaurant?.seated_guests || 0), 0)
  const alerts = online.reduce((n, v) => n + (v.summary?.active_alerts?.length || 0), 0)

  const add = async () => {
    if (!form.name.trim()) return
    const r = await api('/api/hub/venues', { method: 'POST', body: form })
    setCreated(r)
    setForm({ name: '', city: '' })
    load()
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xs font-semibold tracking-[0.3em] text-slate-500">{t('ven.title')}</h2>
        <p className="mt-1 text-xs text-slate-500">{t('ven.sub')}</p>
        {err && <p className="mt-2 text-xs text-red-300">{err}</p>}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[[t('ven.online'), `${online.length}/${venues.length}`], [t('ven.guests'), guests], [t('ven.alerts'), alerts]].map(([l, v]) => (
          <div key={l} className="rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div className="text-[11px] font-semibold tracking-wider text-slate-500">{l}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{v}</div>
          </div>
        ))}
      </div>

      {venues.length === 0 && <p className="rounded-xl border border-dashed border-slate-700 py-10 text-center text-sm text-slate-500">{t('ven.empty')}</p>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {venues.map((v) => {
          const r = v.summary?.restaurant
          const camsDown = (v.summary?.cameras || []).filter((c) => !c.online).length
          return (
            <div key={v.id} className={`rounded-xl border bg-slate-900/70 p-4 ${v.online ? 'border-slate-800' : 'border-slate-800 opacity-60'}`}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold">{v.name}</h3>
                  <p className="text-xs text-slate-500">{v.city || '—'}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${v.online ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-700 text-slate-400'}`}>
                  {v.online ? t('ven.onlineChip') : t('ven.offline')}
                </span>
              </div>
              {r ? (
                <>
                  <div className="mt-3 flex items-end gap-5">
                    <div><div className="text-3xl font-bold tabular-nums">{r.capacity_pct}%</div><div className="text-[10px] text-slate-500">{t('occ.capacity')}</div></div>
                    <div dir="ltr"><div className="text-lg font-semibold">{r.tables_occupied}/{r.tables_total}</div><div className="text-[10px] text-slate-500">{t('occ.tables')}</div></div>
                    <div dir="ltr"><div className="text-lg font-semibold">{r.seated_guests}/{r.seat_capacity}</div><div className="text-[10px] text-slate-500">{t('occ.guests')}</div></div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {(v.summary.tables || []).map((tb) => (
                      <span key={tb.id} title={`${tb.id} ${tb.state} ${tb.timer}`} className={`h-3.5 w-3.5 rounded-sm ${DOT[tb.state] || 'bg-slate-600'}`} />
                    ))}
                  </div>
                  {(v.summary.active_alerts || []).slice(0, 2).map((a, i) => (
                    <p key={i} className="mt-2 truncate rounded bg-red-500/10 px-2 py-1 text-[11px] text-red-300" title={a.message}><Icon id="warn" className="me-1 h-3 w-3" />{a.message}</p>
                  ))}
                  {camsDown > 0 && <p className="mt-2 text-[11px] text-fuchsia-300"><Icon id="cameraOff" className="me-1 h-3 w-3" />{t('ven.camsDown', { n: camsDown })}</p>}
                </>
              ) : (
                <p className="mt-4 text-xs text-slate-500">{t('ven.never')}</p>
              )}
              <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
                <span>{v.last_seen ? t('ven.lastSeen', { t: ago(v.last_seen, now, t) }) : ''}</span>
                <button onClick={async () => { await api(`/api/hub/venues/${v.id}`, { method: 'DELETE' }); load() }} className="hover:text-red-300">{t('ven.del')}</button>
              </div>
            </div>
          )
        })}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <h3 className="mb-3 text-sm font-bold">{t('ven.add')}</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          <input placeholder={t('ven.name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          <input placeholder={t('ven.city')} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          <button onClick={add} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold hover:bg-emerald-500">{t('ven.add')}</button>
        </div>
        {created && (
          <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
            <p className="font-semibold text-amber-300">{t('ven.key')}</p>
            <p className="mt-1 text-slate-400">{t('ven.setup')}</p>
            <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-2 text-[11px] text-slate-200" dir="ltr">{`HUB_URL=${window.location.origin}\nHUB_KEY=${created.api_key}`}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
