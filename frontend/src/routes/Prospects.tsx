import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { ProspectProfile } from '@/lib/api'
import { ProspectScoutingDrawer } from '@/components/ProspectScoutingDrawer'
import { InfoTip, POS_COLOR } from '@/components/viz'
import { GLOSSARY } from '@/lib/glossary'

const COL_INFO: Record<string, string> = {
  'USG%': GLOSSARY.usageRate,
  SCORE: GLOSSARY.prospectScore,
}

const POS_FILTER = ['ALL', 'QB', 'RB', 'WR', 'TE'] as const
type Filter = (typeof POS_FILTER)[number]

// Flex-grid column widths shared between the header row and each virtualized
// data row so they stay pixel-aligned without native <table> layout (which
// @tanstack/react-virtual can't window row-by-row).
const COLS: Array<{ label: string; width: string }> = [
  { label: '#', width: '40px' },
  { label: 'PLAYER', width: '1fr' },
  { label: 'POS', width: '64px' },
  { label: 'COLLEGE', width: '140px' },
  { label: 'AGE', width: '52px' },
  { label: 'USG%', width: '64px' },
  { label: 'YPR', width: '64px' },
  { label: 'RECRUIT', width: '100px' },
  { label: 'SCORE', width: '120px' },
]
const GRID_TEMPLATE = COLS.map((c) => c.width).join(' ')
const ROW_HEIGHT = 46

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

function ProspectRow({
  prospect,
  rank,
  onOpen,
  scouted = false,
}: {
  prospect: ProspectProfile
  rank: number
  onOpen: (prospect: ProspectProfile) => void
  scouted?: boolean
}) {
  const posColor = POS_COLOR[prospect.position] ?? '#6a8098'
  const showUsage = prospect.position === 'WR' || prospect.position === 'TE'

  return (
    <div
      onClick={() => onOpen(prospect)}
      className="war-table-row"
      style={{
        display: 'grid',
        gridTemplateColumns: GRID_TEMPLATE,
        alignItems: 'center',
        height: ROW_HEIGHT,
        cursor: 'pointer',
        borderBottom: '1px solid #0e1526',
      }}
    >
      <span className="pl-3 pr-2" style={{ color: '#3d5070', fontSize: 12, fontFamily: "'DM Mono', monospace" }}>
        {rank}
      </span>
      <span className="px-3" style={{ borderLeft: `2px solid ${posColor}`, display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
        <span style={{ fontSize: 13, color: '#e8eef6', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {prospect.name}
        </span>
        {prospect.player_id && (
          <span
            title="Matched on Sleeper"
            style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#00b8cc', flexShrink: 0 }}
          />
        )}
        {scouted && (
          <span
            title="AI deep-scout report available — open to view"
            style={{
              flexShrink: 0,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.1em',
              padding: '1px 4px',
              color: '#1a9b5e',
              background: 'rgba(26,155,94,0.12)',
              border: '1px solid rgba(26,155,94,0.35)',
              borderRadius: 2,
            }}
          >
            AI
          </span>
        )}
      </span>
      <span className="px-3">
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
      </span>
      <span className="px-3" style={{ fontSize: 12, color: '#6a8098', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {prospect.college || '—'}
      </span>
      <span className="px-3 tabular-nums" style={{ fontSize: 13, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
        {prospect.age != null ? prospect.age.toFixed(1) : '—'}
      </span>
      <span className="px-3 tabular-nums" style={{ fontSize: 13, fontFamily: "'DM Mono', monospace", color: showUsage ? '#1a9b5e' : '#2d4060' }}>
        {showUsage ? `${(prospect.usage_rate * 100).toFixed(1)}%` : '—'}
      </span>
      <span className="px-3 tabular-nums" style={{ fontSize: 13, color: '#d4860c', fontFamily: "'DM Mono', monospace" }}>
        {showUsage && prospect.yards_per_reception > 0 ? prospect.yards_per_reception.toFixed(1) : '—'}
      </span>
      <span className="px-3" style={{ whiteSpace: 'nowrap' }}>
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
      </span>
      <span className="px-3">
        <div style={{ marginBottom: 4 }}>
          <ScoreBar value={prospect.dynasty_prospect_score} />
        </div>
        <span style={{ fontSize: 11, color: '#3d5070', fontFamily: "'DM Mono', monospace" }}>
          {prospect.dynasty_prospect_score.toFixed(1)}
        </span>
      </span>
    </div>
  )
}

// The rookie draft class currently on the clock = current calendar year.
const CURRENT_DRAFT_CLASS = new Date().getFullYear()

export function Prospects() {
  const [filter, setFilter] = useState<Filter>('ALL')
  const [year, setYear] = useState(CURRENT_DRAFT_CLASS)
  const [selected, setSelected] = useState<ProspectProfile | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['prospects', year],
    queryFn: () => api.prospects(year, 200),
  })

  // Which prospects have an AI deep-scout finding (kind `prospect_scout`), keyed by
  // Sleeper id and by lowercased name so the table can flag them without opening the drawer.
  const { data: scoutFindings } = useQuery({
    queryKey: ['findings', 'prospect_scout'],
    queryFn: () => api.findings('prospect_scout'),
    refetchInterval: 60_000,
  })
  const scoutedKeys = new Set<string>()
  for (const f of scoutFindings ?? []) {
    const b = (f.body ?? {}) as Record<string, unknown>
    if (b.player_id) scoutedKeys.add(`id:${String(b.player_id)}`)
    if (b.name) scoutedKeys.add(`nm:${String(b.name).toLowerCase()}`)
  }

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
          {[CURRENT_DRAFT_CLASS - 1, CURRENT_DRAFT_CLASS].map((y) => (
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
        {/* Header row — a CSS grid mirroring ROW's column widths, not a <table>,
            so the virtualized rows below stay pixel-aligned with it. */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: GRID_TEMPLATE,
            background: '#09111f',
            borderBottom: '1px solid #162035',
            minWidth: 720,
          }}
        >
          {COLS.map(({ label }) => (
            <div
              key={label}
              className="py-2 px-3"
              style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.25em', whiteSpace: 'nowrap' }}
            >
              {label}
              {COL_INFO[label] && <InfoTip text={COL_INFO[label]} label={label} />}
            </div>
          ))}
        </div>
        <ProspectVirtualList prospects={prospects} onOpen={setSelected} scoutedKeys={scoutedKeys} />
        {prospects.length === 0 && !isLoading && (
          <div
            className="py-10 text-center tracking-widest uppercase"
            style={{ color: '#3d5070', fontSize: 12 }}
          >
            {error ? 'PROSPECT FEED UNAVAILABLE' : 'NO PROSPECTS FOUND'}
          </div>
        )}
      </div>
      <ProspectScoutingDrawer prospect={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

/**
 * Virtualized row list (up to 200 prospects) — only the rows in the visible
 * scroll window are mounted. Row markup is a CSS-grid div (see ProspectRow),
 * not a native <table>, since @tanstack/react-virtual absolutely positions
 * each row inside the scroll container and native <tr> doesn't support that.
 */
function ProspectVirtualList({
  prospects,
  onOpen,
  scoutedKeys,
}: {
  prospects: ProspectProfile[]
  onOpen: (p: ProspectProfile) => void
  scoutedKeys: Set<string>
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: prospects.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  return (
    <div ref={scrollRef} style={{ minWidth: 720, maxHeight: '70vh', overflowY: 'auto' }}>
      <div style={{ position: 'relative', height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((row) => {
          const p = prospects[row.index]
          const scouted =
            (p.player_id != null && scoutedKeys.has(`id:${p.player_id}`)) ||
            scoutedKeys.has(`nm:${p.name.toLowerCase()}`)
          return (
            <div
              key={`${p.name}-${p.college}`}
              style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${row.start}px)` }}
            >
              <ProspectRow prospect={p} rank={row.index + 1} onOpen={onOpen} scouted={scouted} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
