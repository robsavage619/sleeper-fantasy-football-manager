import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { api, type StartSitRec, type WarRoomAction } from '@/lib/api'

function Panel({
  label,
  accent = '#00b8cc',
  children,
}: {
  label: string
  accent?: string
  children: ReactNode
}) {
  return (
    <div
      style={{
        background: '#0c1625',
        border: '1px solid #162035',
        borderLeft: `3px solid ${accent}`,
        borderRadius: 2,
      }}
    >
      <div
        className="px-4 py-2.5"
        style={{ borderBottom: '1px solid #162035' }}
      >
        <span
          className="tracking-[0.3em] uppercase font-semibold"
          style={{ fontSize: 10, color: accent }}
        >
          {label}
        </span>
      </div>
      {children}
    </div>
  )
}

function StatBlock({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        background: '#0c1625',
        border: '1px solid #162035',
        borderLeft: '3px solid #00b8cc',
        borderRadius: 2,
        padding: '14px 16px',
      }}
    >
      <p
        className="tracking-[0.25em] uppercase mb-1.5"
        style={{ fontSize: 10, color: '#6a8098' }}
      >
        {label}
      </p>
      <p
        className="leading-none font-bold"
        style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontSize: 32,
          color: '#e8eef6',
        }}
      >
        {value}
      </p>
      {sub && (
        <p className="mt-1.5" style={{ fontSize: 11, color: '#3d5070' }}>
          {sub}
        </p>
      )}
    </motion.div>
  )
}

export function Dashboard() {
  const { data: league } = useQuery({ queryKey: ['league'], queryFn: api.league })
  const { data: picks } = useQuery({ queryKey: ['traded-picks'], queryFn: api.tradedPicks })
  const { data: state } = useQuery({ queryKey: ['nfl-state'], queryFn: api.nflState })
  const { data: trending } = useQuery({
    queryKey: ['trending-add'],
    queryFn: () => api.trending('add'),
  })
  const { data: startSit } = useQuery({
    queryKey: ['startsit'],
    queryFn: () => api.startSit(),
    enabled: state?.season_type === 'regular',
  })
  const { data: actions } = useQuery({
    queryKey: ['war-room-actions'],
    queryFn: () => api.warRoomActions(12),
    refetchInterval: 60_000,
  })

  const leagueAny = league as Record<string, unknown> | undefined

  return (
    <div className="p-5 space-y-5">
      {/* Identity header */}
      <div className="flex items-baseline gap-4 pt-1">
        <h1
          className="leading-none uppercase tracking-wide"
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontSize: 40,
            fontWeight: 800,
            color: '#e8eef6',
          }}
        >
          {(leagueAny?.name as string) ?? 'WAR ROOM'}
        </h1>
        <span
          className="tracking-[0.25em] uppercase"
          style={{ fontSize: 11, color: '#6a8098' }}
        >
          {(leagueAny?.status as string) ?? '—'} ·{' '}
          {state?.season_type ?? '—'} WK {state?.week ?? '—'}
        </span>
      </div>

      {/* Stat strip */}
      <div className="grid grid-cols-4 gap-3">
        <StatBlock
          label="Teams"
          value={String((leagueAny?.total_rosters as number) ?? '—')}
          sub="dynasty · 1QB · full PPR"
        />
        <StatBlock
          label="Traded Picks"
          value={String(picks?.length ?? '—')}
          sub="live inventory"
        />
        <StatBlock label="Scoring" value="PPR" sub="100/200 rush · 300/400 pass" />
        <StatBlock label="FAAB" value="$500" sub="continuous · Tue waivers" />
      </div>

      {/* Start/sit panel — only during regular season */}
      {state?.season_type === 'regular' && (
        <StartSitPanel rec={startSit} week={state?.week ?? null} />
      )}

      <ActionQueue actions={actions ?? []} />

      {/* Main grid: intel feed + wire */}
      <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 260px' }}>
        <Panel label="INTEL · FINDINGS" accent="#00b8cc">
          <FindingsFeed />
        </Panel>

        <Panel label="WIRE · TRENDING ADDS (24H)" accent="#3a7cc0">
          <TrendingWire trending={trending ?? []} />
        </Panel>
      </div>
    </div>
  )
}

const ACTION_COLOR: Record<WarRoomAction['kind'], string> = {
  TRADE: '#00b8cc',
  WAIVER: '#3a8cd4',
  PICK: '#d4860c',
  LINEUP: '#1a9b5e',
  SYSTEM: '#c93328',
}

function ActionQueue({ actions }: { actions: WarRoomAction[] }) {
  const top = actions.slice(0, 6)
  return (
    <Panel label="ACTION QUEUE · NEXT BEST MOVES" accent="#d4860c">
      {top.length === 0 ? (
        <div className="p-5" style={{ color: '#3d5070', fontSize: 12 }}>
          No live actions. Data source may still be warming.
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-px" style={{ background: '#162035' }}>
          {top.map((action, index) => {
            const color = ACTION_COLOR[action.kind]
            return (
              <motion.div
                key={action.action_id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.035 }}
                style={{
                  background: '#0c1625',
                  padding: '14px 16px',
                  minHeight: 148,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  boxShadow: `inset 3px 0 0 ${color}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color, letterSpacing: '0.12em' }}>
                    {action.kind}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {action.acceptance_score != null && (
                      <span style={{
                        fontSize: 9,
                        fontWeight: 800,
                        letterSpacing: '0.12em',
                        padding: '2px 6px',
                        color: '#060a12',
                        background: color,
                        borderRadius: 1,
                      }}>
                        {action.acceptance_score} FIT
                      </span>
                    )}
                    <span style={{
                      fontSize: 9,
                      fontWeight: 700,
                      letterSpacing: '0.18em',
                      padding: '2px 6px',
                      color: action.urgency === 'HIGH' ? '#060a12' : '#6a8098',
                      background: action.urgency === 'HIGH' ? color : 'transparent',
                      border: `1px solid ${color}55`,
                      borderRadius: 1,
                    }}>
                      {action.urgency}
                    </span>
                  </div>
                </div>
                <div style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: 22,
                  fontWeight: 800,
                  color: '#e8eef6',
                  lineHeight: 1,
                  letterSpacing: '0.03em',
                  textTransform: 'uppercase',
                }}>
                  {action.title}
                </div>
                <div style={{ fontSize: 12, color: '#8aa0b8', lineHeight: 1.45, flex: 1 }}>
                  {action.command}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: '#3d5070' }}>
                    {action.source}
                  </span>
                  <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, color: '#3d5070' }}>
                    {action.confidence} CONF
                  </span>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

function TrendingWire({ trending }: { trending: Array<{ player_id: string; count: number; name: string; position: string; team: string }> }) {
  if (!trending.length) {
    return (
      <div className="p-4" style={{ fontSize: 12, color: '#3d5070' }}>
        No trending data
      </div>
    )
  }
  return (
    <div>
      {trending.slice(0, 14).map((p, i) => {
        const posColor = POS_COLOR[p.position] ?? '#6a8098'
        return (
          <motion.div
            key={p.player_id}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.025 }}
            className="flex items-center gap-2 px-4 py-2"
            style={{ borderBottom: '1px solid #162035', borderLeft: `2px solid ${posColor}` }}
          >
            <span
              style={{
                fontSize: 9,
                fontWeight: 700,
                padding: '1px 4px',
                color: posColor,
                background: `${posColor}18`,
                borderRadius: 1,
                letterSpacing: '0.1em',
                flexShrink: 0,
              }}
            >
              {p.position || '—'}
            </span>
            <span
              style={{ flex: 1, fontSize: 12, color: '#e8eef6', fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {p.name}
            </span>
            <span style={{ fontSize: 11, color: '#3d5070', flexShrink: 0 }}>{p.team}</span>
            <span
              className="font-bold"
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 12,
                color: '#3a7cc0',
                flexShrink: 0,
              }}
            >
              +{p.count}
            </span>
          </motion.div>
        )
      })}
    </div>
  )
}

function StartSitPanel({ rec, week }: { rec: StartSitRec | undefined; week: number | null }) {
  const AMBER = '#d4900a'

  if (!rec) {
    return (
      <div
        style={{
          background: '#0c1625',
          border: '1px solid #162035',
          borderLeft: `3px solid ${AMBER}`,
          borderRadius: 2,
          padding: '10px 16px',
        }}
      >
        <span className="tracking-[0.3em] uppercase font-semibold" style={{ fontSize: 10, color: AMBER }}>
          LINEUP · WK {week ?? '—'} · loading…
        </span>
      </div>
    )
  }

  const projByIdMap: Record<string, { name: string }> = {}
  for (const p of [...rec.projected_starters, ...rec.current_starters]) {
    projByIdMap[p.player_id] = { name: p.name }
  }

  if (rec.changes.length === 0) {
    return (
      <div
        style={{
          background: '#0c1625',
          border: '1px solid #162035',
          borderLeft: `3px solid ${AMBER}`,
          borderRadius: 2,
          padding: '10px 16px',
        }}
      >
        <span className="tracking-[0.3em] uppercase font-semibold" style={{ fontSize: 10, color: AMBER }}>
          LINEUP · WK {rec.week} · OPTIMAL
        </span>
        <span className="ml-3" style={{ fontSize: 11, color: '#6a8098' }}>
          {rec.total_projected_pts.toFixed(1)} proj
        </span>
        {rec.data_quality === 'DEGRADED' && (
          <span className="ml-3" style={{ fontSize: 11, color: AMBER }}>
            DEGRADED · {rec.warnings[0] ?? 'projection fallback active'}
          </span>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        background: '#0c1625',
        border: '1px solid #162035',
        borderLeft: `3px solid ${AMBER}`,
        borderRadius: 2,
      }}
    >
      <div className="px-4 py-2.5 flex items-center gap-4" style={{ borderBottom: '1px solid #162035' }}>
        <span className="tracking-[0.3em] uppercase font-semibold" style={{ fontSize: 10, color: AMBER }}>
          LINEUP · WEEK {rec.week}
        </span>
        <span style={{ fontSize: 11, color: '#e8eef6', fontWeight: 600 }}>
          OPTIMAL · {rec.total_projected_pts.toFixed(1)} PROJ
        </span>
        <span style={{ fontSize: 11, color: '#6a8098' }}>
          vs CURRENT · {rec.current_projected_pts.toFixed(1)} PROJ
        </span>
        {rec.data_quality === 'DEGRADED' && (
          <span style={{ fontSize: 11, color: AMBER }}>
            DEGRADED · {rec.warnings.length} WARNING{rec.warnings.length === 1 ? '' : 'S'}
          </span>
        )}
      </div>
      <div className="px-4 py-2 flex flex-wrap gap-x-6 gap-y-1">
        {rec.changes.map((c) => {
          const startName = projByIdMap[c.start]?.name ?? c.start
          const sitName = projByIdMap[c.sit]?.name ?? c.sit
          return (
            <motion.div
              key={`${c.start}-${c.sit}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2"
            >
              <span style={{ fontSize: 12, color: '#24a870', fontWeight: 600 }}>
                START {startName}
              </span>
              <span style={{ fontSize: 11, color: '#4a9e70' }}>
                +{c.gain.toFixed(1)}
              </span>
              <span style={{ fontSize: 11, color: '#3d5070' }}>
                sit {sitName}
              </span>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

function FindingsFeed() {
  const { data: findings, isLoading } = useQuery({
    queryKey: ['findings'],
    queryFn: () => api.findings(),
    refetchInterval: 5000,
  })

  if (isLoading) {
    return (
      <div className="p-4" style={{ fontSize: 12, color: '#3d5070' }}>
        Loading…
      </div>
    )
  }

  if (!findings?.length) {
    return (
      <div className="p-5">
        <p className="mb-3" style={{ fontSize: 13, color: '#6a8098' }}>
          No findings. Post via:
        </p>
        <code
          className="px-2 py-1"
          style={{
            fontFamily: "'DM Mono', monospace",
            fontSize: 12,
            color: '#00b8cc',
            background: 'rgba(0, 184, 204, 0.08)',
            border: '1px solid rgba(0, 184, 204, 0.2)',
            borderRadius: 2,
          }}
        >
          sffm finding &lt;kind&gt; --body '…'
        </code>
      </div>
    )
  }

  return (
    <div>
      {findings.slice(0, 5).map((f, i) => (
        <motion.div
          key={f.finding_id}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
          className="p-4 flex items-start gap-3"
          style={{ borderBottom: '1px solid #162035' }}
        >
          <span
            className="shrink-0 mt-0.5 px-2 py-0.5 tracking-wider uppercase"
            style={{
              fontSize: 10,
              color: '#00b8cc',
              background: 'rgba(0, 184, 204, 0.08)',
              border: '1px solid rgba(0, 184, 204, 0.2)',
              borderRadius: 2,
            }}
          >
            {f.kind}
          </span>
          <pre
            className="text-xs overflow-auto whitespace-pre-wrap flex-1"
            style={{ color: '#7a8fa8', margin: 0 }}
          >
            {JSON.stringify(f.body, null, 2)}
          </pre>
        </motion.div>
      ))}
    </div>
  )
}
