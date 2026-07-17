import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="p-10 flex flex-col items-center justify-center text-center" style={{ minHeight: '60vh' }}>
      <div
        className="uppercase tracking-wide leading-none"
        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 72, fontWeight: 800, color: '#162035' }}
      >
        404
      </div>
      <div
        className="uppercase tracking-wide leading-none mt-2"
        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 24, fontWeight: 800, color: '#e8eef6' }}
      >
        No signal on this frequency
      </div>
      <p style={{ color: '#6a8098', fontSize: 13, marginTop: 10, maxWidth: 380 }}>
        That page doesn't exist, or the link is stale. Head back to the War Room to keep working.
      </p>
      <Link
        to="/"
        className="mt-6 tracking-[0.2em] uppercase"
        style={{
          fontSize: 11,
          padding: '9px 18px',
          color: '#060a12',
          background: '#00b8cc',
          borderRadius: 2,
          textDecoration: 'none',
          fontWeight: 700,
        }}
      >
        ← Back to War Room
      </Link>
    </div>
  )
}
