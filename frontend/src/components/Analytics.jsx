import React, { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import Icon from './Icon.jsx'
import { api } from '../api.js'
import { useI18n } from '../i18n.jsx'

const tip = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }

function Kpi({ label, value, unit }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3">
      <div className="text-[11px] font-semibold tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">
        {value}
        {unit && <span className="ms-1 text-sm font-medium text-slate-400">{unit}</span>}
      </div>
    </div>
  )
}

function Card({ title, sub, children, right }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold tracking-wide">{title}</h3>
          {sub && <p className="mb-3 text-xs text-slate-500">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </div>
  )
}

function Heatmap({ data }) {
  const hours = data.hours.filter((h) => h >= 10)
  const max = Math.max(1, ...data.rows.flatMap((r) => hours.map((h) => r.values[h])))
  return (
    <div className="overflow-x-auto" dir="ltr">
      <table className="w-full border-separate border-spacing-1 text-[10px]">
        <thead>
          <tr>
            <th />
            {hours.map((h) => (
              <th key={h} className="font-medium text-slate-500">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.date}>
              <td className="whitespace-nowrap pr-2 text-right text-slate-400">{r.label}</td>
              {hours.map((h) => {
                const v = r.values[h]
                return (
                  <td
                    key={h}
                    title={`${r.label} ${h}:00 - ${v}`}
                    className="h-6 min-w-[22px] rounded text-center text-slate-100"
                    style={{ background: v ? `rgba(56,189,248,${0.12 + 0.88 * (v / max)})` : '#0f172a' }}
                  >
                    {v || ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ServiceTable({ rows, keyName, label, t }) {
  const hot = (n) => (n > 0 ? 'text-amber-300' : 'text-slate-400')
  return (
    <table className="w-full text-sm">
      <thead className="text-start text-[11px] text-slate-500">
        <tr>
          <th className="py-1 text-start">{label}</th>
          <th className="text-start">{t('an.firstCol')}</th>
          <th className="text-start">{t('an.cleanCol')}</th>
          <th className="text-start">{t('an.svcCol')}</th>
          <th className="text-start">{t('an.clnCol')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[keyName]} className="border-t border-slate-800">
            <td className="py-1.5 font-semibold">{r[keyName]}</td>
            <td>{r.avg_first_visit_min}m</td>
            <td>{r.avg_clean_min}m</td>
            <td className={hot(r.service_alerts)}>{r.service_alerts}</td>
            <td className={hot(r.cleaning_alerts)}>{r.cleaning_alerts}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function Analytics() {
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    let alive = true
    const load = () =>
      api('/api/analytics/weekly')
        .then((d) => alive && (setData(d), setErr(false)))
        .catch(() => alive && setErr(true))
    load()
    const i = setInterval(load, 60000)
    return () => {
      alive = false
      clearInterval(i)
    }
  }, [])

  const downloadPdf = async () => {
    const res = await api('/api/reports/weekly.pdf', { raw: true })
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = `weekly-report-${data?.range?.to || ''}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  }
  const sendNow = async () => {
    try {
      await api('/api/reports/send', { method: 'POST' })
      setMsg(t('an.sent'))
    } catch {
      setMsg(t('an.sendFail'))
    }
    setTimeout(() => setMsg(''), 6000)
  }

  if (err) return <p className="py-20 text-center text-slate-400">{t('an.error')}</p>
  if (!data) return <p className="py-20 text-center text-slate-400">{t('an.loading')}</p>

  const k = data.kpis
  const hourly = data.hourly.filter((h) => h.hour >= 10)
  const byKind = data.alerts.by_kind || {}

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xs font-semibold tracking-[0.3em] text-slate-500">{t('an.title')}</h2>
          <span className="text-xs text-slate-500" dir="ltr">
            {data.range.from} → {data.range.to} · {data.range.tz}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {msg && <span className="text-slate-400">{msg}</span>}
          <button onClick={downloadPdf} className="rounded-md bg-sky-600 px-3 py-1.5 font-medium hover:bg-sky-500"><Icon id="download" className="me-1.5 h-4 w-4" />{t('an.pdf')}</button>
          <button onClick={sendNow} className="rounded-md bg-slate-800 px-3 py-1.5 hover:bg-slate-700"><Icon id="send" className="me-1.5 h-4 w-4" />{t('an.send')}</button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Kpi label={t('an.footfall')} value={k.total_guests} />
        <Kpi label={t('an.parties')} value={k.total_parties} />
        <Kpi label={t('an.avgParty')} value={k.avg_party_size} unit={t('an.guests')} />
        <Kpi label={t('an.peak')} value={k.peak_hour} />
        <Kpi label={t('an.busiest')} value={k.busiest_day} />
        <Kpi label={t('an.turns')} value={k.turns_per_table_per_day} unit={t('an.perTable')} />
        <Kpi label={t('an.dwell')} value={k.avg_dwell_min} unit={t('an.min')} />
        <Kpi label={t('an.clean')} value={k.avg_clean_turnaround_min} unit={t('an.min')} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t('an.peakTitle')} sub={t('an.peakSub')}>
          <div className="h-64" dir="ltr">
            <ResponsiveContainer>
              <BarChart data={hourly}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="hour" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(h) => `${h}h`} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip contentStyle={tip} cursor={{ fill: '#1e293b' }} labelFormatter={(h) => `${h}:00`} />
                <Bar dataKey="guests" name={t('an.series.hour')} fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title={t('an.dailyTitle')} sub={t('an.dailySub')}>
          <div className="h-64" dir="ltr">
            <ResponsiveContainer>
              <ComposedChart data={data.daily}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis yAxisId="l" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis yAxisId="r" orientation="right" tick={{ fill: '#94a3b8', fontSize: 11 }} unit="m" />
                <Tooltip contentStyle={tip} cursor={{ fill: '#1e293b' }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="l" dataKey="guests" name={t('an.series.guests')} fill="#34d399" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="l" dataKey="parties" name={t('an.series.parties')} fill="#a78bfa" radius={[4, 4, 0, 0]} />
                <Line yAxisId="r" dataKey="avg_dwell_min" name={t('an.series.dwell')} stroke="#fbbf24" strokeWidth={2} dot />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title={t('an.heatTitle')} sub={t('an.heatSub')}>
            <Heatmap data={data.heatmap} />
          </Card>
        </div>
        <Card title={t('an.turnTitle')} sub={t('an.turnSub')}>
          <table className="w-full text-sm">
            <thead className="text-[11px] text-slate-500">
              <tr>
                <th className="py-1 text-start">{t('an.table')}</th>
                <th className="text-start">{t('an.turnsCol')}</th>
                <th className="text-start">{t('an.guestsCol')}</th>
                <th className="text-start">{t('an.avgTime')}</th>
              </tr>
            </thead>
            <tbody>
              {data.per_table.map((x) => (
                <tr key={x.table} className="border-t border-slate-800">
                  <td className="py-1.5 font-semibold">{x.table}</td>
                  <td>{x.turns}</td>
                  <td>{x.guests}</td>
                  <td>{x.avg_dwell_min}m</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            <span className="rounded bg-red-500/15 px-2 py-1 text-red-300">{t('an.svcAlerts')}: {byKind.service_wait || 0}</span>
            <span className="rounded bg-amber-500/15 px-2 py-1 text-amber-300">{t('an.cleanAlerts')}: {byKind.uncleaned_table || 0}</span>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">{t('an.firstVisit', { n: k.avg_first_visit_wait_min })}</p>
        </Card>
      </div>

      <Card title={t('an.svcTitle')} sub={t('an.svcSub')}>
        <div className="grid gap-6 lg:grid-cols-3">
          <ServiceTable rows={data.service.by_shift} keyName="shift" label={t('an.shift')} t={t} />
          <ServiceTable rows={data.service.by_section} keyName="section" label={t('an.section')} t={t} />
          <ServiceTable rows={data.service.by_table} keyName="table" label={t('an.table')} t={t} />
        </div>
      </Card>
    </div>
  )
}
