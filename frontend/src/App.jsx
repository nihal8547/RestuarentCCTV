import React, { useEffect, useState } from 'react'
import useLiveState from './hooks/useLiveState.js'
import { AuthProvider, useAuth } from './AuthContext.jsx'
import { I18nProvider, useI18n } from './i18n.jsx'
import OccupancyHeader from './components/OccupancyHeader.jsx'
import LiveFeed from './components/LiveFeed.jsx'
import FloorPlan from './components/FloorPlan.jsx'
import AlertPanel from './components/AlertPanel.jsx'
import Analytics from './components/Analytics.jsx'
import Settings from './components/Settings.jsx'
import Studio from './components/Studio.jsx'
import Venues from './components/Venues.jsx'
import StaffView from './components/StaffView.jsx'
import Login from './components/Login.jsx'

function Main() {
  const { user, config, can, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { state, connected } = useLiveState(true)
  const [clock, setClock] = useState(new Date())
  const tabs = [
    ['live', 'tab.live', can('staff')],
    ['analytics', 'tab.analytics', can('manager')],
    ['settings', 'tab.settings', can('manager')],
    ['studio', 'tab.studio', can('owner')],
    ['venues', 'tab.venues', can('owner') && config?.features?.hub],
    ['staff', 'tab.staff', can('staff')],
  ].filter((x) => x[2])
  const fromHash = () => window.location.hash.replace('#/', '').replace('#', '')
  const [tab, setTab] = useState(() => {
    const h = fromHash()
    return tabs.some((x) => x[0] === h) ? h : user.role === 'staff' ? 'staff' : 'live'
  })
  const go = (id) => {
    setTab(id)
    window.location.hash = `/${id}`
  }
  useEffect(() => {
    const i = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(i)
  }, [])

  const th = state?.thresholds
  const name = state?.restaurant_name || config?.restaurant_name

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-4 sm:px-6">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight">{name ? `${name} · ` : ''}{t('app.title')}</h1>
          <p className="text-xs text-slate-500">{t('app.sub')}</p>
        </div>

        <nav className="flex flex-wrap rounded-lg border border-slate-800 bg-slate-900 p-1 text-sm">
          {tabs.map(([id, key]) => (
            <button
              key={id}
              onClick={() => go(id)}
              className={`rounded-md px-3.5 py-1.5 font-medium transition ${tab === id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
            >
              {t(key)}
            </button>
          ))}
        </nav>

        <div className="flex flex-wrap items-center gap-2.5 text-xs text-slate-400">
          {th?.demo && (
            <span className="hidden rounded-full bg-violet-500/15 px-2.5 py-1 text-violet-300 sm:inline" title="Alert thresholds shortened for the demo">
              {t('hdr.demo', { w: th.wait_alert_sec, c: th.clean_alert_sec })}
            </span>
          )}
          <span className="hidden tabular-nums sm:inline" dir="ltr">{clock.toLocaleTimeString()}</span>
          <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 ${connected ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400 pulse-soft'}`} />
            {connected ? t('hdr.live') : t('hdr.reconnecting')}
          </span>
          <button onClick={() => setLang(lang === 'en' ? 'ar' : 'en')} className="rounded-md bg-slate-800 px-2.5 py-1 hover:bg-slate-700">
            {lang === 'en' ? 'العربية' : 'English'}
          </button>
          {config?.auth_required && (
            <button onClick={logout} className="rounded-md bg-slate-800 px-2.5 py-1 hover:bg-slate-700" title={user.username}>
              {user.name} · {t(`role.${user.role}`)} ⎋
            </button>
          )}
        </div>
      </header>

      {tab === 'live' && (
        <div className="space-y-4">
          <OccupancyHeader state={state} />
          <div className="grid gap-4 xl:grid-cols-12">
            <div className="space-y-4 xl:col-span-7">
              <LiveFeed mode={state?.mode} fps={state?.fps} cameras={state?.cameras} />
              <AlertPanel alerts={state?.alerts} />
            </div>
            <div className="xl:col-span-5">
              <FloorPlan state={state} />
            </div>
          </div>
        </div>
      )}
      {tab === 'analytics' && <Analytics />}
      {tab === 'settings' && <Settings />}
      {tab === 'studio' && <Studio />}
      {tab === 'venues' && <Venues />}
      {tab === 'staff' && <StaffView state={state} />}
    </div>
  )
}

function Shell() {
  const { user, ready, offline } = useAuth()
  const { t } = useI18n()
  if (!ready) return <p className="py-24 text-center text-slate-500">…</p>
  if (offline) return <p className="py-24 text-center text-red-300">Backend unreachable. Start it with: uvicorn app.main:app --port 8000</p>
  if (!user) return <Login />
  return <Main key={user.username} />
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </I18nProvider>
  )
}
