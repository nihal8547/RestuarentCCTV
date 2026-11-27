import React, { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { api, withToken } from '../api.js'
import { useI18n } from '../i18n.jsx'

const W = 960
const H = 540
const PALETTE = ['#34d399', '#38bdf8', '#a78bfa', '#f472b6', '#fbbf24', '#fb7185', '#2dd4bf', '#818cf8']

export default function ZoneEditor({ cameras = [] }) {
  const { t } = useI18n()
  const [zones, setZones] = useState(null)
  const [sel, setSel] = useState(null)
  const [drawing, setDrawing] = useState(false)
  const [msg, setMsg] = useState('')
  const [cam, setCam] = useState(cameras[0]?.id || 'cam1')
  const [bg, setBg] = useState(0)
  const drag = useRef(null)
  const svg = useRef(null)

  useEffect(() => {
    api('/api/zones').then((z) => {
      setZones(z)
      setSel(z.tables[0]?.id || null)
    })
  }, [])

  if (!zones) return null
  const tables = zones.tables
  const cur = tables.find((x) => x.id === sel)
  const sections = [...new Set(['A', 'B', 'C', ...tables.map((x) => x.section)])].sort()

  const patch = (id, fn) => setZones((z) => ({ ...z, tables: z.tables.map((x) => (x.id === id ? fn(x) : x)) }))
  const toSvg = (e) => {
    const r = svg.current.getBoundingClientRect()
    return [Math.round(((e.clientX - r.left) / r.width) * W), Math.round(((e.clientY - r.top) / r.height) * H)]
  }

  const onCanvasClick = (e) => {
    if (!drawing || !cur) return
    const p = toSvg(e)
    patch(cur.id, (x) => ({ ...x, polygon: [...x.polygon, p] }))
  }
  const onMove = (e) => {
    if (!drag.current) return
    const [x, y] = toSvg(e)
    const { id, idx } = drag.current
    patch(id, (tb) => ({
      ...tb,
      polygon: tb.polygon.map((p, i) => (i === idx ? [Math.min(W, Math.max(0, x)), Math.min(H, Math.max(0, y))] : p)),
    }))
  }

  const addTable = () => {
    const nums = tables.map((x) => parseInt(x.id.replace(/\D/g, ''), 10) || 0)
    const n = Math.max(0, ...nums) + 1
    const id = `T${String(n).padStart(2, '0')}`
    setZones((z) => ({
      ...z,
      tables: [...z.tables, { id, number: n, seats: 4, section: 'A', shape: 'rect', camera: cam, polygon: [], table_bbox: null }],
    }))
    setSel(id)
    setDrawing(true)
  }
  const delTable = () => {
    setZones((z) => ({ ...z, tables: z.tables.filter((x) => x.id !== sel) }))
    setSel(tables.find((x) => x.id !== sel)?.id || null)
  }

  const save = async () => {
    const body = {
      ...zones,
      tables: tables.map((x) => {
        if (x.polygon.length < 3) return x
        const xs = x.polygon.map((p) => p[0])
        const ys = x.polygon.map((p) => p[1])
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2
        const bw = x.table_bbox ? x.table_bbox[2] - x.table_bbox[0] : 90
        const bh = x.table_bbox ? x.table_bbox[3] - x.table_bbox[1] : 70
        return { ...x, table_bbox: [Math.round(cx - bw / 2), Math.round(cy - bh / 2), Math.round(cx + bw / 2), Math.round(cy + bh / 2)] }
      }),
    }
    try {
      const z = await api('/api/zones', { method: 'PUT', body })
      setZones(z)
      setDrawing(false)
      setMsg(t('set.saved'))
    } catch (e) {
      setMsg(e.message)
    }
    setTimeout(() => setMsg(''), 5000)
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">{t('set.zonesHelp')}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {cameras.length > 1 &&
              cameras.map((c) => (
                <button key={c.id} onClick={() => { setCam(c.id); setBg((n) => n + 1) }} className={`rounded px-2 py-1 text-xs ${cam === c.id ? 'bg-slate-700' : 'bg-slate-800 hover:bg-slate-700'}`}>
                  {c.id}
                </button>
              ))}
            {drawing && <span className="rounded bg-sky-500/15 px-2 py-1 text-xs text-sky-300">{t('set.drawing')}</span>}
          </div>
          <div className="relative aspect-video overflow-hidden rounded-lg border border-slate-800 bg-black">
            <img src={withToken(`/api/snapshot.jpg?raw=1&cam=${cam}&n=${bg}`)} alt="" className="absolute inset-0 h-full w-full select-none object-contain" draggable={false} />
            <svg
              ref={svg}
              viewBox={`0 0 ${W} ${H}`}
              style={{ direction: 'ltr' }}
              className={`absolute inset-0 h-full w-full ${drawing ? 'cursor-crosshair' : ''}`}
              onClick={onCanvasClick}
              onPointerMove={onMove}
              onPointerUp={() => (drag.current = null)}
              onPointerLeave={() => (drag.current = null)}
            >
              {tables
                .filter((x) => (x.camera || cameras[0]?.id || 'cam1') === cam)
                .map((x, i) => {
                  const c = PALETTE[i % PALETTE.length]
                  const pts = x.polygon.map((p) => p.join(',')).join(' ')
                  return (
                    <g key={x.id} opacity={sel === x.id ? 1 : 0.6}>
                      {x.polygon.length >= 3 ? (
                        <polygon points={pts} fill={c} fillOpacity="0.18" stroke={c} strokeWidth={sel === x.id ? 3 : 2} onClick={(e) => { if (!drawing) { e.stopPropagation(); setSel(x.id) } }} />
                      ) : (
                        <polyline points={pts} fill="none" stroke={c} strokeWidth="2" />
                      )}
                      {x.polygon[0] && (
                        <text x={x.polygon[0][0] + 4} y={x.polygon[0][1] - 6} fill="#fff" fontSize="18" fontWeight="700" stroke="#000" strokeWidth="0.6">
                          {x.id}
                        </text>
                      )}
                      {sel === x.id &&
                        x.polygon.map((p, idx) => (
                          <circle
                            key={idx}
                            cx={p[0]}
                            cy={p[1]}
                            r="8"
                            fill="#fff"
                            stroke={c}
                            strokeWidth="3"
                            className="cursor-move"
                            onPointerDown={(e) => {
                              e.stopPropagation()
                              e.currentTarget.setPointerCapture?.(e.pointerId)
                              drag.current = { id: x.id, idx }
                            }}
                            onClick={(e) => e.stopPropagation()}
                          />
                        ))}
                    </g>
                  )
                })}
            </svg>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <button onClick={addTable} className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium hover:bg-emerald-500">+ {t('set.addTable')}</button>
            {cur && <button onClick={delTable} className="rounded-md bg-red-600/80 px-3 py-1.5 text-xs hover:bg-red-600">{t('set.delTable')}</button>}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {tables.map((x) => (
              <button key={x.id} onClick={() => { setSel(x.id); setDrawing(false) }} className={`rounded-md px-2.5 py-1 text-xs font-semibold ${sel === x.id ? 'bg-sky-600' : 'bg-slate-800 hover:bg-slate-700'}`}>
                {x.id}
                {x.polygon.length < 3 && <Icon id="pencil" className="ms-1 h-3 w-3" />}
              </button>
            ))}
          </div>
          {cur && (
            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs">
              <div className="flex gap-2">
                <button onClick={() => setDrawing((d) => !d)} className={`rounded px-2.5 py-1 ${drawing ? 'bg-sky-600' : 'bg-slate-800 hover:bg-slate-700'}`}><Icon id="pencil" className="me-1 h-3.5 w-3.5" />{t('set.drawing').split(':')[0]}</button>
                <button onClick={() => patch(cur.id, (x) => ({ ...x, polygon: x.polygon.slice(0, -1) }))} className="rounded bg-slate-800 px-2.5 py-1 hover:bg-slate-700">{t('set.undo')}</button>
                <button onClick={() => patch(cur.id, (x) => ({ ...x, polygon: [] }))} className="rounded bg-slate-800 px-2.5 py-1 hover:bg-slate-700">{t('set.clear')}</button>
              </div>
              <label className="block">
                <span className="text-slate-400">{t('set.seats')}</span>
                <input type="number" min="1" max="20" value={cur.seats} onChange={(e) => patch(cur.id, (x) => ({ ...x, seats: Number(e.target.value) }))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5" />
              </label>
              <label className="block">
                <span className="text-slate-400">{t('set.sectionCol')}</span>
                <select value={cur.section} onChange={(e) => patch(cur.id, (x) => ({ ...x, section: e.target.value }))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5">
                  {sections.map((s) => (<option key={s}>{s}</option>))}
                </select>
              </label>
              {cameras.length > 1 && (
                <label className="block">
                  <span className="text-slate-400">{t('set.camera')}</span>
                  <select value={cur.camera || cameras[0].id} onChange={(e) => patch(cur.id, (x) => ({ ...x, camera: e.target.value }))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5">
                    {cameras.map((c) => (<option key={c.id}>{c.id}</option>))}
                  </select>
                </label>
              )}
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={save} className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500">{t('set.saveZones')}</button>
            {msg && <span className="text-xs text-slate-300">{msg}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
