import React from 'react'

/** One consistent line-icon set (24x24, stroke 1.8). No emoji anywhere in the UI. */
const P = {
  live: 'M3 12h4l3-8 4 16 3-8h4',
  analytics: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
  settings: 'M12 9a3 3 0 100 6 3 3 0 000-6zm7.4 3a7.4 7.4 0 00-.1-1.2l2-1.5-2-3.5-2.3 1a7.6 7.6 0 00-2-1.2L14.5 3h-4l-.4 2.6a7.6 7.6 0 00-2 1.2l-2.3-1-2 3.5 2 1.5a7.4 7.4 0 000 2.4l-2 1.5 2 3.5 2.3-1a7.6 7.6 0 002 1.2l.4 2.6h4l.4-2.6a7.6 7.6 0 002-1.2l2.3 1 2-3.5-2-1.5c.1-.4.1-.8.1-1.2z',
  studio: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7L19 16z',
  venues: 'M3 21V8l9-5 9 5v13M9 21v-6h6v6',
  staff: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 3a4 4 0 100 8 4 4 0 000-8z',
  users: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 3a4 4 0 100 8 4 4 0 000-8zM23 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8',
  sun: 'M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4',
  moon: 'M12 3a6 6 0 009 9 9 9 0 11-9-9z',
  bell: 'M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 003.4 0',
  bellOff: 'M8.7 3A6 6 0 0118 8c0 2.7.5 4.5 1.1 5.8M17 17H3s3-2 3-9c0-.7.1-1.4.3-2M10.3 21a1.94 1.94 0 003.4 0M2 2l20 20',
  logout: 'M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9',
  clock: 'M12 2a10 10 0 100 20 10 10 0 000-20zM12 6v6l4 2',
  clean: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z',
  camera: 'M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2zM12 9a4 4 0 100 8 4 4 0 000-8z',
  cameraOff: 'M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2zM2 2l20 20',
  warn: 'M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0zM12 9v4M12 17h.01',
  check: 'M20 6L9 17l-5-5',
  x: 'M18 6L6 18M6 6l12 12',
  download: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  pencil: 'M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z',
  menu: 'M4 6h16M4 12h16M4 18h16',
  arrowLeft: 'M19 12H5M12 19l-7-7 7-7',
  arrowRight: 'M5 12h14M12 5l7 7-7 7',
  dot: 'M12 9a3 3 0 100 6 3 3 0 000-6z',
  party: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 3a4 4 0 100 8 4 4 0 000-8z',
}

export default function Icon({ id, className = 'h-5 w-5', fill = false }) {
  return (
    <svg viewBox="0 0 24 24" fill={fill ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={`inline-block shrink-0 ${className}`} aria-hidden="true">
      <path d={P[id] || P.live} />
    </svg>
  )
}
export { Icon }
