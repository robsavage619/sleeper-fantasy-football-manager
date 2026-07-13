import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

const POS_FILTER = ['ALL', 'QB', 'RB', 'WR', 'TE'] as const
type Filter = (typeof POS_FILTER)[number]

const TABLE_COLS = ['#', 'PLAYER', 'POS', 'AGE', 'TEAM', 'PRIORITY', 'ADDS', 'EST. BID']

function PriorityBar({ value }: { value: number }) {
  const color = value > 80 ? '#c93328' : value >= 60 ? '#d4860c' : '#00b8cc'
  return (
    <div
      style={{
        width: '100%',
        height: 3,
        background: '#162035',
        borderRadius: 1,
        overflow: 'hidden',
      }}
    >
      <motion.div
        style={{ height: '100%', background: color, borderRadius: 1 }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, value)}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  )
}

export function Waivers() {
  const [filter, setFilter] = useState<Filter>('ALL')

  const { data, isLoading, error } = useQuery({
    queryKey: ['waiver-candidates'],
    queryFn: () => api.waiverCandidates(),
  })

  const candidates = (data ?? []).filter((c) => filter === 'ALL' || c.position === filter)

  return (
    <div>
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          padding: '6px 20px',
          background: 'rgba(201, 51, 40, 0.08)',
          borderBottom: '1px solid rgba(201, 51, 40, 0.3)',
        }}
      >
        <span
          style={{
            fontSize: 11,
            color: '#c93328',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            fontWeight: 600,
          }}
        >
          ⚠ All waiver claims require explicit approval before submission
        </span>
      </div>

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
            WAIVER WIRE
          </h1>
          <span
            className="tracking-[0.3em] uppercase"
            style={{ fontSize: 11, color: '#6a8098' }}
          >
            FAAB $500 · TUESDAY · ⚠ APPROVAL REQUIRED
          </span>
        </div>
      </div>

      {isLoading && (
        <div
          className="p-8 text-center tracking-widest uppercase"
          style={{ color: '#3d5070', fontSize: 12 }}
        >
          LOADING WAIVERS…
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

      <div
        className="flex items-center gap-3 px-5 py-3"
        style={{ borderBottom: '1px solid #162035', background: '#09111f' }}
      >
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
      </div>

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
            {candidates.map((c, i) => {
              const posColor = POS_COLOR[c.position] ?? '#6a8098'
              return (
                <motion.tr
                  key={c.player_id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.014 }}
                >
                  <td
                    className="py-2.5 pl-3 pr-2"
                    style={{
                      color: '#3d5070',
                      fontSize: 12,
                      fontFamily: "'DM Mono', monospace",
                      width: 40,
                    }}
                  >
                    {i + 1}
                  </td>
                  <td className="py-2.5 px-3" style={{ borderLeft: `2px solid ${posColor}` }}>
                    <span style={{ fontSize: 13, color: '#e8eef6', fontWeight: 500 }}>
                      {c.name}
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
                      {c.position}
                    </span>
                  </td>
                  <td
                    className="py-2.5 px-3 tabular-nums"
                    style={{
                      fontSize: 13,
                      color: '#6a8098',
                      fontFamily: "'DM Mono', monospace",
                      width: 48,
                    }}
                  >
                    {Math.round(c.age)}
                  </td>
                  <td className="py-2.5 px-3" style={{ fontSize: 12, color: '#3d5070', width: 56 }}>
                    {c.team || 'FA'}
                  </td>
                  <td className="py-2.5 px-3" style={{ width: 120, minWidth: 100 }}>
                    <PriorityBar value={c.add_priority} />
                  </td>
                  <td
                    className="py-2.5 px-3 tabular-nums"
                    style={{
                      fontSize: 13,
                      color: '#6a8098',
                      fontFamily: "'DM Mono', monospace",
                      width: 60,
                    }}
                  >
                    {c.trending_adds}
                  </td>
                  <td
                    className="py-2.5 px-3 tabular-nums"
                    style={{
                      fontSize: 13,
                      color: '#d4860c',
                      fontFamily: "'DM Mono', monospace",
                      width: 80,
                    }}
                  >
                    ${c.faab_estimate}
                  </td>
                </motion.tr>
              )
            })}
          </tbody>
        </table>
        {candidates.length === 0 && !isLoading && (
          <div
            className="py-10 text-center tracking-widest uppercase"
            style={{ color: '#3d5070', fontSize: 12 }}
          >
            NO CANDIDATES FOUND
          </div>
        )}
      </div>
    </div>
  )
}
