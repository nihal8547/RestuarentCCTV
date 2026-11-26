import React, { useState } from 'react'
import { useAuth } from '../AuthContext.jsx'
import { useI18n } from '../i18n.jsx'

export default function Login() {
  const { login, config } = useAuth()
  const { t, lang, setLang } = useI18n()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      await login(u.trim(), p)
    } catch {
      setErr(t('login.bad'))
    }
    setBusy(false)
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/80 p-7 shadow-2xl">
        <div className="mb-1 flex items-center justify-between">
          <h1 className="text-xl font-bold">{t('login.title')}</h1>
          <button type="button" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')} className="rounded-md bg-slate-800 px-2.5 py-1 text-xs hover:bg-slate-700">
            {lang === 'en' ? 'العربية' : 'English'}
          </button>
        </div>
        <p className="mb-5 text-sm text-slate-400">
          {config?.restaurant_name} · {t('login.sub')}
        </p>
        <label className="mb-1 block text-xs text-slate-400">{t('login.user')}</label>
        <input autoFocus value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-sky-500" />
        <label className="mb-1 block text-xs text-slate-400">{t('login.pass')}</label>
        <input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" className="mb-4 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-sky-500" />
        {err && <p className="mb-3 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</p>}
        <button disabled={busy || !u || !p} className="w-full rounded-lg bg-sky-600 py-2.5 font-semibold hover:bg-sky-500 disabled:opacity-40">
          {t('login.btn')}
        </button>
      </form>
    </div>
  )
}
