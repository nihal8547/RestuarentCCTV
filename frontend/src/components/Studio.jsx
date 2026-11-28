import React, { useCallback, useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, withToken } from '../api.js'

const CLASSES = ['customer', 'staff', 'table_clean', 'table_dirty']
const COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fb923c']
const card = 'rounded-xl border border-slate-800 bg-slate-900/70 p-4'
const btn = 'rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-semibold hover:bg-sky-500 disabled:opacity-40'
const btn2 = 'rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-40'
const inp = 'rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm'

function useOverview() {
  const [ov, setOv] = useState(null)
  const reload = useCallback(() => api('/api/studio/overview').then(setOv).catch(() => {}), [])
  useEffect(() => {
    reload()
    const t = setInterval(reload, 3000)
    return () => clearInterval(t)
  }, [reload])
  return [ov, reload]
}

/* ---------------------------------------------------------------- Dataset */
function Dataset({ ov, reload }) {
  const [every, setEvery] = useState(2)
  const [max, setMax] = useState(300)
  const [count, setCount] = useState(60)
  const [interval, setIntervalSec] = useState(10)
  const [cam, setCam] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const file = useRef()
  const st = ov.stats
  const running = ov.jobs.some((j) => j.status === 'running')

  const upload = async () => {
    const f = file.current?.files?.[0]
    if (!f) return setMsg('Choose a video file first')
    const fd = new FormData()
    fd.append('file', f)
    fd.append('every', every)
    fd.append('max_frames', max)
    setBusy(true)
    setMsg(`Uploading ${(f.size / 1e6).toFixed(0)} MB…`)
    try {
      await api('/api/studio/upload', { method: 'POST', body: fd })
      setMsg('Uploaded - extracting frames (see jobs below)')
    } catch (e) {
      setMsg('Upload failed: ' + e.message)
    }
    setBusy(false)
    reload()
  }
  const post = async (path, body, ok) => {
    try {
      await api(path, { method: 'POST', body })
      setMsg(ok)
    } catch (e) {
      setMsg('Error: ' + e.message)
    }
    reload()
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={card}>
        <h3 className="font-bold">1 · Add footage</h3>
        <p className="mt-1 text-xs text-slate-400">
          Best: 2-3 days of your own CCTV (lunch + dinner, empty + busy, day + night). Frames are de-duplicated automatically.
        </p>
        <div className="mt-3 space-y-3 text-sm">
          <div>
            <div className="font-semibold">Upload a video file</div>
            <input ref={file} type="file" accept="video/*" className="mt-1 block w-full text-xs" />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label className="text-xs">1 frame every <input type="number" min="0.5" step="0.5" value={every} onChange={(e) => setEvery(+e.target.value)} className={inp + ' w-16'} /> s</label>
              <label className="text-xs">max <input type="number" min="10" value={max} onChange={(e) => setMax(+e.target.value)} className={inp + ' w-20'} /> frames</label>
              <button className={btn} disabled={busy} onClick={upload}>Upload &amp; extract</button>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-3">
            <div className="font-semibold">Capture from the live camera</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select value={cam} onChange={(e) => setCam(e.target.value)} className={inp}>
                <option value="">default camera</option>
                {ov.cameras.map((c) => <option key={c.id}>{c.id}</option>)}
              </select>
              <button className={btn2} onClick={() => post('/api/studio/capture', { cam: cam || undefined }, 'Frame captured')}>Capture now</button>
              <span className="text-xs text-slate-400">or</span>
              <input type="number" min="2" value={count} onChange={(e) => setCount(+e.target.value)} className={inp + ' w-16'} />
              <span className="text-xs">frames, every</span>
              <input type="number" min="1" value={interval} onChange={(e) => setIntervalSec(+e.target.value)} className={inp + ' w-16'} />
              <span className="text-xs">s</span>
              <button className={btn2} onClick={() => post('/api/studio/capture', { cam: cam || undefined, count, interval }, 'Capturing series…')}>Start series</button>
            </div>
            {ov.mode === 'sim' && <p className="mt-1 text-[11px] text-amber-300">Simulator mode: frames are labelled automatically (ground truth) - use this to try the whole workflow without footage.</p>}
          </div>
        </div>
        {msg && <p className="mt-3 text-xs text-sky-300">{msg}</p>}
      </div>

      <div className={card}>
        <h3 className="font-bold">2 · Dataset status</h3>
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-lg bg-slate-950/70 p-2"><div className="text-[11px] text-slate-500">IMAGES</div><div className="font-mono text-lg">{st.images}</div></div>
          <div className="rounded-lg bg-slate-950/70 p-2"><div className="text-[11px] text-slate-500">LABELLED</div><div className="font-mono text-lg">{st.labeled}</div></div>
          {CLASSES.map((c, i) => (
            <div key={c} className="flex items-center justify-between rounded-lg bg-slate-950/70 px-2 py-1 text-xs">
              <span style={{ color: COLORS[i] }}>{c}</span><span className="font-mono">{st.boxes[c]}</span>
            </div>
          ))}
        </div>
        {st.warnings.map((w) => <p key={w} className="mt-2 text-xs text-amber-300"><Icon id="warn" className="me-1 h-3.5 w-3.5" />{w}</p>)}
        <div className="mt-3 flex flex-wrap gap-2">
          <button className={btn} disabled={!ov.yolo.installed || running || !st.images} onClick={() => post('/api/studio/autolabel', { only_unlabeled: true }, 'Auto-labelling started')}>
            Auto-label unlabelled images
          </button>
          <a className={btn2} href={withToken('/api/studio/export')}>Export dataset (.zip)</a>
        </div>
        <p className="mt-1 text-[11px] text-slate-500">
          Auto-label uses the current model to pre-draw people (staff by uniform colour) and one box per table zone
          (clean, or dirty if cups/plates are seen). You then fix mistakes in the <b>Label</b> tab - much faster than drawing from scratch.
          Export gives you YOLO-format data to train on a GPU PC / Colab.
        </p>
        <div className="mt-3 space-y-1">
          {ov.jobs.map((j) => (
            <div key={j.id} className="rounded bg-slate-950/70 px-2 py-1 text-xs">
              <div className="flex justify-between"><span>{j.kind}</span><span className={j.status === 'failed' ? 'text-red-400' : j.status === 'done' ? 'text-emerald-400' : 'text-sky-300'}>{j.status}</span></div>
              <div className="h-1 overflow-hidden rounded bg-slate-800"><div className="h-full bg-sky-500" style={{ width: `${j.total ? Math.min(100, (100 * j.done) / j.total) : j.status === 'done' ? 100 : 5}%` }} /></div>
              {j.message && <div className="text-slate-400">{j.message}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- Annotator */
function Annotator({ ov, reload }) {
  const [filter, setFilter] = useState('unlabeled')
  const [list, setList] = useState({ total: 0, items: [] })
  const [idx, setIdx] = useState(0)
  const [img, setImg] = useState(null) // {name,width,height,boxes}
  const [boxes, setBoxes] = useState([])
  const [sel, setSel] = useState(-1)
  const [cls, setCls] = useState(0)
  const [drag, setDrag] = useState(null)
  const [dirty, setDirty] = useState(false)
  const svg = useRef()

  const loadList = useCallback(() => api(`/api/studio/images?filter=${filter}&limit=500`).then((r) => { setList(r); return r }), [filter])
  useEffect(() => { loadList(); setIdx(0) }, [loadList])
  const cur = list.items[idx]
  useEffect(() => {
    if (!cur) { setImg(null); setBoxes([]); return }
    api(`/api/studio/labels/${cur.name}`).then((r) => { setImg(r); setBoxes(r.boxes); setSel(-1); setDirty(false) }).catch(() => {})
  }, [cur?.name])

  const save = useCallback(async () => {
    if (!cur) return
    await api(`/api/studio/labels/${cur.name}`, { method: 'PUT', body: { boxes } })
    setDirty(false)
    reload()
  }, [cur, boxes, reload])
  const go = async (d) => {
    if (dirty) await save()
    const n = idx + d
    if (n >= 0 && n < list.items.length) setIdx(n)
    else if (filter === 'unlabeled') { const r = await loadList(); setIdx(Math.min(idx, Math.max(0, r.items.length - 1))) }
  }
  const pt = (e) => {
    const s = svg.current
    const p = s.createSVGPoint()
    p.x = e.clientX; p.y = e.clientY
    const q = p.matrixTransform(s.getScreenCTM().inverse())
    return [Math.max(0, Math.min(img.width, q.x)), Math.max(0, Math.min(img.height, q.y))]
  }
  const down = (e) => { if (e.target === svg.current || e.target.tagName === 'image') { setSel(-1); setDrag({ s: pt(e), e: pt(e) }) } }
  const move = (e) => drag && setDrag({ ...drag, e: pt(e) })
  const up = () => {
    if (!drag) return
    const [x1, y1] = drag.s, [x2, y2] = drag.e
    if (Math.abs(x2 - x1) > 8 && Math.abs(y2 - y1) > 8) {
      setBoxes([...boxes, { cls, x1: Math.min(x1, x2), y1: Math.min(y1, y2), x2: Math.max(x1, x2), y2: Math.max(y1, y2) }])
      setSel(boxes.length); setDirty(true)
    }
    setDrag(null)
  }
  useEffect(() => {
    const h = (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return
      if (e.key >= '1' && e.key <= '4') {
        const c = +e.key - 1
        if (sel >= 0) { setBoxes((b) => b.map((x, i) => (i === sel ? { ...x, cls: c } : x))); setDirty(true) }
        setCls(c)
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (sel >= 0) { setBoxes((b) => b.filter((_, i) => i !== sel)); setSel(-1); setDirty(true) }
      } else if (e.key === 'ArrowRight' || e.key === 'd') go(1)
      else if (e.key === 'ArrowLeft' || e.key === 'a') go(-1)
      else if (e.key === 's' || e.key === 'Enter') save()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  })

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <div className={card + ' xl:col-span-9'}>
        <div className="flex flex-wrap items-center gap-2">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className={inp}>
            <option value="unlabeled">Unlabelled</option><option value="labeled">Labelled</option><option value="all">All</option>
          </select>
          <span className="text-xs text-slate-400">{list.total ? `${idx + 1} / ${list.items.length} (${list.total} total)` : 'no images'}</span>
          <div className="ml-auto flex flex-wrap gap-1">
            {CLASSES.map((c, i) => (
              <button key={c} onClick={() => { setCls(i); if (sel >= 0) { setBoxes((b) => b.map((x, k) => (k === sel ? { ...x, cls: i } : x))); setDirty(true) } }}
                className={`rounded-md border px-2 py-1 text-xs ${cls === i ? 'bg-slate-700' : ''}`} style={{ borderColor: COLORS[i], color: COLORS[i] }}>
                {i + 1} · {c}
              </button>
            ))}
          </div>
        </div>
        {img ? (
          <svg ref={svg} viewBox={`0 0 ${img.width} ${img.height}`} className="mt-3 w-full cursor-crosshair select-none rounded-lg bg-black"
            style={{ direction: 'ltr' }} onPointerDown={down} onPointerMove={move} onPointerUp={up}>
            <image href={withToken(`/api/studio/image/${img.name}`)} width={img.width} height={img.height} />
            {boxes.map((b, i) => (
              <g key={i} onPointerDown={(e) => { e.stopPropagation(); setSel(i) }} style={{ cursor: 'pointer' }}>
                <rect x={b.x1} y={b.y1} width={b.x2 - b.x1} height={b.y2 - b.y1} fill={COLORS[b.cls]} fillOpacity={sel === i ? 0.25 : 0.08}
                  stroke={COLORS[b.cls]} strokeWidth={sel === i ? 3 : 1.5} />
                <text x={b.x1 + 3} y={b.y1 + 13} fill={COLORS[b.cls]} fontSize="12" fontWeight="700" style={{ paintOrder: 'stroke' }} stroke="#000" strokeWidth="3">{CLASSES[b.cls]}</text>
              </g>
            ))}
            {drag && <rect x={Math.min(drag.s[0], drag.e[0])} y={Math.min(drag.s[1], drag.e[1])} width={Math.abs(drag.e[0] - drag.s[0])} height={Math.abs(drag.e[1] - drag.s[1])} fill="none" stroke="#fff" strokeDasharray="4 3" />}
          </svg>
        ) : (
          <div className="mt-3 flex h-64 items-center justify-center rounded-lg bg-slate-950 text-sm text-slate-500">
            {filter === 'unlabeled' ? 'Nothing left to label - add footage or switch the filter.' : 'No images.'}
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <button className={btn2} onClick={() => go(-1)} disabled={idx === 0}>Prev</button>
          <button className={btn} onClick={save} disabled={!cur || !dirty}>Save</button>
          <button className={btn} onClick={() => go(1)} disabled={!cur}>Save &amp; next →</button>
          <button className={btn2} disabled={!cur || sel < 0} onClick={() => { setBoxes(boxes.filter((_, i) => i !== sel)); setSel(-1); setDirty(true) }}>Delete box</button>
          <button className={btn2} disabled={!cur} onClick={() => { setBoxes([]); setDirty(true) }}>Clear all</button>
          <button className={btn2 + ' ml-auto text-red-300'} disabled={!cur}
            onClick={async () => { if (confirm('Delete this image from the dataset?')) { await api(`/api/studio/image/${cur.name}`, { method: 'DELETE' }); const r = await loadList(); setIdx(Math.min(idx, Math.max(0, r.items.length - 1))); reload() } }}>
            Delete image
          </button>
        </div>
      </div>
      <div className={card + ' xl:col-span-3 text-xs text-slate-300'}>
        <h3 className="text-sm font-bold">How to label</h3>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li><b style={{ color: COLORS[0] }}>customer</b> - every seated/standing guest (box the whole person).</li>
          <li><b style={{ color: COLORS[1] }}>staff</b> - waiters / bussers.</li>
          <li><b style={{ color: COLORS[2] }}>table_clean</b> - box on the table top when it is empty/wiped.</li>
          <li><b style={{ color: COLORS[3] }}>table_dirty</b> - table with plates, glasses, napkins left.</li>
          <li>Drag on the image to draw. Click a box to select it, press <kbd>1-4</kbd> to change its class, <kbd>Del</kbd> to remove.</li>
          <li><kbd>←/→</kbd> prev/next (auto-saves), <kbd>S</kbd> save.</li>
          <li>An image with no boxes is saved as "nothing here" - that is useful too (empty restaurant).</li>
          <li>Be consistent: a table is <i>either</i> clean or dirty in a frame, never both.</li>
        </ul>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Train */
function Train({ ov }) {
  const [tr, setTr] = useState(null)
  const [form, setForm] = useState({ name: '', base: 'yolov8n.pt', epochs: 60, imgsz: 960, batch: 8, device: '' })
  const [err, setErr] = useState('')
  const [chk, setChk] = useState(null)
  useEffect(() => { api('/api/studio/check').then(setChk).catch(() => {}) }, [ov.stats.labeled])
  const load = useCallback(() => api('/api/studio/train').then(setTr).catch(() => {}), [])
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [load])
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'number' ? +e.target.value : e.target.value })
  const start = async () => {
    setErr('')
    try { setTr(await api('/api/studio/train', { method: 'POST', body: form })) } catch (e) { setErr(e.message) }
  }
  const running = tr?.status === 'running'
  const last = tr?.metrics?.[tr.metrics.length - 1]
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={card}>
        <h3 className="font-bold">Train a model</h3>
        <p className="mt-1 text-xs text-slate-400">
          Uses all labelled images ({ov.stats.labeled}). 80% train / 20% validation (whole time blocks are held out, so the accuracy score is honest). Training runs in the background; you can close this page.
          {ov.yolo.cuda ? ` GPU: ${ov.yolo.device_name}` : ' No GPU on this server - CPU training is slow; prefer exporting the dataset and training on a GPU PC / Colab, then import the .pt in the Models tab.'}
        </p>
        {chk && (chk.errors.length > 0 || chk.warnings.length > 0) && (
          <div className="mt-3 space-y-1 rounded-lg border border-slate-700 p-3 text-xs">
            <p className="font-semibold">Dataset check</p>
            {chk.errors.map((e) => <p key={e} className="text-red-300"><Icon id="x" className="me-1 h-3.5 w-3.5" />{e}</p>)}
            {chk.warnings.map((w) => <p key={w} className="text-amber-300"><Icon id="warn" className="me-1 h-3.5 w-3.5" />{w}</p>)}
          </div>
        )}
        {chk && chk.ok && chk.warnings.length === 0 && <p className="mt-3 text-xs text-emerald-300"><Icon id="check" className="me-1 h-3.5 w-3.5" />Dataset check passed: {chk.stats.boxes} boxes in {chk.stats.labeled} images.</p>}
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <label className="col-span-2 text-xs">Model name (optional)<input className={inp + ' mt-1 w-full'} value={form.name} onChange={set('name')} placeholder="auto: model-YYYYMMDD-HHMM" /></label>
          <label className="text-xs">Base model
            <select className={inp + ' mt-1 w-full'} value={form.base} onChange={set('base')}>
              <option value="yolov8n.pt">yolov8n (fast, CPU ok)</option><option value="yolov8s.pt">yolov8s (better, GPU)</option><option value="yolov8m.pt">yolov8m (best, strong GPU)</option>
            </select></label>
          <label className="text-xs">Epochs<input type="number" min="3" className={inp + ' mt-1 w-full'} value={form.epochs} onChange={set('epochs')} /></label>
          <label className="text-xs">Image size<select className={inp + ' mt-1 w-full'} value={form.imgsz} onChange={set('imgsz')}><option value={640}>640</option><option value={960}>960</option><option value={1280}>1280</option></select></label>
          <label className="text-xs">Batch<input type="number" min="1" className={inp + ' mt-1 w-full'} value={form.batch} onChange={set('batch')} /></label>
          <label className="text-xs">Device<select className={inp + ' mt-1 w-full'} value={form.device} onChange={set('device')}><option value="">auto</option><option value="cpu">cpu</option><option value="0">GPU 0</option></select></label>
        </div>
        <div className="mt-3 flex gap-2">
          <button className={btn} disabled={running || (chk && !chk.ok) || !ov.yolo.installed} onClick={start}>Start training</button>
          {running && <button className={btn2} onClick={() => api('/api/studio/train/cancel', { method: 'POST' }).then(load)}>Cancel</button>}
        </div>
        {!ov.yolo.installed && <p className="mt-2 text-xs text-amber-300">ultralytics is not installed here (build with INSTALL_YOLO=1). Export the dataset and train elsewhere.</p>}
        {err && <p className="mt-2 text-xs text-red-400">{err}</p>}
      </div>

      <div className={card}>
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Progress</h3>
          <span className={`rounded-full px-2 py-0.5 text-xs ${tr?.status === 'done' ? 'bg-emerald-500/20 text-emerald-300' : tr?.status === 'failed' ? 'bg-red-500/20 text-red-300' : 'bg-sky-500/20 text-sky-300'}`}>{tr?.status || 'idle'}</span>
        </div>
        {tr?.name && <p className="mt-1 text-xs text-slate-400">{tr.name} · {tr.base} · {tr.n_train} train / {tr.n_val} val images</p>}
        {tr?.epochs && <div className="mt-2 h-2 overflow-hidden rounded bg-slate-800"><div className="h-full bg-sky-500 transition-all" style={{ width: `${Math.min(100, ((last?.epoch || 0) / tr.epochs) * 100)}%` }} /></div>}
        {last && <p className="mt-1 text-xs">epoch {last.epoch}/{tr.epochs} · mAP50 <b>{last.map50}</b> · mAP50-95 {last.map5095}</p>}
        {tr?.metrics?.length > 0 && (
          <div className="mt-2 h-48">
            <ResponsiveContainer>
              <LineChart data={tr.metrics}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="epoch" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Legend />
                <Line type="monotone" dataKey="map50" stroke="#34d399" dot={false} name="mAP50" /><Line type="monotone" dataKey="box_loss" stroke="#f87171" dot={false} name="box loss" /></LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {tr?.log && <pre className="mt-2 max-h-40 overflow-auto rounded bg-black/60 p-2 text-[10px] leading-snug text-slate-400">{tr.log.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')}</pre>}
        {tr?.status === 'done' && <p className="mt-2 text-xs text-emerald-300">Done - go to the <b>Models</b> tab to review accuracy and activate it.</p>}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- Models */
function Models({ ov, reload }) {
  const [models, setModels] = useState([])
  const [msg, setMsg] = useState('')
  const [name, setName] = useState('')
  const file = useRef()
  const load = useCallback(() => api('/api/studio/models').then(setModels).catch(() => {}), [])
  useEffect(() => { load() }, [load, ov.active_model])
  const activate = async (n) => {
    setMsg('')
    const go = async (force) => { await api('/api/studio/models/activate', { method: 'POST', body: { name: n, force } }); setMsg(n ? `Activated ${n} - cameras reloaded the model.` : 'Back to the stock YOLO model.') }
    try { await go(false) } catch (e) {
      if (/force/i.test(e.message) && confirm(e.message.replace(/Use force.*/, '') + '\n\nActivate it anyway?')) { try { await go(true) } catch (e2) { setMsg('Error: ' + e2.message) } } else setMsg('Error: ' + e.message)
    }
    load(); reload()
  }
  const imp = async () => {
    const f = file.current?.files?.[0]
    if (!f || !name) return setMsg('Choose a .pt file and give it a name')
    const fd = new FormData(); fd.append('file', f); fd.append('name', name)
    try { await api('/api/studio/models/import', { method: 'POST', body: fd }); setMsg('Imported'); setName('') } catch (e) { setMsg('Error: ' + e.message) }
    load()
  }
  const gate = (m) => (m.map50 == null ? null : m.map50 >= 0.75 ? ['good', 'text-emerald-300'] : m.map50 >= 0.5 ? ['usable - monitor closely', 'text-amber-300'] : ['weak - label more data', 'text-red-300'])
  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h3 className="font-bold">Model in use</h3>
            <p className="text-xs text-slate-400">{ov.active_model ? <>studio model <b>{ov.active_model}</b></> : <>stock model (<code>{ov.model_in_use}</code>) - people only, uniform-colour staff</>}</p></div>
          {ov.active_model && <button className={btn2} onClick={() => activate(null)}>Roll back to stock</button>}
        </div>
        {msg && <p className="mt-2 text-xs text-sky-300">{msg}</p>}
        <p className="mt-2 text-[11px] text-slate-500">Activation hot-swaps the model on every camera without restarting. Watch the Live tab for a few minutes; if it behaves worse, roll back.</p>
      </div>
      {models.map((m) => (
        <div key={m.name} className={card}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-bold">{m.name} {m.active && <span className="ml-2 rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300">ACTIVE</span>}</div>
            <div className="flex gap-2">
              {!m.active && <button className={btn} disabled={!m.usable} onClick={() => activate(m.name)}>Activate</button>}
              {!m.active && <button className={btn2 + ' text-red-300'} onClick={async () => { if (confirm(`Delete model ${m.name}?`)) { await api(`/api/studio/models/${m.name}`, { method: 'DELETE' }); load() } }}>Delete</button>}
            </div>
          </div>
          <div className="mt-1 text-xs text-slate-400">{m.source} · {new Date(m.created * 1000).toLocaleString()} {m.base && `· base ${m.base} · ${m.epochs} epochs · ${m.labeled} images`}</div>
          {m.map50 != null && (
            <div className="mt-2 text-xs">mAP50 <b>{m.map50}</b> · mAP50-95 {m.map5095} <span className={gate(m)[1]}>({gate(m)[0]})</span>
              {m.best_conf != null && <span className="ms-2 text-slate-400">live threshold {m.best_conf} (best F1 {m.best_f1}) · held out: {m.n_val} images</span>}
              <div className="mt-1 flex flex-wrap gap-2">{Object.entries(m.per_class_ap50 || {}).map(([k, v]) => <span key={k} className="rounded bg-slate-950/70 px-2 py-0.5 font-mono">{k} AP {v}{m.per_class_precision?.[k] != null ? ` · P ${m.per_class_precision[k]} R ${m.per_class_recall?.[k]}` : ''}</span>)}</div></div>
          )}
          <div className="mt-1 text-[11px] text-slate-500">classes: {(m.classes || []).join(', ')}{!m.usable && ' - NOT usable (needs customer/staff/table_* names)'}</div>
        </div>
      ))}
      {!models.length && <div className={card + ' text-sm text-slate-400'}>No trained or imported models yet.</div>}
      <div className={card}>
        <h3 className="font-bold">Import a model trained elsewhere (.pt)</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <input ref={file} type="file" accept=".pt" className="text-xs" />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="model name" className={inp} />
          <button className={btn2} onClick={imp}>Import</button>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- Main */
export default function Studio() {
  const [ov, reload] = useOverview()
  const [tab, setTab] = useState('dataset')
  if (!ov) return <div className="p-6 text-slate-400">Loading…</div>
  const tabs = [['dataset', '1 · Dataset'], ['label', '2 · Label'], ['train', '3 · Train'], ['models', '4 · Models']]
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">Model Studio</h2>
          <p className="text-xs text-slate-400">Teach the AI your restaurant: footage → labels → training → activate. Owner only.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px] text-slate-400">
          <span className="rounded-full border border-slate-700 px-2 py-0.5">YOLO {ov.yolo.installed ? `v${ov.yolo.version}` : 'not installed'}</span>
          <span className="rounded-full border border-slate-700 px-2 py-0.5">{ov.yolo.cuda ? `GPU ${ov.yolo.device_name}` : 'CPU'}</span>
          {ov.cameras.map((c) => c.detect_ms > 0 && <span key={c.id} className="rounded-full border border-slate-700 px-2 py-0.5">{c.id}: {c.detect_ms} ms/frame</span>)}
        </div>
      </div>
      <div className="flex gap-1 rounded-lg bg-slate-900 p-1 text-sm">
        {tabs.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} className={`rounded-md px-3 py-1.5 ${tab === id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}>{label}</button>
        ))}
      </div>
      {tab === 'dataset' && <Dataset ov={ov} reload={reload} />}
      {tab === 'label' && <Annotator ov={ov} reload={reload} />}
      {tab === 'train' && <Train ov={ov} />}
      {tab === 'models' && <Models ov={ov} reload={reload} />}
    </div>
  )
}
