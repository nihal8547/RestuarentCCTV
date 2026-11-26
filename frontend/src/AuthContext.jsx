import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setToken } from './api.js'

const Ctx = createContext(null)
export const RANK = { staff: 1, manager: 2, owner: 3 }

export function AuthProvider({ children }) {
  const [config, setConfig] = useState(null)
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [offline, setOffline] = useState(false)

  const logout = useCallback(() => {
    setToken('')
    setUser(null)
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const cfg = await api('/api/config')
        if (!alive) return
        setConfig(cfg)
        if (!cfg.auth_required) {
          setUser({ username: 'local', role: 'owner', name: 'Local' })
        } else {
          try {
            setUser(await api('/api/me'))
          } catch {
            setUser(null)
          }
        }
      } catch {
        setOffline(true)
      }
      alive && setReady(true)
    })()
    const onUnauth = () => logout()
    window.addEventListener('ra:unauth', onUnauth)
    return () => {
      alive = false
      window.removeEventListener('ra:unauth', onUnauth)
    }
  }, [logout])

  const login = async (username, password) => {
    const r = await api('/api/auth/login', { method: 'POST', body: { username, password } })
    setToken(r.token)
    setUser(r.user)
  }

  const can = (min) => !!user && RANK[user.role] >= RANK[min]

  return <Ctx.Provider value={{ config, user, ready, offline, login, logout, can }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
