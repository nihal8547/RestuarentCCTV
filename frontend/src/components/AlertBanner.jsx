import React from 'react'
import { useI18n } from '../i18n.jsx'
import { alertText } from '../alertText.js'

/** Sticky red strip on every tab while any alert is unresolved - nobody has to be on the Live tab to notice it. */
export default function AlertBanner({ alerts = [], onView }) {
  const { t } = useI18n()
  const active = alerts.filter((a) => !a.resolved)
  if (!active.length) return null
  const first = active[0]
  return (
    <button
      onClick={onView}
      className="sticky top-2 z-30 mb-3 flex w-full items-center gap-3 rounded-xl border border-red-500/50 bg-red-600 px-4 py-2.5 text-start text-sm font-semibold text-white shadow-lg shadow-red-900/30"
      aria-live="assertive"
    >
      <span className="pulse-soft text-base">●</span>
      <span className="min-w-0 flex-1 truncate">{alertText(first, t)}</span>
      <span className="shrink-0 rounded-full bg-white/20 px-2 py-0.5 text-xs">{t('banner.count', { n: active.length })}</span>
    </button>
  )
}
