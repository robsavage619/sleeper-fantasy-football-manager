import { NavLink } from 'react-router-dom'
import { BarChart2, Users, Zap, ArrowLeftRight, TrendingUp, Brain, Telescope, FileText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const NAV: Array<{ to: string; label: string; icon: LucideIcon }> = [
  { to: '/', label: 'War Room', icon: BarChart2 },
  { to: '/draft', label: 'Draft Board', icon: Zap },
  { to: '/roster', label: 'Roster', icon: Users },
  { to: '/trades', label: 'Trades', icon: ArrowLeftRight },
  { to: '/waivers', label: 'Waivers', icon: TrendingUp },
  { to: '/owners', label: 'GM Profiles', icon: Brain },
  { to: '/prospects', label: 'Prospects', icon: Telescope },
  { to: '/narrative', label: 'War Room Brief', icon: FileText },
]

export function Sidebar() {
  return (
    <nav
      className="flex flex-col h-screen sticky top-0 shrink-0"
      style={{ width: 200, background: '#070c16', borderRight: '1px solid #162035' }}
    >
      {/* Brand / logo */}
      <div className="px-3 pt-4 pb-3" style={{ borderBottom: '1px solid #162035' }}>
        <img
          src="/logo.png"
          alt="Sleeper War Room"
          style={{ width: '100%', height: 'auto', display: 'block' }}
          onError={(e) => {
            // Fallback: hide the broken image, show text brand
            ;(e.currentTarget as HTMLImageElement).style.display = 'none'
            const fallback = e.currentTarget.nextElementSibling as HTMLElement | null
            if (fallback) fallback.style.display = 'block'
          }}
        />
        {/* Text fallback — hidden when logo loads */}
        <div style={{ display: 'none' }}>
          <div
            className="leading-none tracking-[0.12em] uppercase"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: 24,
              fontWeight: 800,
              color: '#e8eef6',
            }}
          >
            SLEEPER
          </div>
          <div
            className="leading-none tracking-[0.2em] uppercase mt-0.5"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: 16,
              fontWeight: 700,
              color: '#00b8cc',
            }}
          >
            WAR ROOM
          </div>
        </div>
        <div
          className="mt-2 tracking-[0.3em] uppercase"
          style={{ fontSize: 10, color: '#3a7cc0' }}
        >
          DYNASTY · 2026
        </div>
      </div>

      {/* Nav */}
      <div className="flex flex-col flex-1 py-3 px-2 gap-px">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 12px',
              borderRadius: 2,
              fontSize: 13,
              fontWeight: 500,
              textDecoration: 'none',
              letterSpacing: '0.01em',
              transition: 'background 0.1s, color 0.1s',
              background: isActive ? '#0d1e2e' : 'transparent',
              color: isActive ? '#e8eef6' : '#6a8098',
              borderLeft: `2px solid ${isActive ? '#00b8cc' : 'transparent'}`,
            })}
          >
            <Icon size={14} />
            {label}
          </NavLink>
        ))}
      </div>

      {/* Footer */}
      <div
        className="px-4 py-3"
        style={{ borderTop: '1px solid #162035' }}
      >
        <div
          className="tracking-[0.25em] uppercase"
          style={{ fontSize: 10, color: '#2d4060' }}
        >
          AI-REASONED · v0.1
        </div>
      </div>
    </nav>
  )
}
