const KEY = 'ra_token'

export const getToken = () => {
  try {
    return localStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}
export const setToken = (t) => {
  try {
    t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}

/** Append ?token= for resources the browser fetches itself (<img> MJPEG stream, WebSocket). */
export const withToken = (url) => {
  const t = getToken()
  return t ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(t)}` : url
}

export async function api(path, { method = 'GET', body, raw = false } = {}) {
  const headers = {}
  const t = getToken()
  if (t) headers.Authorization = `Bearer ${t}`
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) })
  if (res.status === 401 && !path.includes('/auth/login')) {
    window.dispatchEvent(new Event('ra:unauth'))
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* not json */
    }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return raw ? res : res.json()
}
