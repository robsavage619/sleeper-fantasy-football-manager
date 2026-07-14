import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { api, leagueFormatLabel, type StartSitRec, type TransactionPlan, type WarRoomAction } from '@/lib/api'

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
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60 * 1000 })
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
  const { data: actions, isError: actionsError, error: actionsErrorObj } = useQuery({
    queryKey: ['war-room-actions'],
    queryFn: () => api.warRoomActions(12),
    refetchInterval: 60_000,
  })
  const { data: evals } = useQuery({
    queryKey: ['recommendation-evals'],
    queryFn: () => api.recommendationEvals(8),
    refetchInterval: 120_000,
  })

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
          {league?.name ?? 'WAR ROOM'}
        </h1>
        <span
          className="tracking-[0.25em] uppercase"
          style={{ fontSize: 11, color: '#6a8098' }}
        >
          {league?.status ?? '—'} ·{' '}
          {state?.season_type ?? '—'} WK {state?.week ?? '—'}
        </span>
      </div>

      {/* Stat strip */}
      <div className="grid grid-cols-4 gap-3">
        <StatBlock
          label="Teams"
          value={String(league?.total_rosters ?? '—')}
          sub={leagueFormatLabel(league)}
        />
        <StatBlock
          label="Traded Picks"
          value={String(picks?.length ?? '—')}
          sub="live inventory"
        />
        <StatBlock
          label="Season"
          value={league?.season ?? '—'}
          sub={league ? `${league.status} · ${state?.season_type ?? '—'}` : '—'}
        />
        <StatBlock
          label="FAAB Left"
          value={me ? `$${me.faab_remaining}` : '—'}
          sub={me ? `of $${me.faab_budget} budget` : '—'}
        />
      </div>

      {evals && evals.overall_status === 'DEGRADED' && (
        <div
          className="px-4 py-3"
          style={{
            background: '#0c1625',
            border: '1px solid rgba(212, 134, 12, 0.35)',
            borderLeft: '3px solid #d4860c',
            borderRadius: 2,
          }}
        >
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <span
              className="tracking-[0.3em] uppercase font-semibold"
              style={{ color: '#d4860c', fontSize: 10 }}
            >
              RECOMMENDATION QUALITY · DEGRADED
            </span>
            <span style={{ color: '#b8c6d8', fontSize: 12 }}>
              {evals.findings[0]?.detail}
            </span>
            <span
              className="tracking-wider uppercase"
              style={{ color: '#6a8098', fontSize: 10 }}
            >
              {evals.findings.length} finding{evals.findings.length === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      )}

      {/* Start/sit panel — only during regular season */}
      {state?.season_type === 'regular' && (
        <StartSitPanel rec={startSit} week={state?.week ?? null} />
      )}

      <ActionQueue
        actions={actions ?? []}
        isError={actionsError}
        errorMessage={actionsErrorObj instanceof Error ? actionsErrorObj.message : null}
      />

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

function ActionQueue({
  actions,
  isError,
  errorMessage,
}: {
  actions: WarRoomAction[]
  isError?: boolean
  errorMessage?: string | null
}) {
  const top = actions.slice(0, 6)
  const [plan, setPlan] = useState<TransactionPlan | null>(null)
  const [planningId, setPlanningId] = useState<string | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)

  async function buildPlan(action: WarRoomAction) {
    setPlanningId(action.action_id)
    setPlanError(null)
    try {
      setPlan(await api.transactionPlan({
        action_id: action.action_id,
        kind: action.kind,
        command: action.command,
      }))
    } catch (e) {
      setPlanError(e instanceof Error ? e.message : 'Failed to build transaction plan')
    } finally {
      setPlanningId(null)
    }
  }

  return (
    <Panel label="ACTION QUEUE · NEXT BEST MOVES" accent="#d4860c">
      {planError && (
        <div
          className="px-4 py-2.5"
          style={{ borderBottom: '1px solid #162035', color: '#e07060', background: 'rgba(201, 51, 40, 0.06)', fontSize: 12 }}
        >
          {planError}
        </div>
      )}
      {isError ? (
        <div
          className="p-5"
          style={{ color: '#e07060', background: 'rgba(201, 51, 40, 0.06)', fontSize: 12 }}
        >
          Failed to load action queue{errorMessage ? ` · ${errorMessage}` : ''}
        </div>
      ) : top.length === 0 ? (
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
                  <button
                    onClick={() => void buildPlan(action)}
                    style={{
                      border: '1px solid #24344f',
                      background: planningId === action.action_id ? '#162035' : 'transparent',
                      color: '#6a8098',
                      fontFamily: "'DM Mono', monospace",
                      fontSize: 10,
                      padding: '2px 6px',
                      borderRadius: 2,
                      cursor: 'pointer',
                    }}
                  >
                    {planningId === action.action_id ? '...' : 'PLAN'}
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
      {plan && (
        <div className="px-4 py-3" style={{ borderTop: '1px solid #162035', background: '#09111f' }}>
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <span
              className="tracking-[0.24em] uppercase"
              style={{ color: '#d4860c', fontSize: 10, fontWeight: 700 }}
            >
              {plan.status}
            </span>
            <span style={{ color: '#e8eef6', fontFamily: "'DM Mono', monospace", fontSize: 11 }}>
              {plan.confirm_phrase}
            </span>
          </div>
          <div style={{ color: '#8aa0b8', fontSize: 12, lineHeight: 1.55 }}>
            {plan.steps.join(' · ')}
          </div>
          <div className="mt-2" style={{ color: '#c93328', fontSize: 11 }}>
            {plan.warnings.join(' · ')}
          </div>
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

function relativeTime(iso: string | undefined): string {
  if (!iso) return ''
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

function summarizeFinding(kind: string, body: Record<string, unknown>): {
  title: string
  detail: string
} {
  const s = (v: unknown) => (v == null ? '' : String(v))
  switch (kind) {
    case 'narrative':
      return { title: 'Weekly narrative', detail: s(body.narrative) }
    case 'trade':
      return {
        title: `Trade — ${s(body.partner) || 'target'}`,
        detail:
          body.send || body.receive
            ? `Send ${s(body.send)} → Get ${s(body.receive)}. ${s(body.rationale)}`
            : s(body.rationale),
      }
    case 'waiver':
      return {
        title: `Waiver — ${s(body.player)}`,
        detail: `${body.faab_bid ? `Bid ${s(body.faab_bid)}` : ''}${
          body.drop ? ` · drop ${s(body.drop)}` : ''
        }. ${s(body.rationale)}`,
      }
    case 'draft':
      return { title: `Draft — ${s(body.pick)}`, detail: s(body.rationale) }
    case 'prospect':
      return { title: `Prospect — ${s(body.name)}`, detail: `${s(body.verdict)}. ${s(body.rationale)}` }
    case 'lineup':
      return {
        title: `Lineup — start ${s(body.start)}`,
        detail: `Sit ${s(body.sit)}. ${s(body.rationale)}`,
      }
    default: {
      const detail = Object.entries(body)
        .filter(([k]) => k !== 'generated_at' && k !== 'data_quality_ack')
        .map(([k, v]) => `${k}: ${s(v)}`)
        .join(' · ')
      return { title: kind, detail }
    }
  }
}

function FindingsFeed() {
  const { data: findings, isLoading } = useQuery({
    queryKey: ['findings'],
    queryFn: () => api.findings(),
    refetchInterval: 60_000,
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
      {findings.slice(0, 6).map((f, i) => {
        const body = (f.body ?? {}) as Record<string, unknown>
        const { title, detail } = summarizeFinding(f.kind, body)
        const stamp = relativeTime(body.generated_at as string | undefined)
        return (
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
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <span style={{ fontSize: 13, fontWeight: 600, color: '#c9d6e8' }}>{title}</span>
                {stamp && <span style={{ fontSize: 10, color: '#3d5070' }}>{stamp}</span>}
              </div>
              {detail && (
                <p className="mt-1" style={{ fontSize: 12, color: '#7a8fa8', lineHeight: 1.5 }}>
                  {detail}
                </p>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
