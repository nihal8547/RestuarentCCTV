import React from 'react'
import { useI18n } from '../i18n.jsx'
import TableDrawer from './TableDrawer.jsx'

const COLORS = {
  FREE: { fill: '#052e1c', stroke: '#34d399', text: '#6ee7b7', chair: '#34d399' },
  OCCUPIED: { fill: '#3b0d12', stroke: '#f87171', text: '#fca5a5', chair: '#f87171' },
  NEEDS_CLEANING: { fill: '#3a2504', stroke: '#fbbf24', text: '#fcd34d', chair: '#fbbf24' },
}
const SEAT = [[-55, -48], [55, -48], [-55, 48], [55, 48]]
const SEC_TINT = { A: '#d4d4d8', B: '#a1a1aa', C: '#71717a' }   // greyscale sections

function Table({ t, tr, onPick }) {
  const c = t.camera_online === false ? { fill: '#1e293b', stroke: '#64748b', text: '#94a3b8', chair: '#64748b' } : COLORS[t.state]
  const [x1, y1, x2, y2] = t.bbox
  const cx = (x1 + x2) / 2
  const cy = (y1 + y2) / 2
  const w = x2 - x1
  const h = y2 - y1
  const alert = t.wait_alert || t.clean_alert
  return (
    <g onClick={() => onPick(t.id)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}
       onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onPick(t.id)}>
      {SEAT.slice(0, t.seats).map(([dx, dy], i) => (
        <rect
          key={i}
          x={cx + dx - 11}
          y={cy + dy - 11}
          width="22"
          height="22"
          rx="6"
          fill={t.state === 'OCCUPIED' && i < t.guests ? c.chair : 'transparent'}
          stroke={c.chair}
          strokeWidth="2"
          opacity={t.state === 'OCCUPIED' && i < t.guests ? 1 : 0.5}
        />
      ))}
      <rect
        x={x1}
        y={y1}
        width={w}
        height={h}
        rx={t.shape === 'round' ? h / 2 : 12}
        fill={c.fill}
        stroke={c.stroke}
        strokeWidth="3"
        className={alert ? 'pulse-soft' : ''}
      />
      <text x={cx} y={cy - 8} textAnchor="middle" fill="#fff" fontSize="20" fontWeight="700">
        {t.id}
      </text>
      <text x={cx} y={cy + 7} textAnchor="middle" fill={c.text} fontSize="12" fontWeight="700">
        {t.camera_online === false
          ? tr('set.offline')
          : t.state === 'FREE'
            ? tr('floor.free')
            : t.state === 'OCCUPIED'
              ? tr(t.guests === 1 ? 'floor.guest' : 'floor.guests', { n: t.guests })
              : tr('floor.dirty')}
      </text>
      {t.state !== 'FREE' && t.camera_online !== false && (
        <text x={cx} y={cy + 22} textAnchor="middle" fill="#fff" fontSize="12" className="font-mono">
          {t.timer}
        </text>
      )}
      {t.reserved && t.state === 'FREE' && (
        <text x={cx} y={cy + 22} textAnchor="middle" fill="#7dd3fc" fontSize="11" fontWeight="700">
          {tr('tbl.reserved')}
        </text>
      )}
      {alert && (
        <g transform={`translate(${x2 - 6}, ${y1 - 6})`}>
          <circle r="13" fill="#dc2626" />
          <text textAnchor="middle" y="6" fill="#fff" fontSize="18" fontWeight="800">!</text>
        </g>
      )}
    </g>
  )
}

export default function FloorPlan({ state }) {
  const { t: tr } = useI18n()
  const [picked, setPicked] = React.useState(null)
  const tables = state?.tables ?? []
  const sections = state?.sections ?? []
  const rec = state?.recommendation
  // section bands = bounding boxes of that section's zone rectangles
  const bands = sections.map((s) => {
    const zs = tables.filter((t) => t.section === s.id).map((t) => t.zone)
    return {
      ...s,
      x1: Math.min(...zs.map((z) => z[0])) - 10,
      y1: Math.min(...zs.map((z) => z[1])) - 10,
      x2: Math.max(...zs.map((z) => z[2])) + 10,
      y2: Math.max(...zs.map((z) => z[3])) + 10,
    }
  })

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70">
      <div className="border-b border-slate-800 px-4 py-3">
        <h3 className="text-sm font-bold tracking-[0.25em]">{tr('floor.title')}</h3>
        <p className="text-xs text-slate-400">{tr('floor.sub')}</p>
      </div>

      <div className="p-3">
        <svg viewBox="0 0 960 540" style={{ direction: 'ltr' }} className="w-full rounded-lg bg-slate-950">
          {bands.map((b) => (
            <g key={b.id}>
              <rect
                x={b.x1}
                y={b.y1}
                width={b.x2 - b.x1}
                height={b.y2 - b.y1}
                rx="18"
                fill={SEC_TINT[b.id] || '#64748b'}
                opacity={0.06 + (b.load_pct / 100) * 0.16}
                stroke={SEC_TINT[b.id] || '#64748b'}
                strokeOpacity="0.35"
                strokeDasharray="6 6"
              />
              <text x={b.x1 + 14} y={b.y1 + 22} fill={SEC_TINT[b.id] || '#94a3b8'} fontSize="15" fontWeight="700">
                {tr('floor.section', { id: b.id })} · {b.load_pct}%
              </text>
            </g>
          ))}
          {rec &&
            tables
              .filter((t) => t.id === rec.table)
              .map((t) => (
                <rect
                  key="rec"
                  x={t.zone[0] + 6}
                  y={t.zone[1] + 26}
                  width={t.zone[2] - t.zone[0] - 12}
                  height={t.zone[3] - t.zone[1] - 32}
                  rx="14"
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="2.5"
                  strokeDasharray="4 6"
                  className="pulse-soft"
                />
              ))}
          {tables.map((t) => (
            <Table key={t.id} t={t} tr={tr} onPick={setPicked} />
          ))}
        </svg>

        <p className="mt-2 text-center text-[11px] text-slate-500">{tr('tbl.click')}</p>

        <div className="mt-3 grid grid-cols-3 gap-2">
          {sections.map((s) => (
            <div key={s.id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold" style={{ color: SEC_TINT[s.id] }}>
                  {tr('floor.section', { id: s.id })}
                </span>
                <span className="text-slate-400" dir="ltr">
                  {s.guests}/{s.seats}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ width: `${s.load_pct}%`, background: SEC_TINT[s.id] }}
                />
              </div>
              <div className="mt-1 text-[10px] text-slate-500">
                {tr('floor.freeocc', { f: s.free_tables, o: s.occupied_tables })}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-300">
          {rec ? (
            <>
              <b>{tr('floor.next')}</b> {tr('floor.nextText', { t: rec.table, s: rec.section })}
            </>
          ) : (
            <>{tr('floor.nofree')}</>
          )}
        </div>
      </div>
      {picked && tables.find((x) => x.id === picked) && (
        <TableDrawer table={tables.find((x) => x.id === picked)} onClose={() => setPicked(null)} />
      )}
    </div>
  )
}
