import React from 'react'
import { useI18n } from '../i18n.jsx'

const P = {
  live: 'M3 12h4l3-8 4 16 3-8h4',
  analytics: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6zm7.4-3a7.4 7.4 0 00-.1-1.2l2-1.5-2-3.5-2.3 1a7.6 7.6 0 00-2-1.2L14.5 3h-4l-.4 2.6a7.6 7.6 0 00-2 1.2l-2.3-1-2 3.5 2 1.5a7.4 7.4 0 000 2.4l-2 1.5 2 3.5 2.3-1a7.6 7.6 0 002 1.2l.4 2.6h4l.4-2.6a7.6 7.6 0 002-1.2l2.3 1 2-3.5-2-1.5c.1-.4.1-.8.1-1.2z',
  studio: 'M12 3l2.2 5.3L20 9l-4.2 3.8L17 18.5 12 15.6 7 18.5l1.2-5.7L4 9l5.8-.7L12 3z',
  venues: 'M3 21V8l9-5 9 5v13M9 21v-6h6v6',
  staff: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM4 21a8 8 0 0116 0',
}

export function Icon({ id, className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={P[id] || P.live} />
    </svg>
  )
}

/** Left navigation. Fixed column on desktop, slide-in drawer on phones. */
export default function Sidebar({ tabs, tab, onGo, name, open, onClose, alertCount, children }) {
  const { t } = useI18n()
  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 start-0 z-50 flex w-64 flex-col border-e border-slate-800 bg-slate-900 transition-transform duration-200 lg:sticky lg:top-0 lg:z-20 lg:h-screen lg:translate-x-0 lg:shrink-0 ${open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full'} lg:rtl:translate-x-0`}
      >
        <div className="flex items-center gap-3 px-5 pb-4 pt-5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-sky-600 text-white"><Icon id="live" /></div>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold leading-tight">{name || t('app.title')}</p>
            <p className="truncate text-[11px] text-slate-500">{t('app.title')}</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
          {tabs.map(([id, key]) => (
            <button
              key={id}
              onClick={() => { onGo(id); onClose() }}
              aria-current={tab === id ? 'page' : undefined}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-start text-sm font-medium transition ${tab === id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
            >
              <Icon id={id} />
              <span className="flex-1 truncate">{t(key)}</span>
              {id === 'live' && alertCount > 0 && (
                <span className="rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">{alertCount}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="space-y-2 border-t border-slate-800 p-3 text-xs text-slate-400">{children}</div>
      </aside>
    </>
  )
}
