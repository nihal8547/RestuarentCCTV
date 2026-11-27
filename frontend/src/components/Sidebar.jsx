import React from 'react'
import { useI18n } from '../i18n.jsx'
import Icon from './Icon.jsx'

export { Icon }

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
