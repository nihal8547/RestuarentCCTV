import React, { useState } from 'react'
import { withToken } from '../api.js'
import { useI18n } from '../i18n.jsx'

export default function LiveFeed({ mode, fps, cameras = [] }) {
  const { t } = useI18n()
  const [error, setError] = useState(false)
  const [nonce, setNonce] = useState(0)
  const [cam, setCam] = useState(null)
  const active = cam || cameras[0]?.id || 'cam1'
  const info = cameras.find((c) => c.id === active)

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${info?.online === false ? 'bg-slate-500' : 'bg-red-500 pulse-soft'}`} />
          <h3 className="text-sm font-semibold tracking-wide">{t('feed.title')}</h3>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          {cameras.length > 1 && (
            <div className="flex overflow-hidden rounded-md border border-slate-700">
              {cameras.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setCam(c.id)
                    setError(false)
                    setNonce((n) => n + 1)
                  }}
                  className={`px-2.5 py-1 ${active === c.id ? 'bg-slate-700 text-white' : 'hover:bg-slate-800'}`}
                >
                  {c.id}
                  <span className={`ms-1.5 inline-block h-1.5 w-1.5 rounded-full ${c.online ? 'bg-emerald-400' : 'bg-red-500'}`} />
                </button>
              ))}
            </div>
          )}
          <span>
            {mode === 'sim' ? t('feed.sim') : t('feed.cctv')} · <span dir="ltr">{fps ?? 0} fps</span>
          </span>
        </div>
      </div>
      <div className="relative aspect-video bg-black">
        {error ? (
          <div className="absolute inset-0 grid place-items-center text-center text-sm text-slate-400">
            <div>
              <p>{t('feed.unavailable')}</p>
              <button
                onClick={() => {
                  setError(false)
                  setNonce((n) => n + 1)
                }}
                className="mt-3 rounded-md bg-slate-800 px-3 py-1.5 text-xs hover:bg-slate-700"
              >
                {t('feed.retry')}
              </button>
            </div>
          </div>
        ) : (
          <img
            key={`${active}-${nonce}`}
            src={withToken(`/video_feed?cam=${active}&n=${nonce}`)}
            alt="Live annotated CCTV feed"
            className="h-full w-full object-contain"
            onError={() => setError(true)}
          />
        )}
      </div>
      <div className="flex flex-wrap gap-4 border-t border-slate-800 px-4 py-2 text-[11px] text-slate-400">
        <Legend color="bg-emerald-500" text={t('legend.free')} />
        <Legend color="bg-red-500" text={t('legend.occupied')} />
        <Legend color="bg-amber-500" text={t('legend.cleaning')} />
        <Legend color="bg-sky-500" text={t('legend.staff')} />
      </div>
    </div>
  )
}

function Legend({ color, text }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-sm ${color}`} />
      {text}
    </span>
  )
}
