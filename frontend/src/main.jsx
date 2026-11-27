import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './index.css'

try {   // apply the saved theme before first paint (no flash)
  const th = localStorage.getItem('theme') || 'dark'
  document.documentElement.classList.toggle('light', th === 'light')
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', th === 'light' ? '#ffffff' : '#000000')
} catch { /* ignore */ }

createRoot(document.getElementById('root')).render(<App />)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}
