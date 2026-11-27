import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import { useI18n } from '../i18n.jsx'
import VideoSource from './VideoSource.jsx'
import ZoneEditor from './ZoneEditor.jsx'
import { Icon } from './Sidebar.jsx'

function Section({ title, children }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
      <h3 className="mb-4 text-sm font-bold tracking-wide">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, help, children }) {
  return (
    <label className="block text-xs">
      <span className="text-slate-300">{label}</span>
      {children}
      {help && <span className="mt-1 block text-[11px] text-slate-500">{help}</span>}
    </label>
  )
}

const inputCls = 'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-500 disabled:opacity-50'

function Chip({ ok, children }) {
  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-700/50 text-slate-400'}`}>{children}</span>
}

export default function Settings() {
  const { t } = useI18n()
  const { can, user } = useAuth()
  const isOwner = can('owner')
  const [s, setS] = useState(null)
  const [saved, setSaved] = useState('')
  const [users, setUsers] = useState([])
  const [nu, setNu] = useState({ username: '', password: '', role: 'staff' })
  const [userErr, setUserErr] = useState('')

  const load = () => api('/api/settings').then(setS)
  const loadUsers = () => isOwner && api('/api/users').then(setUsers).catch(() => {})
  useEffect(() => {
    load()
    loadUsers()
    const i = setInterval(load, 5000)
    return () => clearInterval(i)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [form, setForm] = useState(null)
  const [sec, setSec] = useState(() => { try { return localStorage.getItem('set_sec') || 'general' } catch { return 'general' } })
  const pick = (id) => { setSec(id); try { localStorage.setItem('set_sec', id) } catch { /* ignore */ } }
  useEffect(() => {
    if (s && !form) setForm(s)
  }, [s, form])
  if (!s || !form) return null

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const save = async () => {
    const keys = ['restaurant_name', 'wait_alert_sec', 'clean_alert_sec', 'occupy_confirm_sec', 'leave_confirm_sec', 'waiter_visit_sec', 'clean_confirm_sec', 'camera_offline_sec', 'report_enabled', 'report_weekday', 'report_hour']
    const body = Object.fromEntries(keys.map((k) => [k, form[k]]))
    try {
      const r = await api('/api/settings', { method: 'PUT', body })
      setS(r)
      setForm(r)
      setSaved(t('set.saved'))
    } catch (e) {
      setSaved(`⚠ ${e.message}`)
    }
    setTimeout(() => setSaved(''), 4000)
  }

  const addUser = async () => {
    setUserErr('')
    try {
      await api('/api/users', { method: 'POST', body: nu })
      setNu({ username: '', password: '', role: 'staff' })
      loadUsers()
    } catch (e) {
      setUserErr(e.message)
    }
  }
  const resetPw = async (u) => {
    const pw = window.prompt(t('set.newPw'))
    if (pw) await api(`/api/users/${u.id}/password`, { method: 'PUT', body: { password: pw } }).catch((e) => alert(e.message))
  }
  const simToggle = async (cam, offline) => {
    await api(`/api/sim/camera/${cam}`, { method: 'POST', body: { offline } })
    load()
  }

  const num = (k, label, help, step = 1) => (
    <Field label={label} help={help}>
      <input type="number" step={step} disabled={!isOwner} value={form[k]} onChange={(e) => set(k, e.target.value)} className={inputCls} />
    </Field>
  )

  const keys = ['restaurant_name', 'wait_alert_sec', 'clean_alert_sec', 'occupy_confirm_sec', 'leave_confirm_sec', 'waiter_visit_sec', 'clean_confirm_sec', 'camera_offline_sec', 'report_enabled', 'report_weekday', 'report_hour']
  const dirty = isOwner && keys.some((k) => String(form[k]) !== String(s[k]))
  const groups = [
    ['general', 'set.sec.general', 'settings', true],
    ['alerts', 'set.sec.alerts', 'live', true],
    ['cameras', 'set.sec.cameras', 'studio', true],
    ['zones', 'set.sec.zones', 'venues', isOwner],
    ['users', 'set.sec.users', 'staff', isOwner],
    ['system', 'set.sec.system', 'analytics', true],
  ].filter((g) => g[3])
  const cur = groups.some((g) => g[0] === sec) ? sec : 'general'

  return (
    <div className="gap-6 md:flex">
      <nav className="mb-4 flex shrink-0 gap-1 overflow-x-auto whitespace-nowrap md:mb-0 md:sticky md:top-4 md:w-52 md:flex-col md:self-start" aria-label="Settings sections">
        {groups.map(([id, key, icon]) => (
          <button key={id} onClick={() => pick(id)} aria-current={cur === id ? 'page' : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-start text-sm font-medium transition ${cur === id ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
            <Icon id={icon} className="h-4 w-4" />{t(key)}
          </button>
        ))}
      </nav>

      <div className="min-w-0 flex-1 space-y-4 pb-20">
        {!isOwner && <p className="text-xs text-amber-300">{t('set.readonly')}</p>}

        {cur === 'general' && (
          <>
        <Section title={t('set.general')}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Field label={t('set.name')}>
                <input disabled={!isOwner} value={form.restaurant_name} onChange={(e) => set('restaurant_name', e.target.value)} className={inputCls} />
              </Field>
            </div>
            {num('wait_alert_sec', t('set.wait'), t('set.waitHelp'))}
            {num('clean_alert_sec', t('set.clean'), t('set.cleanHelp'))}
            {num('occupy_confirm_sec', t('set.occupy'), null, 0.5)}
            {num('leave_confirm_sec', t('set.leave'), null, 0.5)}
            {num('waiter_visit_sec', t('set.visit'), null, 0.5)}
            {num('clean_confirm_sec', t('set.cleanConfirm'), null, 0.5)}
            {num('camera_offline_sec', t('set.camOffline'))}
          </div>
        </Section>
          </>
        )}

        {cur === 'alerts' && (
          <>
          <Section title={t('set.report')}>
            <label className="mb-3 flex items-center gap-2 text-sm">
              <input type="checkbox" disabled={!isOwner} checked={!!form.report_enabled} onChange={(e) => set('report_enabled', e.target.checked)} />
              {t('set.reportOn')}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t('set.weekday')}>
                <select disabled={!isOwner} value={form.report_weekday} onChange={(e) => set('report_weekday', Number(e.target.value))} className={inputCls}>
                  {[0, 1, 2, 3, 4, 5, 6].map((d) => (<option key={d} value={d}>{t(`day.${d}`)}</option>))}
                </select>
              </Field>
              <Field label={t('set.hour')}>
                <input type="number" min="0" max="23" disabled={!isOwner} value={form.report_hour} onChange={(e) => set('report_hour', Number(e.target.value))} className={inputCls} />
              </Field>
            </div>
          </Section>

          <Section title={t('set.notif')}>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="flex items-center gap-2">{t('set.webhook')} <Chip ok={s.notifications.webhook}>{s.notifications.webhook ? t('set.configured') : t('set.notConfigured')}</Chip></span>
              <span className="flex items-center gap-2">{t('set.telegram')} <Chip ok={s.notifications.telegram}>{s.notifications.telegram ? t('set.configured') : t('set.notConfigured')}</Chip></span>
            </div>
            <p className="mt-3 text-[11px] text-slate-500">{t('set.notifHelp')}</p>
          </Section>

          </>
        )}

        {cur === 'cameras' && (
          <>
          <Section title={t('set.cameras')}>
            <ul className="space-y-2 text-sm">
              {s.cameras.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${c.online ? 'bg-emerald-400' : 'bg-red-500 pulse-soft'}`} />
                    <b>{c.id}</b> <span className="text-xs text-slate-500">{c.source}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <Chip ok={c.online}>{c.online ? t('set.online') : t('set.offline')}</Chip>
                    {isOwner && c.sim && (
                      <button onClick={() => simToggle(c.id, c.online)} className="rounded bg-slate-800 px-2.5 py-1 text-xs hover:bg-slate-700">
                        {c.online ? t('set.simOff') : t('set.simOn')}
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            {s.cameras.some((c) => c.sim) && <p className="mt-2 text-[11px] text-slate-500">{t('set.simHelp')}</p>}
          </Section>
            {isOwner && (
        <Section title="Video source - real video / live CCTV">
          <VideoSource />
        </Section>
      )}

            )}
          </>
        )}

        {cur === 'zones' && isOwner && (
          <>
        <Section title={t('set.zones')}>
          <ZoneEditor cameras={s.cameras} />
        </Section>
      )}

          </>
        )}

        {cur === 'users' && isOwner && (
          <>
        <Section title={t('set.users')}>
          <table className="mb-4 w-full text-sm">
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-slate-800">
                  <td className="py-2 font-semibold">{u.username}</td>
                  <td className="text-slate-400">{u.display_name}</td>
                  <td><Chip ok={u.role === 'owner'}>{t(`role.${u.role}`)}</Chip></td>
                  <td className="text-end">
                    <button onClick={() => resetPw(u)} className="me-2 rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700">{t('set.resetPw')}</button>
                    {u.username !== user.username && (
                      <button onClick={async () => { await api(`/api/users/${u.id}`, { method: 'DELETE' }); loadUsers() }} className="rounded bg-red-600/70 px-2 py-1 text-xs hover:bg-red-600">{t('set.delUser')}</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid gap-2 sm:grid-cols-4">
            <input placeholder={t('set.username')} value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} className={inputCls} />
            <input type="password" placeholder={t('set.password')} value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} className={inputCls} />
            <select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })} className={inputCls}>
              {['staff', 'manager', 'owner'].map((r) => (<option key={r} value={r}>{t(`role.${r}`)}</option>))}
            </select>
            <button onClick={addUser} className="mt-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold hover:bg-emerald-500">{t('set.addUser')}</button>
          </div>
          {userErr && <p className="mt-2 text-xs text-red-300">{userErr}</p>}
        </Section>
      )}

          </>
        )}

        {cur === 'system' && (
          <>
      <Section title={t('set.hubInfo')}>
        <p className="text-sm text-slate-300">
          {s.hub.enabled ? t('set.hubOn') : s.hub.pushing_to ? t('set.hubPush', { u: s.hub.pushing_to }) : t('set.hubOff')}
        </p>
      </Section>
          </>
        )}
      </div>

      {dirty && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-700 bg-slate-900 px-4 py-3 lg:start-64">
          <div className="mx-auto flex max-w-[1400px] items-center justify-end gap-3">
            <span className="me-auto text-xs text-amber-300">● {t('set.unsaved')}</span>
            {saved && <span className="text-xs text-slate-300">{saved}</span>}
            <button onClick={() => setForm(s)} className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700">{t('set.discard')}</button>
            <button onClick={save} className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500">{t('set.save')}</button>
          </div>
        </div>
      )}
    </div>
  )
}
