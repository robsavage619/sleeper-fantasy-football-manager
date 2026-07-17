import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { OpponentAdjustedEntry, PlayerPriceHistory, PositionBidStats, VegasGame } from '@/lib/api'
import { InfoTip } from '@/components/viz'
import { GLOSSARY } from '@/lib/glossary'

const VEGAS_COL_INFO: Record<string, string> = { 'BLOWOUT RISK': GLOSSARY.blowoutRisk }
const FAAB_COL_INFO: Record<string, string> = {
  p25: GLOSSARY.faabPercentile,
  p50: GLOSSARY.faabPercentile,
  p75: GLOSSARY.faabPercentile,
  p90: GLOSSARY.faabPercentile,
}

const POS_COLOR: Record<string, string> = { QB: '#e05030', RB: '#24a870', WR: '#3a8cd4', TE: '#c8820a' }
const AGGRO_COLOR: Record<string, string> = {
  AGGRESSIVE: '#c93328',
  TYPICAL: '#6a8098',
  CONSERVATIVE: '#24a870',
  UNKNOWN: '#3d5070',
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline gap-3 px-5 pt-6 pb-2">
      <h2
        className="uppercase tracking-wide leading-none"
        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 22, fontWeight: 800, color: '#e8eef6' }}
      >
        {children}
      </h2>
      {sub && <span className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>{sub}</span>}
    </div>
  )
}

function PosTag({ position }: { position: string }) {
  const c = POS_COLOR[position] ?? '#6a8098'
  return (
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', padding: '1px 5px', color: c, background: `${c}18`, borderRadius: 1 }}>
      {position}
    </span>
  )
}

function ColHead({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <div className="px-3 py-2 tracking-[0.15em] uppercase" style={{ fontSize: 10, fontWeight: 700, color, borderBottom: `1px solid ${color}30` }}>{children}</div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div style={{ color: '#3d5070', fontSize: 12, padding: '10px 20px' }}>{children}</div>
}

function Loading({ label }: { label: string }) {
  return <div className="py-6 text-center tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>{label}</div>
}

function blowoutColor(risk: number | null): string {
  if (risk == null) return '#3d5070'
  if (risk >= 0.5) return '#c93328'
  if (risk >= 0.25) return '#d4860c'
  return '#24a870'
}

function VegasRow({ g, i }: { g: VegasGame; i: number }) {
  const total = g.implied_total
  return (
    <motion.tr initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.015 }}>
      <td className="py-2 px-3" style={{ fontSize: 13, color: '#e8eef6', width: 60 }}>{g.team}</td>
      <td className="py-2 px-3" style={{ fontSize: 12, color: '#6a8098' }}>{g.is_home ? 'vs' : '@'} {g.opponent}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: total != null ? '#e8eef6' : '#3d5070', fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {total != null ? total.toFixed(1) : '—'}
      </td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
        {g.team_spread != null ? `${g.team_spread > 0 ? '-' : '+'}${Math.abs(g.team_spread).toFixed(1)}` : '—'}
      </td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
        {g.game_total != null ? g.game_total.toFixed(1) : '—'}
      </td>
      <td className="py-2 px-3">
        {g.blowout_risk != null ? (
          <div className="flex items-center gap-2">
            <div style={{ width: 60, height: 5, background: '#0e1526', borderRadius: 1, overflow: 'hidden' }}>
              <motion.div
                style={{ height: '100%', background: blowoutColor(g.blowout_risk), borderRadius: 1 }}
                initial={{ width: 0 }}
                animate={{ width: `${g.blowout_risk * 100}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
            <span className="tabular-nums" style={{ fontSize: 11, color: blowoutColor(g.blowout_risk), fontFamily: "'DM Mono', monospace" }}>
              {(g.blowout_risk * 100).toFixed(0)}%
            </span>
          </div>
        ) : (
          <span style={{ fontSize: 12, color: '#3d5070' }}>—</span>
        )}
      </td>
    </motion.tr>
  )
}

function MoverRow({ m, tone }: { m: PlayerPriceHistory; tone: 'up' | 'down' }) {
  const color = tone === 'up' ? '#24a870' : '#c93328'
  const pct = m.momentum_pct ?? 0
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-3 py-1.5 px-3"
      style={{ borderBottom: '1px solid #0e1526' }}
    >
      {m.meta && <PosTag position={m.meta.position} />}
      <span style={{ fontSize: 13, color: '#e8eef6', width: 150, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {m.meta?.name ?? m.sleeper_id}
      </span>
      <span style={{ fontSize: 11, color: '#6a8098', width: 40 }}>{m.meta?.team ?? '—'}</span>
      <span className="tabular-nums" style={{ flex: 1, textAlign: 'right', fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
      </span>
    </motion.div>
  )
}

function ScheduleLuckRow({ e, tone }: { e: OpponentAdjustedEntry; tone: 'soft' | 'tough' }) {
  const color = tone === 'soft' ? '#c93328' : '#24a870'
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-3 py-1.5 px-3"
      style={{ borderBottom: '1px solid #0e1526' }}
    >
      <PosTag position={e.position} />
      <span style={{ fontSize: 13, color: '#e8eef6', width: 150, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {e.name}
      </span>
      <span style={{ fontSize: 11, color: '#6a8098', width: 40 }}>{e.team}</span>
      <span className="tabular-nums" style={{ fontSize: 11, color: '#3d5070', width: 90 }}>
        {e.raw_fp.toFixed(0)} raw · {e.adjusted_fp.toFixed(0)} adj
      </span>
      <span className="tabular-nums" style={{ flex: 1, textAlign: 'right', fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {e.schedule_luck > 0 ? '+' : ''}{e.schedule_luck.toFixed(1)}
      </span>
    </motion.div>
  )
}

function PositionRow({ stats }: { stats: PositionBidStats }) {
  const c = POS_COLOR[stats.position] ?? '#6a8098'
  const fmt = (v: number | null) => (v != null ? `$${v.toFixed(0)}` : '—')
  return (
    <tr>
      <td className="py-2 px-3" style={{ borderLeft: `2px solid ${c}` }}><PosTag position={stats.position} /></td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{stats.n}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: '#8a9ab0', fontFamily: "'DM Mono', monospace" }}>{fmt(stats.p25)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: '#e8eef6', fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{fmt(stats.p50)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: '#d4860c', fontFamily: "'DM Mono', monospace" }}>{fmt(stats.p75)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: '#c93328', fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{fmt(stats.p90)}</td>
    </tr>
  )
}

export function MarketSignals() {
  const state = useQuery({ queryKey: ['nfl-state'], queryFn: api.nflState, staleTime: 10 * 60 * 1000 })
  // Off-season/preseason reports week 0, which has no odds yet — fall back to week 1
  // (same convention Matchups.tsx uses for its gameday query).
  const week = state.data?.week || 1

  const vegas = useQuery({ queryKey: ['vegas-environment', week], queryFn: () => api.vegasEnvironment(week) })
  const risers = useQuery({ queryKey: ['price-movers', 'up'], queryFn: () => api.priceMovers('up', 12) })
  const fallers = useQuery({ queryKey: ['price-movers', 'down'], queryFn: () => api.priceMovers('down', 12) })
  const faab = useQuery({ queryKey: ['faab-market'], queryFn: api.faabMarket })
  const owners = useQuery({ queryKey: ['owner-profiles'], queryFn: api.ownerProfiles, staleTime: 5 * 60 * 1000 })
  const scheduleLuck = useQuery({
    queryKey: ['opponent-adjusted'],
    queryFn: () => api.opponentAdjusted(),
  })

  const nameByRoster = new Map<number, string>()
  for (const o of owners.data ?? []) nameByRoster.set(o.roster_id, o.display_name || `Roster ${o.roster_id}`)

  const games = [...(vegas.data?.games ?? [])]
    .filter((g) => g.implied_total != null)
    .sort((a, b) => (b.implied_total ?? 0) - (a.implied_total ?? 0))

  const positions = ['QB', 'RB', 'WR', 'TE']
  const posStats = positions.map((p) => faab.data?.by_position[p]).filter((s): s is NonNullable<typeof s> => !!s)

  const ownerRows = Object.entries(faab.data?.by_owner ?? {})
    .map(([rid, profile]) => ({ ...profile, roster_id: Number(rid) }))
    .filter((o) => o.aggressiveness !== 'UNKNOWN')
    .sort((a, b) => (b.median_bid ?? 0) - (a.median_bid ?? 0))

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 40, fontWeight: 800, color: '#e8eef6' }}>
            MARKET SIGNALS
          </h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: '#6a8098' }}>
            VEGAS ENVIRONMENT · PRICE MOMENTUM · FAAB CLEARING PRICE
          </span>
        </div>
      </div>

      {/* Vegas environment */}
      <SectionTitle sub={vegas.data ? `week ${week} · league avg ${vegas.data.league_avg_implied_total?.toFixed(1) ?? '—'} pts` : ''}>
        Vegas Game Environment
      </SectionTitle>
      <div style={{ overflowX: 'auto' }}>
        {games.length === 0 && !vegas.isLoading && (
          <Empty>{vegas.data?.warnings?.[0] ?? `No published odds yet for week ${week}.`}</Empty>
        )}
        {games.length > 0 && (
          <table className="w-full text-left war-table">
            <thead>
              <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                {['TEAM', 'MATCHUP', 'IMPLIED TOTAL', 'SPREAD', 'GAME TOTAL', 'BLOWOUT RISK'].map((h) => (
                  <th key={h} className="py-2 px-3" style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
                    {h}
                    {VEGAS_COL_INFO[h] && <InfoTip text={VEGAS_COL_INFO[h]} label={h} />}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {games.map((g, i) => (
                <VegasRow key={`${g.team}-${g.week}`} g={g} i={i} />
              ))}
            </tbody>
          </table>
        )}
        {vegas.isLoading && <Loading label="PRICING GAME ENVIRONMENT…" />}
      </div>

      {/* Price movers */}
      <SectionTitle sub={risers.data?.snapshot_dates ? `${risers.data.snapshot_dates.length} snapshot(s) collected` : ''}>
        Price Movers
        <InfoTip text={GLOSSARY.momentum} label="momentum" />
      </SectionTitle>
      {(risers.data?.snapshot_dates.length ?? 0) < 2 && !risers.isLoading ? (
        <Empty>
          Only {risers.data?.snapshot_dates.length ?? 0} FantasyCalc snapshot archived so far — momentum needs at
          least 2. This compounds automatically every Tuesday refresh.
        </Empty>
      ) : (
        <div className="grid gap-px pb-2" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
          <div style={{ background: '#060a12' }}>
            <ColHead color="#24a870">RISERS</ColHead>
            {(risers.data?.movers ?? []).length === 0 && !risers.isLoading && <Empty>No risers this cycle.</Empty>}
            {(risers.data?.movers ?? []).map((m) => (
              <MoverRow key={m.sleeper_id} m={m} tone="up" />
            ))}
          </div>
          <div style={{ background: '#060a12' }}>
            <ColHead color="#c93328">FALLERS</ColHead>
            {(fallers.data?.movers ?? []).length === 0 && !fallers.isLoading && <Empty>No fallers this cycle.</Empty>}
            {(fallers.data?.movers ?? []).map((m) => (
              <MoverRow key={m.sleeper_id} m={m} tone="down" />
            ))}
          </div>
        </div>
      )}

      {/* FAAB market */}
      <SectionTitle sub={faab.data ? `${faab.data.n_bids} winning bids · ${faab.data.seasons_covered.length} seasons` : ''}>
        FAAB Clearing Prices
      </SectionTitle>
      <div style={{ overflowX: 'auto' }}>
        {posStats.length === 0 && !faab.isLoading && <Empty>Not enough waiver history yet to price a position.</Empty>}
        {posStats.length > 0 && (
          <table className="w-full text-left war-table">
            <thead>
              <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                {['POS', 'N', 'p25', 'p50', 'p75', 'p90'].map((h) => (
                  <th key={h} className="py-2 px-3" style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.2em' }}>
                    {h}
                    {FAAB_COL_INFO[h] && <InfoTip text={FAAB_COL_INFO[h]} label={h} />}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {posStats.map((s) => (
                <PositionRow key={s.position} stats={s} />
              ))}
            </tbody>
          </table>
        )}
        {faab.isLoading && <Loading label="WALKING LEAGUE HISTORY…" />}
      </div>

      <div className="px-5 pt-3 pb-2 tracking-[0.15em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>
        Owner bid aggressiveness
      </div>
      <div className="px-5 pb-8">
        {ownerRows.length === 0 && !faab.isLoading && <Empty>Not enough per-owner bid history yet.</Empty>}
        {ownerRows.map((o, i) => (
          <motion.div
            key={o.roster_id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.02 }}
            className="flex items-center gap-3 py-1.5"
            style={{ borderBottom: '1px solid #0e1526' }}
          >
            <span style={{ fontSize: 13, color: '#e8eef6', width: 160, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {nameByRoster.get(o.roster_id) ?? `Roster ${o.roster_id}`}
            </span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.1em',
                padding: '2px 7px',
                color: AGGRO_COLOR[o.aggressiveness],
                background: `${AGGRO_COLOR[o.aggressiveness]}18`,
                borderRadius: 1,
              }}
            >
              {o.aggressiveness}
            </span>
            <span className="tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
              median ${o.median_bid?.toFixed(0) ?? '—'}
            </span>
            <span style={{ fontSize: 11, color: '#3d5070' }}>{o.n_bids} bids</span>
          </motion.div>
        ))}
      </div>

      {/* Opponent-adjusted (schedule luck) */}
      <SectionTitle sub={scheduleLuck.data ? `season ${scheduleLuck.data.season} · raw vs DvP-adjusted FP` : ''}>
        Schedule Luck
        <InfoTip text={GLOSSARY.scheduleLuck} label="schedule luck" />
      </SectionTitle>
      <div className="grid gap-px pb-8" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#c93328">SOFTEST SCHEDULE — raw stats most inflated</ColHead>
          {(scheduleLuck.data?.softest_schedule ?? []).length === 0 && !scheduleLuck.isLoading && (
            <Empty>Not enough data this season.</Empty>
          )}
          {(scheduleLuck.data?.softest_schedule ?? []).map((e) => (
            <ScheduleLuckRow key={e.player_id} e={e} tone="soft" />
          ))}
        </div>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#24a870">TOUGHEST SCHEDULE — raw stats most deflated</ColHead>
          {(scheduleLuck.data?.toughest_schedule ?? []).length === 0 && !scheduleLuck.isLoading && (
            <Empty>Not enough data this season.</Empty>
          )}
          {(scheduleLuck.data?.toughest_schedule ?? []).map((e) => (
            <ScheduleLuckRow key={e.player_id} e={e} tone="tough" />
          ))}
        </div>
      </div>
    </div>
  )
}
