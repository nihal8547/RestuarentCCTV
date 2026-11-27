import React, { useCallback, useEffect, useState } from 'react'
import Icon from './Icon.jsx'
import { api } from '../api.js'
import { useAuth, RANK } from '../AuthContext.jsx'
import { useI18n } from '../i18n.jsx'

const BADGE = {
  FREE: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  OCCUPIED: 'bg-red-500/15 text-red-300 border-red-500/40',
  NEEDS_CLEANING: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
}

export default function TableDrawer({ table, onClose }) {
  const { t: tr } = useI18n()
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const auth = useAuth()
  const isManager = (RANK[auth?.user?.role] ?? 0) >= RANK.manager

  const load = useCallback(() => {
    api(`/api/tables/${table.id}`).then(setDetail).catch(() => {})
  }, [table.id])
  useEffect(() => {
    load()
  }, [load, table.state, table.reserved])

  const act = async (action) => {
    setBusy(true)
    setErr('')
    try {
      await api(`/api/tables/${table.id}/action`, { method: 'POST', body: { action } })
      load()
    } catch (e) {
      setErr(tr('tbl.err', { m: e.message || 'error' }))
    } finally {
      setBusy(false)
    }
  }

  const ref = async (clear) => {
    setBusy(true)
    setErr('')
    try {
      await api(`/api/tables/${table.id}/reference`, { method: 'POST', body: { clear } })
      setErr(clear ? '' : tr('tbl.refOk'))
    } catch (e) {
      setErr(tr('tbl.err', { m: e.message || 'error' }))
    } finally {
      setBusy(false)
    }
  }

  const actions = []
  if (table.state === 'NEEDS_CLEANING') actions.push(['mark_clean', tr('tbl.markClean')])
  if (table.state === 'OCCUPIED') actions.push(['waiter_visit', tr('tbl.visit')])
  if (table.state === 'FREE') actions.push([table.reserved ? 'unreserve' : 'reserve', table.reserved ? tr('tbl.unreserve') : tr('tbl.reserve')])

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 sm:items-center" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-t-2xl border border-slate-700 bg-slate-900 p-5 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={tr('tbl.title', { id: table.id })}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">{tr('tbl.title', { id: table.id })}</h3>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-800" aria-label={tr('tbl.close')}>
            <Icon id="x" className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${BADGE[table.state]}`}>
            {tr('tbl.state.' + table.state)}
          </span>
          {table.reserved && (
            <span className="rounded-full border border-sky-500/40 bg-sky-500/15 px-3 py-0.5 text-xs font-semibold text-sky-300">
              {tr('tbl.reserved')}
            </span>
          )}
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          {[
            [tr('tbl.seats'), table.seats],
            [tr('tbl.section'), table.section],
            [tr('tbl.guests'), table.state === 'OCCUPIED' ? table.guests : '-'],
            [tr('tbl.timer'), table.state === 'FREE' ? '-' : table.timer],
            [tr('tbl.visits'), table.state === 'OCCUPIED' ? table.visits ?? 0 : '-'],
          ].map(([k, v]) => (
            <div key={k} className="rounded-lg bg-slate-950/70 px-3 py-2">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">{k}</dt>
              <dd className="font-mono" dir="ltr">{v}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">{tr('tbl.actions')}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {actions.length ? (
              actions.map(([a, label]) => (
                <button
                  key={a}
                  disabled={busy}
                  onClick={() => act(a)}
                  className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500 disabled:opacity-50"
                >
                  {label}
                </button>
              ))
            ) : (
              <span className="text-xs text-slate-500">{tr('tbl.none')}</span>
            )}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">{tr('tbl.hint')}</p>
          {err && <p className="mt-1 text-xs text-red-400">{err}</p>}
        </div>

        <div className="mt-4 rounded-lg bg-slate-950/70 p-3 text-xs">
          <div className="font-semibold uppercase tracking-widest text-slate-400">{tr('tbl.vision')}</div>
          <div className="mt-1 flex justify-between"><span>{tr('tbl.items')}</span><span className="font-mono" dir="ltr">{table.items ?? 0}</span></div>
          <div className="flex justify-between"><span>{tr('tbl.appear')}</span>
            <span className="font-mono" dir="ltr">{table.has_ref ? (table.appearance ?? '…') : tr('tbl.noref')}</span></div>
          {isManager && (
            <div className="mt-2 flex flex-wrap gap-2">
              <button disabled={busy} onClick={() => ref(false)} className="rounded-md border border-slate-600 px-2 py-1 hover:bg-slate-800">{tr('tbl.setRef')}</button>
              {table.has_ref && <button disabled={busy} onClick={() => ref(true)} className="rounded-md border border-slate-600 px-2 py-1 hover:bg-slate-800">{tr('tbl.clearRef')}</button>}
            </div>
          )}
          {isManager && <p className="mt-1 text-[10px] text-slate-500">{tr('tbl.refHint')}</p>}
        </div>

        <div className="mt-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">{tr('tbl.recent')}</div>
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs">
            {detail?.events?.length ? (
              detail.events.slice(0, 8).map((e) => (
                <li key={e.id} className="flex justify-between rounded bg-slate-950/60 px-2 py-1">
                  <span>{tr('ev.' + e.type) === 'ev.' + e.type ? e.type : tr('ev.' + e.type)}</span>
                  <span className="font-mono text-slate-500" dir="ltr">
                    {new Date(e.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </li>
              ))
            ) : (
              <li className="text-slate-500">{tr('tbl.noact')}</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}
