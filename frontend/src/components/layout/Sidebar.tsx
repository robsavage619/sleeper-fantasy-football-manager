import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, leagueTypeLabel } from '@/lib/api'
import {
  BarChart2,
  Users,
  Zap,
  ArrowLeftRight,
  TrendingUp,
  Brain,
  Telescope,
  Sparkles,
  Award,
  Gauge,
  LineChart,
  Menu,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

type NavItem = { to: string; label: string; icon: LucideIcon }

// Grouped by the decision the GM is making this week, not by which engine
// produced the page — "This Week" for weekly action, "Market" for pricing
// intel, "Franchise" for roster-level state, "League" for scouting rivals,
// "Draft" for rookie-class work.
const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: 'This Week',
    items: [
      { to: '/', label: 'War Room', icon: BarChart2 },
      { to: '/matchups', label: 'Matchup Lab', icon: Gauge },
      { to: '/waivers', label: 'Waivers', icon: TrendingUp },
      { to: '/trades', label: 'Trades', icon: ArrowLeftRight },
    ],
  },
  {
    label: 'Market',
    items: [{ to: '/market', label: 'Market', icon: LineChart }],
  },
  {
    label: 'Franchise',
    items: [{ to: '/roster', label: 'Roster', icon: Users }],
  },
  {
    label: 'League',
    items: [
      { to: '/owners', label: 'GM Profiles', icon: Brain },
      { to: '/report-card', label: 'Report Card', icon: Award },
    ],
  },
  {
    label: 'Draft',
    items: [
      { to: '/draft', label: 'Draft Board', icon: Zap },
      { to: '/prospects', label: 'Prospects', icon: Telescope },
    ],
  },
  {
    label: '',
    items: [{ to: '/narrative', label: 'AI Briefing', icon: Sparkles }],
  },
]

function NavLinks() {
  return (
    <div className="flex flex-col flex-1 py-3 px-2 gap-3 overflow-y-auto">
      {NAV_GROUPS.map((group, gi) => (
        <div key={group.label || `group-${gi}`}>
          {group.label && (
            <div
              className="px-3 pb-1 tracking-[0.24em] uppercase"
              style={{ fontSize: 9.5, color: '#2d4060', fontWeight: 700 }}
            >
              {group.label}
            </div>
          )}
          <div className="flex flex-col gap-px">
            {group.items.map(({ to, label, icon: Icon }) => (
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
        </div>
      ))}
    </div>
  )
}

export function Sidebar() {
  const { data: league } = useQuery({ queryKey: ['league'], queryFn: api.league, staleTime: 10 * 60 * 1000 })
  const subtitle = league ? `${leagueTypeLabel(league)} · ${league.season}` : 'DYNASTY'
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <>
      {/* Mobile top bar — shown below md, replaces the fixed sidebar */}
      <div
        className="md:hidden flex items-center justify-between px-3 py-2 sticky top-0 z-30"
        style={{ background: '#070c16', borderBottom: '1px solid #162035' }}
      >
        <span
          className="tracking-[0.2em] uppercase"
          style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 16, fontWeight: 800, color: '#00b8cc' }}
        >
          WAR ROOM
        </span>
        <button
          onClick={() => setMobileOpen((o) => !o)}
          aria-label="Toggle navigation"
          style={{ color: '#8aa0b8', background: 'transparent', border: 'none', padding: 4, cursor: 'pointer' }}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      {mobileOpen && (
        <nav
          className="md:hidden flex flex-col sticky top-[41px] z-30"
          style={{ maxHeight: 'calc(100vh - 41px)', background: '#070c16', borderBottom: '1px solid #162035', overflowY: 'auto' }}
          onClick={() => setMobileOpen(false)}
        >
          <NavLinks />
        </nav>
      )}

      {/* Desktop sidebar */}
      <nav
        className="hidden md:flex flex-col h-screen sticky top-0 shrink-0"
        style={{ width: 200, background: '#070c16', borderRight: '1px solid #162035' }}
      >
      {/* Brand / logo */}
      <div className="px-3 pt-4 pb-3" style={{ borderBottom: '1px solid #162035' }}>
        <img
          src="/logo.png"
          alt="Sleeper War Room"
          // The asset carries a baked-in black field; screen blending drops it
          // against the dark sidebar so the mark reads as part of the chrome
          // instead of a pasted-on slab.
          style={{ width: '100%', height: 'auto', display: 'block', mixBlendMode: 'screen' }}
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
          {subtitle}
        </div>
      </div>

      {/* Nav */}
      <NavLinks />

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
    </>
  )
}
