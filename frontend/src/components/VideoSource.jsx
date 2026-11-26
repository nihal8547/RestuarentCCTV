import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, withToken } from '../api.js'

const inp = 'rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm'
const btn = 'rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-semibold hover:bg-sky-500 disabled:opacity-40'
const btn2 = 'rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-40'

/** Click a waiter's shirt in the camera frame -> uniform colour range, applied live. */
function UniformCalibrator({ cam }) {
  const [res, setRes] = useState(null)
  const [status, setStatus] = useState(null)
  const [msg, setMsg] = useState('')
  const [tick, setTick] = useState(0)
  const img = useRef()
  const load = useCallback(() => api('/api/calibrate/status').then(setStatus).catch(() => {}), [])
  useEffect(() => { load() }, [load])
  const click = async (e) => {
    const r = img.current.getBoundingClientRect()
    const x = Math.round(((e.clientX - r.left) / r.width) * img.current.naturalWidth)
    const y = Math.round(((e.clientY - r.top) / r.height) * img.current.naturalHeight)
    try { setRes(await api(`/api/calibrate/uniform?x=${x}&y=${y}&cam=${cam}`)); setMsg('') } catch (er) { setMsg('Error: ' + er.message) }
  }
  const apply = async () => { await api('/api/calibrate/uniform', { method: 'POST', body: { low: res.low_list, high: res.high_list } }); setMsg('Applied live - staff in this colour are now recognised.'); load() }
  const clear = async () => { await api('/api/calibrate/uniform', { method: 'POST', body: { clear: true } }); setRes(null); setMsg('Colour cue turned off.'); load() }
  const hsv2css = (h, s, v) => `hsl(${h * 2}, ${Math.round((s / 255) * 100)}%, ${Math.round((v / 255) * 50)}%)`
  return (
    <div className="rounded-lg bg-slate-950/70 p-3">
      <div className="font-semibold">Staff uniform colour</div>
      <p className="text-xs text-slate-400">
        Status: {status?.enabled ? <span className="text-emerald-300">ON ({status.low?.join(',')} → {status.high?.join(',')})</span> : <span className="text-amber-300">OFF - staff are then recognised by behaviour only</span>}.
        Click on a waiter's shirt in the picture, then Apply.
      </p>
      <img ref={img} key={tick} src={withToken(`/api/snapshot.jpg?raw=1&cam=${cam}&t=${tick}`)} onClick={click} alt="camera frame" className="mt-2 w-full max-w-xl cursor-crosshair rounded-lg border border-slate-700" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button className={btn2} onClick={() => setTick(tick + 1)}>Refresh frame</button>
        {res && <><span className="inline-block h-5 w-5 rounded border border-slate-500" style={{ background: hsv2css(...res.low_list.map((v, i) => Math.round((v + res.high_list[i]) / 2))) }} />
          <code className="text-xs">{res.low} → {res.high}</code><button className={btn} onClick={apply}>Apply</button></>}
        {status?.enabled && <button className={btn2} onClick={clear}>Turn colour cue off</button>}
      </div>
      {msg && <p className="mt-1 text-xs text-sky-300">{msg}</p>}
    </div>
  )
}

/** Owner tool: switch a camera between the simulator, an uploaded video file and a live RTSP stream - no restart. */
export default function VideoSource() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [rtsp, setRtsp] = useState('')
  const [cam, setCam] = useState('')
  const [pick, setPick] = useState('')
  const file = useRef()
  const load = useCallback(() => api('/api/source').then((r) => { setD(r); setCam((c) => c || r.cameras[0]?.id || '') }).catch(() => {}), [])
  useEffect(() => { load() }, [load])
  if (!d) return null

  const run = async (fn, ok) => {
    setBusy(true); setMsg('')
    try { await fn(); setMsg(ok) } catch (e) { setMsg('Error: ' + e.message) }
    setBusy(false); load()
  }
  const setSrc = (source) => run(() => api('/api/source', { method: 'POST', body: { cam, source } }), 'Source switched - the camera restarted with the new source.')
  const upload = () => {
    const f = file.current?.files?.[0]
    if (!f) return setMsg('Choose a video file first')
    const fd = new FormData(); fd.append('file', f); fd.append('cam', cam); fd.append('use_now', 'true')
    return run(() => api('/api/source/upload', { method: 'POST', body: fd }), 'Video uploaded and playing in a loop on the camera.')
  }
  const cur = d.cameras.find((c) => c.id === cam)
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <select value={cam} onChange={(e) => setCam(e.target.value)} className={inp}>{d.cameras.map((c) => <option key={c.id}>{c.id}</option>)}</select>
        <span className="text-xs text-slate-400">now: <code>{cur?.source}</code> {cur?.sim ? '(simulator)' : ''}</span>
      </div>
      <div className="rounded-lg bg-slate-950/70 p-3">
        <div className="font-semibold">Test with a real video file</div>
        <p className="text-xs text-slate-400">Upload an MP4 of your restaurant (CCTV export or phone video). It plays in a loop through the real AI (YOLO). Then draw the table zones on it (Table zones below).</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input ref={file} type="file" accept="video/*" className="text-xs" />
          <button className={btn} disabled={busy} onClick={upload}>Upload &amp; use</button>
        </div>
        {d.videos.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <select value={pick} onChange={(e) => setPick(e.target.value)} className={inp}><option value="">previously uploaded…</option>{d.videos.map((v) => <option key={v}>{v}</option>)}</select>
            <button className={btn2} disabled={!pick || busy} onClick={() => setSrc('video:' + pick)}>Use this video</button>
          </div>
        )}
      </div>
      <div className="rounded-lg bg-slate-950/70 p-3">
        <div className="font-semibold">Live CCTV (RTSP)</div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input value={rtsp} onChange={(e) => setRtsp(e.target.value)} placeholder="rtsp://user:pass@192.168.1.64:554/Streaming/Channels/102" className={inp + ' w-full max-w-md'} />
          <button className={btn} disabled={!rtsp || busy} onClick={() => setSrc(rtsp.trim())}>Connect</button>
        </div>
      </div>
      {cam && <UniformCalibrator cam={cam} />}
      <div className="flex flex-wrap items-center gap-2">
        <button className={btn2} disabled={busy} onClick={() => setSrc('sim')}>Back to simulator</button>
        <button className={btn2} disabled={busy} onClick={() => { if (confirm('Delete the demo history (fake weekly data) from the database?')) run(() => api('/api/data/purge-demo', { method: 'POST' }), 'Demo history removed - analytics now show real data only.') }}>Remove demo history</button>
      </div>
      {msg && <p className="text-xs text-sky-300">{msg}</p>}
    </div>
  )
}
