import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { ProspectProfile } from '@/lib/api'

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

const POS_FILTER = ['ALL', 'QB', 'RB', 'WR', 'TE'] as const
type Filter = (typeof POS_FILTER)[number]

const TABLE_COLS = ['#', 'PLAYER', 'POS', 'COLLEGE', 'AGE', 'TGT%', 'YPR', 'RECRUIT', 'SCORE']

function ScoreBar({ value }: { value: number }) {
  const color = value > 80 ? '#c93328' : value >= 60 ? '#d4860c' : '#00b8cc'
  return (
    <div style={{ width: '100%', height: 3, background: '#162035', borderRadius: 1, overflow: 'hidden' }}>
      <motion.div
        style={{ height: '100%', background: color, borderRadius: 1 }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, value)}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  )
}

function Stars({ count }: { count: number }) {
  return (
    <span style={{ color: '#d4860c', fontSize: 11, letterSpacing: '-0.05em' }}>
      {'★'.repeat(count)}
      <span style={{ color: '#2d4060' }}>{'★'.repeat(5 - count)}</span>
    </span>
  )
}

function ProspectRow({ prospect, index }: { prospect: ProspectProfile; index: number }) {
  const posColor = POS_COLOR[prospect.position] ?? '#6a8098'
  const showTgt = prospect.position === 'WR' || prospect.position === 'TE'

  return (
    <motion.tr
      key={prospect.name}
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.014 }}
    >
      <td
        className="py-2.5 pl-3 pr-2"
        style={{ color: '#3d5070', fontSize: 12, fontFamily: "'DM Mono', monospace", width: 40 }}
      >
        {index + 1}
      </td>
      <td className="py-2.5 px-3" style={{ borderLeft: `2px solid ${posColor}` }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 13, color: '#e8eef6', fontWeight: 500 }}>{prospect.name}</span>
          {prospect.player_id && (
            <span
              title="Matched on Sleeper"
              style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#00b8cc',
                flexShrink: 0,
              }}
            />
          )}
        </span>
      </td>
      <td className="py-2.5 px-3">
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.15em',
            padding: '2px 6px',
            color: posColor,
            background: `${posColor}18`,
            borderRadius: 1,
          }}
        >
          {prospect.position}
        </span>
      </td>
      <td className="py-2.5 px-3" style={{ fontSize: 12, color: '#6a8098', whiteSpace: 'nowrap' }}>
        {prospect.college || '—'}
      </td>
      <td
        className="py-2.5 px-3 tabular-nums"
        style={{ fontSize: 13, color: '#6a8098', fontFamily: "'DM Mono', monospace", width: 48 }}
      >
        {prospect.age != null ? prospect.age.toFixed(1) : '—'}
      </td>
      <td
        className="py-2.5 px-3 tabular-nums"
        style={{
          fontSize: 13,
          fontFamily: "'DM Mono', monospace",
          width: 60,
          color: showTgt ? '#1a9b5e' : '#2d4060',
        }}
      >
        {showTgt ? `${(prospect.target_share * 100).toFixed(1)}%` : '—'}
      </td>
      <td
        className="py-2.5 px-3 tabular-nums"
        style={{
          fontSize: 13,
          color: '#d4860c',
          fontFamily: "'DM Mono', monospace",
          width: 60,
        }}
      >
        {showTgt && prospect.yards_per_reception > 0 ? prospect.yards_per_reception.toFixed(1) : '—'}
      </td>
      <td className="py-2.5 px-3" style={{ width: 100, whiteSpace: 'nowrap' }}>
        {prospect.recruiting_rank != null ? (
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
              #{prospect.recruiting_rank}
            </span>
            {prospect.stars != null && <Stars count={prospect.stars} />}
          </span>
        ) : (
          <span style={{ fontSize: 12, color: '#2d4060' }}>—</span>
        )}
      </td>
      <td className="py-2.5 px-3" style={{ width: 120, minWidth: 100 }}>
        <div style={{ marginBottom: 4 }}>
          <ScoreBar value={prospect.dynasty_prospect_score} />
        </div>
        <span style={{ fontSize: 11, color: '#3d5070', fontFamily: "'DM Mono', monospace" }}>
          {prospect.dynasty_prospect_score.toFixed(1)}
        </span>
      </td>
    </motion.tr>
  )
}

export function Prospects() {
  const [filter, setFilter] = useState<Filter>('ALL')
  const [year, setYear] = useState(2025)

  const { data, isLoading, error } = useQuery({
    queryKey: ['prospects', year],
    queryFn: () => api.prospects(year, 200),
  })

  const prospects = (data ?? []).filter((p) => filter === 'ALL' || p.position === filter)
  const fallbackMode = (data ?? []).some((p) => p.rationale.includes('Sleeper dynasty fallback'))

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1
            className="leading-none uppercase tracking-wide"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: 40,
              fontWeight: 800,
              color: '#e8eef6',
            }}
          >
            PROSPECT BOARD
          </h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: '#6a8098' }}>
            CFBD · DYNASTY DRAFT CLASS · {year}
          </span>
        </div>
      </div>

      <div
        className="flex items-center gap-4 px-5 py-3"
        style={{ borderBottom: '1px solid #162035', background: '#09111f' }}
      >
        {/* Position filter */}
        <div className="flex gap-1">
          {POS_FILTER.map((pos) => (
            <button
              key={pos}
              onClick={() => setFilter(pos)}
              className="tracking-widest uppercase font-bold transition-all"
              style={{
                fontSize: 11,
                padding: '5px 12px',
                background: filter === pos ? '#00b8cc' : 'transparent',
                color: filter === pos ? '#060a12' : '#6a8098',
                border: `1px solid ${filter === pos ? '#00b8cc' : '#162035'}`,
                borderRadius: 2,
                cursor: 'pointer',
              }}
            >
              {pos}
            </button>
          ))}
        </div>

        {/* Year toggle */}
        <div className="flex gap-1 ml-4">
          {[2025, 2026].map((y) => (
            <button
              key={y}
              onClick={() => setYear(y)}
              className="tracking-widest uppercase font-bold transition-all"
              style={{
                fontSize: 11,
                padding: '5px 12px',
                background: year === y ? '#d4860c' : 'transparent',
                color: year === y ? '#060a12' : '#6a8098',
                border: `1px solid ${year === y ? '#d4860c' : '#162035'}`,
                borderRadius: 2,
                cursor: 'pointer',
              }}
            >
              {y}
            </button>
          ))}
        </div>

        <div className="flex-1" />
        {fallbackMode && (
          <span
            style={{
              fontSize: 10,
              color: '#d4860c',
              letterSpacing: '0.18em',
              padding: '3px 8px',
              border: '1px solid rgba(212,134,12,0.3)',
              background: 'rgba(212,134,12,0.08)',
              borderRadius: 2,
            }}
          >
            SLEEPER FALLBACK
          </span>
        )}
        <span style={{ fontSize: 11, color: '#2d4060', letterSpacing: '0.15em' }}>
          {prospects.length} PROSPECTS
        </span>
      </div>

      {isLoading && (
        <div className="p-8 text-center tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>
          LOADING PROSPECTS…
        </div>
      )}

      {fallbackMode && !error && (
        <div
          className="mx-5 mt-4 p-4"
          style={{
            background: 'rgba(212,134,12,0.07)',
            border: '1px solid rgba(212,134,12,0.22)',
            boxShadow: 'inset 3px 0 0 #d4860c',
            borderRadius: 2,
          }}
        >
          <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 18, fontWeight: 800, color: '#d4860c', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            CFBD feed unavailable
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: '#8aa0b8', lineHeight: 1.5 }}>
            Showing Sleeper dynasty search-rank fallback so the board stays useful without `CFBD_API_KEY`.
            Usage metrics remain blank until the college feed is configured.
          </div>
        </div>
      )}

      {error && (
        <div
          className="mx-5 mt-4 p-3"
          style={{
            background: 'rgba(201, 51, 40, 0.06)',
            border: '1px solid rgba(201, 51, 40, 0.2)',
            borderLeft: '3px solid #c93328',
            borderRadius: 2,
            color: '#e07060',
            fontSize: 13,
          }}
        >
          {String(error)}
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-left war-table">
          <thead>
            <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
              {TABLE_COLS.map((label) => (
                <th
                  key={label}
                  className="py-2 px-3"
                  style={{
                    color: '#3d5070',
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: '0.25em',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {prospects.map((p, i) => (
              <ProspectRow key={`${p.name}-${p.college}`} prospect={p} index={i} />
            ))}
          </tbody>
        </table>
        {prospects.length === 0 && !isLoading && (
          <div
            className="py-10 text-center tracking-widest uppercase"
            style={{ color: '#3d5070', fontSize: 12 }}
          >
            {error ? 'PROSPECT FEED UNAVAILABLE' : 'NO PROSPECTS FOUND'}
          </div>
        )}
      </div>
    </div>
  )
}
