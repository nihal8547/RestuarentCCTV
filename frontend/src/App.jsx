import React, { useEffect, useState } from 'react'
import useLiveState from './hooks/useLiveState.js'
import useAlertNotifier from './hooks/useAlertNotifier.js'
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
import Icon from './components/Icon.jsx'
import Sidebar from './components/Sidebar.jsx'
import AlertBanner from './components/AlertBanner.jsx'
import Login from './components/Login.jsx'

function Main() {
  const { user, config, can, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { state, connected } = useLiveState(true)
  const [clock, setClock] = useState(new Date())
  const [theme, setTheme] = useState(() => (document.documentElement.classList.contains('light') ? 'light' : 'dark'))
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    document.documentElement.classList.toggle('light', next === 'light')
    document.querySelector('meta[name=theme-color]')?.setAttribute('content', next === 'light' ? '#ffffff' : '#000000')
    try { localStorage.setItem('theme', next) } catch { /* private mode */ }
    setTheme(next)
  }
  const alertSig = useAlertNotifier(state?.alerts, t)
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

  const [menu, setMenu] = useState(false)
  const activeAlerts = (state?.alerts || []).filter((a) => !a.resolved).length
  const title = t(tabs.find((x) => x[0] === tab)?.[1] || 'tab.live')

  const sideTools = (
    <>
      <div className="grid grid-cols-3 gap-2">
        <button onClick={toggleTheme} className="rounded-md bg-slate-800 px-2 py-2 hover:bg-slate-700"
          title={theme === 'light' ? 'Black theme' : 'White theme'} aria-label={theme === 'light' ? 'Black theme' : 'White theme'}>
          <Icon id={theme === 'light' ? 'moon' : 'sun'} className="mx-auto h-5 w-5" />
        </button>
        <button onClick={alertSig.enabled ? alertSig.disable : alertSig.enable}
          className={`rounded-md px-2 py-2 ${alertSig.enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-sky-600 text-white hover:bg-sky-500'}`}
          title={t('staff.enable')} aria-label={t('staff.enable')}>
          <Icon id={alertSig.enabled ? 'bell' : 'bellOff'} className="mx-auto h-5 w-5" />
        </button>
        <button onClick={() => setLang(lang === 'en' ? 'ar' : 'en')} className="rounded-md bg-slate-800 px-2 py-2 hover:bg-slate-700">
          {lang === 'en' ? 'ع' : 'EN'}
        </button>
      </div>
      {config?.auth_required && (
        <button onClick={logout} className="flex w-full items-center justify-between rounded-md bg-slate-800 px-3 py-2 hover:bg-slate-700" title={user.username}>
          <span className="truncate">{user.name} · {t(`role.${user.role}`)}</span>
          <Icon id="logout" className="h-4 w-4" />
        </button>
      )}
    </>
  )

  return (
    <div className="lg:flex">
      <Sidebar tabs={tabs} tab={tab} onGo={go} name={name} open={menu} onClose={() => setMenu(false)} alertCount={activeAlerts}>
        {sideTools}
      </Sidebar>

      <main className="min-w-0 flex-1 px-4 py-4 sm:px-6">
        <div className="mx-auto max-w-[1400px]">
          <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button onClick={() => setMenu(true)} className="rounded-md bg-slate-800 p-2 hover:bg-slate-700 lg:hidden" aria-label="Menu">
                <Icon id="menu" />
              </button>
              <div>
                <h1 className="text-lg font-bold tracking-tight">{title}</h1>
                <p className="hidden text-xs text-slate-500 sm:block">{t('app.sub')}</p>
              </div>
            </div>
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
            </div>
          </header>

      {tab !== 'staff' && <AlertBanner alerts={state?.alerts} onView={() => go('live')} />}

      {tab === 'live' && (
        <div className="space-y-4">
          <OccupancyHeader state={state} />
          <div className="grid gap-4 xl:grid-cols-12">
            {/* phone order: floor plan, alerts, camera. desktop: camera + alerts left, floor plan right */}
            <div className="order-3 xl:order-none xl:col-span-7 xl:row-start-1"><LiveFeed mode={state?.mode} fps={state?.fps} cameras={state?.cameras} /></div>
            <div className="order-2 xl:order-none xl:col-span-7 xl:row-start-2"><AlertPanel alerts={state?.alerts} /></div>
            <div className="order-1 xl:order-none xl:col-span-5 xl:col-start-8 xl:row-span-2 xl:row-start-1"><FloorPlan state={state} /></div>
          </div>
        </div>
      )}
      {tab === 'analytics' && <Analytics />}
      {tab === 'settings' && <Settings />}
      {tab === 'studio' && <Studio />}
      {tab === 'venues' && <Venues />}
      {tab === 'staff' && <StaffView state={state} alertsOn={alertSig.enabled} onEnable={alertSig.enable} />}
        </div>
      </main>
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
