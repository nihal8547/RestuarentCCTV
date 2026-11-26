import React from 'react'
import { useI18n } from '../i18n.jsx'

function Stat({ label, value, sub, accent }) {
  return (
    <div className="min-w-[170px] flex-1 rounded-xl border border-slate-800 bg-slate-900/70 px-5 py-3">
      <div className="flex items-baseline gap-3">
        <span className="text-xs font-semibold tracking-[0.18em] text-slate-400">{label}</span>
        <span className={`text-3xl font-bold tabular-nums ${accent}`} dir="ltr">{value}</span>
      </div>
      {sub}
    </div>
  )
}

export default function OccupancyHeader({ state }) {
  const { t } = useI18n()
  const r = state?.restaurant
  const pct = r?.capacity_pct ?? 0
  const bar = pct >= 85 ? 'bg-red-500' : pct >= 55 ? 'bg-amber-400' : 'bg-emerald-400'
  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold tracking-[0.3em] text-slate-500">{t('occ.title')}</h2>
      <div className="flex flex-wrap gap-3">
        <Stat
          label={t('occ.capacity')}
          value={`${pct}%`}
          accent="text-white"
          sub={
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
              <div className={`h-full ${bar} transition-all duration-700`} style={{ width: `${pct}%` }} />
            </div>
          }
        />
        <Stat
          label={t('occ.tables')}
          value={`${r?.tables_occupied ?? 0}/${r?.tables_total ?? 0}`}
          accent="text-red-400"
          sub={<div className="mt-1 text-[11px] text-slate-500">{t('occ.needclean', { n: r?.needs_cleaning ?? 0 })}</div>}
        />
        <Stat
          label={t('occ.guests')}
          value={`${r?.seated_guests ?? 0}/${r?.seat_capacity ?? 0}`}
          accent="text-sky-300"
          sub={<div className="mt-1 text-[11px] text-slate-500">{t('occ.livecount')}</div>}
        />
      </div>
    </section>
  )
}
