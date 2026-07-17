import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { MispricingEntry, OpponentAdjustedEntry, PlayerPriceHistory, PositionBidStats, RegressionFlag, VegasGame } from '@/lib/api'
import {
  ColHead,
  Empty,
  INK,
  InfoTip,
  Loading,
  POS_COLOR,
  PosTag,
  RangeBar,
  RankedBar,
  SectionTitle,
  Sparkline,
  STATUS,
} from '@/components/viz'
import { GLOSSARY } from '@/lib/glossary'

const EDGE_COL_INFO: Record<string, string> = {
  EDGE: GLOSSARY.edgePct,
  'MKT VAL': GLOSSARY.leverage,
  'VALUE GAP': GLOSSARY.valueGap,
}
const REG_COL_INFO: Record<string, string> = { 'TD±': GLOSSARY.tdOverExpected }
const CONTENTION_COL_INFO: Record<string, string> = { PLAYOFF: GLOSSARY.titleOdds }
const VEGAS_COL_INFO: Record<string, string> = { 'BLOWOUT RISK': GLOSSARY.blowoutRisk }
const FAAB_COL_INFO: Record<string, string> = {
  p25: GLOSSARY.faabPercentile,
  p50: GLOSSARY.faabPercentile,
  p75: GLOSSARY.faabPercentile,
  p90: GLOSSARY.faabPercentile,
}

const LABEL_COLOR: Record<string, string> = {
  'WIN-NOW': '#e0a030',
  SUSTAIN: '#24a870',
  RETOOL: '#3a8cd4',
  REBUILD: '#8a94a6',
  HOLD: '#6a8098',
}
const AGGRO_COLOR: Record<string, string> = {
  AGGRESSIVE: STATUS.bad,
  TYPICAL: INK.muted,
  CONSERVATIVE: STATUS.good,
  UNKNOWN: INK.dim,
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

function Stat({ label, value, accent, info }: { label: string; value: string; accent: string; info?: string }) {
  return (
    <div>
      <div className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: INK.dim }}>
        {label}
        {info && <InfoTip text={info} label={label} />}
      </div>
      <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 34, fontWeight: 800, color: accent, lineHeight: 1 }}>
        {value}
      </div>
    </div>
  )
}

// ── mispricing (buy/sell) ────────────────────────────────────────────────────

function EdgeTable({ rows, tone }: { rows: MispricingEntry[]; tone: 'buy' | 'sell' }) {
  const color = tone === 'buy' ? STATUS.good : STATUS.bad
  if (rows.length === 0)
    return <Empty>No {tone === 'buy' ? 'buy' : 'sell'} edges this cycle.</Empty>
  return (
    <table className="w-full text-left war-table">
      <thead>
        <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
          {['PLAYER', 'POS', 'TEAM', 'EDGE', 'MKT VAL', 'VALUE GAP', ''].map((h) => (
            <th key={h} className="py-2 px-3" style={{ color: INK.dim, fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
              {h}
              {EDGE_COL_INFO[h] && <InfoTip text={EDGE_COL_INFO[h]} label={h} />}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((e, i) => (
          <motion.tr key={e.player_id + i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
            <td className="py-2 px-3" style={{ borderLeft: `2px solid ${color}`, fontSize: 13, color: INK.primary }}>{e.name}</td>
            <td className="py-2 px-3"><PosTag position={e.position} /></td>
            <td className="py-2 px-3" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{e.team}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
              {e.edge_pct > 0 ? '+' : ''}{e.edge_pct.toFixed(1)}%
            </td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{e.market_value != null ? e.market_value.toFixed(0) : '—'}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: e.value_gap != null ? color : INK.dim, fontFamily: "'DM Mono', monospace" }}>
              {e.value_gap != null ? `${e.value_gap > 0 ? '+' : ''}${e.value_gap.toFixed(0)}` : '—'}
            </td>
            <td className="py-2 px-3">
              <Link
                to={`/trades?targetPlayer=${encodeURIComponent(e.player_id)}&targetName=${encodeURIComponent(e.name)}&targetPos=${e.position}`}
                style={{ fontSize: 10, color: STATUS.info, letterSpacing: '0.08em', textDecoration: 'none', whiteSpace: 'nowrap' }}
              >
                TRADE FOR →
              </Link>
            </td>
          </motion.tr>
        ))}
      </tbody>
    </table>
  )
}

/** Simple bucketed histogram of edge_pct magnitude — how skewed the board is. */
function EdgeDistribution({ buys, sells }: { buys: MispricingEntry[]; sells: MispricingEntry[] }) {
  const all = [...buys, ...sells]
  if (all.length === 0) return <Empty>No mispricing data to distribute.</Empty>
  const buckets = [
    { lo: -Infinity, hi: -50, label: '<-50%' },
    { lo: -50, hi: -25, label: '-50..-25' },
    { lo: -25, hi: -10, label: '-25..-10' },
    { lo: -10, hi: 0, label: '-10..0' },
    { lo: 0, hi: 10, label: '0..10' },
    { lo: 10, hi: 25, label: '10..25' },
    { lo: 25, hi: 50, label: '25..50' },
    { lo: 50, hi: Infinity, label: '>50%' },
  ]
  const counts = buckets.map((b) => all.filter((e) => e.edge_pct >= b.lo && e.edge_pct < b.hi).length)
  const max = Math.max(1, ...counts)
  return (
    <div className="px-5 pb-6">
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 90 }}>
        {buckets.map((b, i) => {
          const h = Math.max(2, (counts[i] / max) * 84)
          const color = b.hi <= 0 ? STATUS.good : b.lo >= 0 ? STATUS.bad : INK.muted
          return (
            <div key={b.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <span style={{ fontSize: 9, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{counts[i] || ''}</span>
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: h }}
                style={{ width: '100%', background: color, borderRadius: '2px 2px 0 0' }}
              />
            </div>
          )
        })}
      </div>
      <div className="flex justify-between" style={{ marginTop: 4 }}>
        {buckets.map((b) => (
          <span key={b.label} style={{ flex: 1, textAlign: 'center', fontSize: 8, color: INK.dim }}>{b.label}</span>
        ))}
      </div>
      <div style={{ marginTop: 4, fontSize: 10, color: INK.dim }}>
        Edge % distribution across {all.length} scored players — how far league-scoring value strays from generic PPR.
      </div>
    </div>
  )
}

function RegTable({ rows, tone }: { rows: RegressionFlag[]; tone: 'buy' | 'sell' }) {
  const color = tone === 'buy' ? STATUS.good : STATUS.bad
  if (rows.length === 0) return <Empty>Nothing flagged.</Empty>
  return (
    <table className="w-full text-left war-table">
      <thead>
        <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
          {['PLAYER', 'POS', 'TDs', 'xTD', 'TD±'].map((h) => (
            <th key={h} className="py-2 px-3" style={{ color: INK.dim, fontSize: 10, fontWeight: 600, letterSpacing: '0.2em' }}>
              {h}
              {REG_COL_INFO[h] && <InfoTip text={REG_COL_INFO[h]} label={h} />}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((f, i) => (
          <motion.tr key={f.player_id + i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
            <td className="py-2 px-3" style={{ borderLeft: `2px solid ${color}`, fontSize: 13, color: INK.primary }}>{f.name}</td>
            <td className="py-2 px-3"><PosTag position={f.position} /></td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{f.total_tds.toFixed(0)}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{f.expected_tds.toFixed(1)}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{f.td_oe > 0 ? '+' : ''}{f.td_oe.toFixed(1)}</td>
          </motion.tr>
        ))}
      </tbody>
    </table>
  )
}

// ── vegas / movers / faab / schedule luck ────────────────────────────────────

function blowoutColor(risk: number | null): string {
  if (risk == null) return INK.dim
  if (risk >= 0.5) return STATUS.bad
  if (risk >= 0.25) return STATUS.warn
  return STATUS.good
}

function VegasRow({ g, i }: { g: VegasGame; i: number }) {
  const total = g.implied_total
  return (
    <motion.tr initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.015 }}>
      <td className="py-2 px-3" style={{ fontSize: 13, color: INK.primary, width: 60 }}>{g.team}</td>
      <td className="py-2 px-3" style={{ fontSize: 12, color: INK.muted }}>{g.is_home ? 'vs' : '@'} {g.opponent}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: total != null ? INK.primary : INK.dim, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {total != null ? total.toFixed(1) : '—'}
      </td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>
        {g.team_spread != null ? `${g.team_spread > 0 ? '-' : '+'}${Math.abs(g.team_spread).toFixed(1)}` : '—'}
      </td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>
        {g.game_total != null ? g.game_total.toFixed(1) : '—'}
      </td>
      <td className="py-2 px-3">
        {g.blowout_risk != null ? (
          <div className="flex items-center gap-2">
            <div style={{ width: 60, height: 5, background: '#0e1526', borderRadius: 1, overflow: 'hidden' }}>
              <motion.div style={{ height: '100%', background: blowoutColor(g.blowout_risk), borderRadius: 1 }} initial={{ width: 0 }} animate={{ width: `${g.blowout_risk * 100}%` }} transition={{ duration: 0.4 }} />
            </div>
            <span className="tabular-nums" style={{ fontSize: 11, color: blowoutColor(g.blowout_risk), fontFamily: "'DM Mono', monospace" }}>
              {(g.blowout_risk * 100).toFixed(0)}%
            </span>
          </div>
        ) : (
          <span style={{ fontSize: 12, color: INK.dim }}>—</span>
        )}
      </td>
    </motion.tr>
  )
}

function MoverRow({ m, tone }: { m: PlayerPriceHistory; tone: 'up' | 'down' }) {
  const color = tone === 'up' ? STATUS.good : STATUS.bad
  const p = m.momentum_pct ?? 0
  const values = m.points.map((pt) => pt.value)
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-3 py-1.5 px-3"
      style={{ borderBottom: '1px solid #0e1526' }}
    >
      {m.meta && <PosTag position={m.meta.position} />}
      <span style={{ fontSize: 13, color: INK.primary, width: 140, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {m.meta?.name ?? m.sleeper_id}
      </span>
      <span style={{ fontSize: 11, color: INK.muted, width: 36 }}>{m.meta?.team ?? '—'}</span>
      <Sparkline values={values} width={70} height={22} color={color} />
      <span className="tabular-nums" style={{ flex: 1, textAlign: 'right', fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {p > 0 ? '+' : ''}{p.toFixed(1)}%
      </span>
    </motion.div>
  )
}

function ScheduleLuckRow({ e, tone }: { e: OpponentAdjustedEntry; tone: 'soft' | 'tough' }) {
  const color = tone === 'soft' ? STATUS.bad : STATUS.good
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-3 py-1.5 px-3"
      style={{ borderBottom: '1px solid #0e1526' }}
    >
      <PosTag position={e.position} />
      <span style={{ fontSize: 13, color: INK.primary, width: 150, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {e.name}
      </span>
      <span style={{ fontSize: 11, color: INK.muted, width: 40 }}>{e.team}</span>
      <span className="tabular-nums" style={{ fontSize: 11, color: INK.dim, width: 90 }}>
        {e.raw_fp.toFixed(0)} raw · {e.adjusted_fp.toFixed(0)} adj
      </span>
      <span className="tabular-nums" style={{ flex: 1, textAlign: 'right', fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
        {e.schedule_luck > 0 ? '+' : ''}{e.schedule_luck.toFixed(1)}
      </span>
    </motion.div>
  )
}

function PositionRow({ stats }: { stats: PositionBidStats }) {
  const c = POS_COLOR[stats.position] ?? INK.muted
  const fmt = (v: number | null) => (v != null ? `$${v.toFixed(0)}` : '—')
  return (
    <tr>
      <td className="py-2 px-3" style={{ borderLeft: `2px solid ${c}` }}><PosTag position={stats.position} /></td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{stats.n}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: INK.secondary, fontFamily: "'DM Mono', monospace" }}>{fmt(stats.p25)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: INK.primary, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{fmt(stats.p50)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: STATUS.warn, fontFamily: "'DM Mono', monospace" }}>{fmt(stats.p75)}</td>
      <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color: STATUS.bad, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{fmt(stats.p90)}</td>
    </tr>
  )
}

/** p25 → p90 range bar per position — the FAAB clearing-price spread at a glance. */
function FaabRangeChart({ stats }: { stats: PositionBidStats[] }) {
  if (stats.length === 0) return null
  const max = Math.max(1, ...stats.map((s) => s.p90 ?? 0))
  return (
    <div className="px-5 pb-2" style={{ display: 'grid', gap: 10 }}>
      {stats.map((s) => (
        <div key={s.position} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 40, flexShrink: 0 }}><PosTag position={s.position} /></div>
          <div style={{ flex: 1 }}>
            <RangeBar floor={s.p25 ?? 0} median={s.p50 ?? 0} ceiling={s.p90 ?? s.p75 ?? 0} max={max} color={POS_COLOR[s.position]} />
          </div>
        </div>
      ))}
    </div>
  )
}

const TABS = ['MISPRICING', 'REGRESSION', 'TITLE & CONTENTION', 'VEGAS & MOVERS', 'FAAB & SCHEDULE'] as const
type Tab = (typeof TABS)[number]

export function Market() {
  const [searchParams] = useSearchParams()
  const initialTab = searchParams.get('tab')
  const [tab, setTab] = useState<Tab>(
    initialTab && (TABS as readonly string[]).includes(initialTab) ? (initialTab as Tab) : 'MISPRICING',
  )
  const focusPlayerId = searchParams.get('player')
  const focusPlayerName = searchParams.get('name')

  const mispricing = useQuery({ queryKey: ['mispricing'], queryFn: () => api.mispricing(12) })
  const sim = useQuery({ queryKey: ['season-sim'], queryFn: () => api.seasonSim(3000) })
  const contention = useQuery({ queryKey: ['contention'], queryFn: api.contention })
  const regression = useQuery({ queryKey: ['regression'], queryFn: () => api.regression(10) })
  const owners = useQuery({ queryKey: ['owner-profiles'], queryFn: api.ownerProfiles, staleTime: 5 * 60 * 1000 })

  const state = useQuery({ queryKey: ['nfl-state'], queryFn: api.nflState, staleTime: 10 * 60 * 1000 })
  const week = state.data?.week || 1
  const vegas = useQuery({ queryKey: ['vegas-environment', week], queryFn: () => api.vegasEnvironment(week) })
  const risers = useQuery({ queryKey: ['price-movers', 'up'], queryFn: () => api.priceMovers('up', 12) })
  const fallers = useQuery({ queryKey: ['price-movers', 'down'], queryFn: () => api.priceMovers('down', 12) })
  const faab = useQuery({ queryKey: ['faab-market'], queryFn: api.faabMarket })
  const scheduleLuck = useQuery({ queryKey: ['opponent-adjusted'], queryFn: () => api.opponentAdjusted() })
  const focusTrend = useQuery({
    queryKey: ['price-trend', focusPlayerId],
    queryFn: () => api.playerPriceTrend(focusPlayerId!),
    enabled: !!focusPlayerId,
  })

  const nameByRoster = new Map<number, string>()
  for (const o of owners.data ?? []) nameByRoster.set(o.roster_id, o.display_name || `Roster ${o.roster_id}`)
  const rosterName = (id: number) => nameByRoster.get(id) ?? `Roster ${id}`

  const me = sim.data?.teams.find((t) => t.is_me)
  const maxTitle = Math.max(0.01, ...(sim.data?.teams ?? []).map((t) => t.title_odds))

  const games = [...(vegas.data?.games ?? [])].filter((g) => g.implied_total != null).sort((a, b) => (b.implied_total ?? 0) - (a.implied_total ?? 0))
  const positions = ['QB', 'RB', 'WR', 'TE']
  const posStats = positions.map((p) => faab.data?.by_position[p]).filter((s): s is NonNullable<typeof s> => !!s)
  const ownerRows = Object.entries(faab.data?.by_owner ?? {})
    .map(([rid, profile]) => ({ ...profile, roster_id: Number(rid) }))
    .filter((o) => o.aggressiveness !== 'UNKNOWN')
    .sort((a, b) => (b.median_bid ?? 0) - (a.median_bid ?? 0))

  const regRows = [
    ...(regression.data?.sell_high ?? []).map((r) => ({ id: r.player_id, label: r.name, avatar: null, value: r.td_oe, sub: r.position })),
    ...(regression.data?.buy_low ?? []).map((r) => ({ id: r.player_id, label: r.name, avatar: null, value: r.td_oe, sub: r.position })),
  ].sort((a, b) => b.value - a.value)

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 40, fontWeight: 800, color: INK.primary }}>
            MARKET
          </h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: INK.muted }}>
            SCORING-LEVERAGE · VEGAS · PRICE MOMENTUM · FAAB · SCHEDULE LUCK
          </span>
        </div>
      </div>

      {focusPlayerId && (
        <div className="px-5 py-3" style={{ background: '#070d18', borderBottom: '1px solid #162035' }}>
          <div className="flex items-center gap-4">
            <span className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: STATUS.info }}>PLAYER FOCUS</span>
            <span style={{ fontSize: 14, color: INK.primary, fontWeight: 600 }}>{focusPlayerName ?? focusTrend.data?.meta?.name ?? focusPlayerId}</span>
            {focusTrend.data && (
              <>
                <Sparkline values={focusTrend.data.points.map((p) => p.value)} width={100} height={26} />
                <span style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>
                  {focusTrend.data.momentum_pct != null ? `${focusTrend.data.momentum_pct > 0 ? '+' : ''}${focusTrend.data.momentum_pct.toFixed(1)}% momentum` : focusTrend.data.note}
                </span>
              </>
            )}
            {focusTrend.isLoading && <span style={{ fontSize: 11, color: INK.dim }}>loading trend…</span>}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 px-5 py-3" style={{ borderBottom: '1px solid #162035', background: '#09111f' }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="tracking-widest uppercase font-bold transition-all"
            style={{
              fontSize: 10.5,
              padding: '6px 12px',
              background: tab === t ? '#00b8cc' : 'transparent',
              color: tab === t ? '#060a12' : INK.muted,
              border: `1px solid ${tab === t ? '#00b8cc' : '#162035'}`,
              borderRadius: 2,
              cursor: 'pointer',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'MISPRICING' && (
        <>
          <SectionTitle sub={mispricing.data ? mispricing.data.calibration : 'our scoring vs generic PPR'}>League-Specific Mispricing</SectionTitle>
          <div className="grid gap-px" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.good}>BUY — market cheap for us</ColHead>
              <EdgeTable rows={mispricing.data?.buys ?? []} tone="buy" />
            </div>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.bad}>SELL — market overpays</ColHead>
              <EdgeTable rows={mispricing.data?.sells ?? []} tone="sell" />
            </div>
          </div>
          {mispricing.isLoading && <Loading label="RE-SCORING UNDER LEAGUE RULES…" />}
          {mispricing.data?.market_source === 'none' && (
            <div className="px-5 py-2" style={{ color: STATUS.warn, fontSize: 11 }}>Market feed down — edges shown without market value.</div>
          )}
          <SectionTitle sub="how skewed the board is">Edge Magnitude Distribution</SectionTitle>
          <EdgeDistribution buys={mispricing.data?.buys ?? []} sells={mispricing.data?.sells ?? []} />
        </>
      )}

      {tab === 'REGRESSION' && (
        <>
          <SectionTitle sub="TD-over-expected">Regression Watch</SectionTitle>
          <div className="grid gap-px" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.bad}>SELL-HIGH — rode TD variance up</ColHead>
              <RegTable rows={regression.data?.sell_high ?? []} tone="sell" />
            </div>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.good}>BUY-LOW — unlucky on real usage</ColHead>
              <RegTable rows={regression.data?.buy_low ?? []} tone="buy" />
            </div>
          </div>
          {regression.isLoading && <Loading label="MODELING RED-ZONE OPPORTUNITY…" />}
          <SectionTitle sub="actual minus expected TDs, ranked">TD Over/Under Diverging</SectionTitle>
          <div className="px-5 pb-8">
            {regRows.length === 0 ? (
              <Empty>No regression flags this cycle.</Empty>
            ) : (
              <RankedBar
                items={regRows}
                diverging
                colorFor={(v) => (v >= 0 ? STATUS.bad : STATUS.good)}
                format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`}
              />
            )}
          </div>
        </>
      )}

      {tab === 'TITLE & CONTENTION' && (
        <>
          <SectionTitle sub={sim.data ? `${sim.data.schedule_source} · ${sim.data.n_sims} sims` : ''}>Title Equity</SectionTitle>
          {me && (
            <div className="px-5 pb-2 flex flex-wrap gap-6">
              <Stat label="MY TITLE ODDS" value={pct(me.title_odds)} accent={STATUS.info} info={GLOSSARY.titleOdds} />
              <Stat label="MY PLAYOFF ODDS" value={pct(me.playoff_odds)} accent={STATUS.good} info={GLOSSARY.titleOdds} />
              <Stat label="PROJ WINS" value={me.avg_wins.toFixed(1)} accent={INK.muted} />
              <Stat label="STRENGTH/WK" value={me.strength.toFixed(0)} accent={INK.muted} info={GLOSSARY.leverage} />
            </div>
          )}
          <div className="px-5 pb-3">
            {(sim.data?.teams ?? []).map((t, i) => (
              <div key={t.roster_id} className="flex items-center gap-3 py-1">
                <span style={{ width: 150, fontSize: 12, color: t.is_me ? STATUS.info : '#b8c6d8', fontWeight: t.is_me ? 600 : 400, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {i + 1}. {rosterName(t.roster_id)}{t.is_me ? ' ◆' : ''}
                </span>
                <div style={{ flex: 1, height: 6, background: '#0e1526', borderRadius: 1, overflow: 'hidden', maxWidth: 360 }}>
                  <motion.div style={{ height: '100%', background: t.is_me ? STATUS.info : '#2d4a6a', borderRadius: 1 }} initial={{ width: 0 }} animate={{ width: `${(t.title_odds / maxTitle) * 100}%` }} transition={{ duration: 0.5 }} />
                </div>
                <span className="tabular-nums" style={{ width: 48, fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace", textAlign: 'right' }}>{pct(t.title_odds)}</span>
              </div>
            ))}
            {sim.isLoading && <Loading label="SIMULATING SEASON…" />}
          </div>

          <SectionTitle sub="buyer / seller classifier">Contention Windows</SectionTitle>
          <div style={{ overflowX: 'auto' }}>
            <table className="w-full text-left war-table">
              <thead>
                <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                  {['TEAM', 'WINDOW', 'PLAYOFF', 'CORE AGE', 'YOUTH', 'WANTS', 'SHOULD MOVE'].map((h) => (
                    <th key={h} className="py-2 px-3" style={{ color: INK.dim, fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
                      {h}
                      {CONTENTION_COL_INFO[h] && <InfoTip text={CONTENTION_COL_INFO[h]} label={h} />}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(contention.data?.windows ?? []).map((w, i) => (
                  <motion.tr key={w.roster_id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
                    <td className="py-2 px-3" style={{ fontSize: 13, color: w.is_me ? STATUS.info : INK.primary, fontWeight: w.is_me ? 600 : 400, whiteSpace: 'nowrap' }}>{rosterName(w.roster_id)}{w.is_me ? ' ◆' : ''}</td>
                    <td className="py-2 px-3">
                      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 7px', color: LABEL_COLOR[w.label], background: `${LABEL_COLOR[w.label]}18`, borderRadius: 1, whiteSpace: 'nowrap' }}>{w.label}</span>
                    </td>
                    <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{pct(w.playoff_odds)}</td>
                    <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{w.core_age.toFixed(1)}</td>
                    <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>{pct(w.young_share)}</td>
                    <td className="py-2 px-3" style={{ fontSize: 11, color: INK.secondary, maxWidth: 200 }}>{w.seeking}</td>
                    <td className="py-2 px-3" style={{ fontSize: 11, color: INK.secondary, maxWidth: 200 }}>{w.shedding}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
            {contention.isLoading && <Loading label="CLASSIFYING WINDOWS…" />}
          </div>
          <div style={{ height: 16 }} />
        </>
      )}

      {tab === 'VEGAS & MOVERS' && (
        <>
          <SectionTitle sub={vegas.data ? `week ${week} · league avg ${vegas.data.league_avg_implied_total?.toFixed(1) ?? '—'} pts` : ''}>
            Vegas Game Environment
          </SectionTitle>
          <div style={{ overflowX: 'auto' }}>
            {games.length === 0 && !vegas.isLoading && <Empty>{vegas.data?.warnings?.[0] ?? `No published odds yet for week ${week}.`}</Empty>}
            {games.length > 0 && (
              <table className="w-full text-left war-table">
                <thead>
                  <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                    {['TEAM', 'MATCHUP', 'IMPLIED TOTAL', 'SPREAD', 'GAME TOTAL', 'BLOWOUT RISK'].map((h) => (
                      <th key={h} className="py-2 px-3" style={{ color: INK.dim, fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
                        {h}
                        {VEGAS_COL_INFO[h] && <InfoTip text={VEGAS_COL_INFO[h]} label={h} />}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {games.map((g, i) => <VegasRow key={`${g.team}-${g.week}`} g={g} i={i} />)}
                </tbody>
              </table>
            )}
            {vegas.isLoading && <Loading label="PRICING GAME ENVIRONMENT…" />}
          </div>

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
                <ColHead color={STATUS.good}>RISERS</ColHead>
                {(risers.data?.movers ?? []).length === 0 && !risers.isLoading && <Empty>No risers this cycle.</Empty>}
                {(risers.data?.movers ?? []).map((m) => <MoverRow key={m.sleeper_id} m={m} tone="up" />)}
              </div>
              <div style={{ background: '#060a12' }}>
                <ColHead color={STATUS.bad}>FALLERS</ColHead>
                {(fallers.data?.movers ?? []).length === 0 && !fallers.isLoading && <Empty>No fallers this cycle.</Empty>}
                {(fallers.data?.movers ?? []).map((m) => <MoverRow key={m.sleeper_id} m={m} tone="down" />)}
              </div>
            </div>
          )}
          <div style={{ height: 16 }} />
        </>
      )}

      {tab === 'FAAB & SCHEDULE' && (
        <>
          <SectionTitle sub={faab.data ? `${faab.data.n_bids} winning bids · ${faab.data.seasons_covered.length} seasons` : ''}>
            FAAB Clearing Prices
          </SectionTitle>
          <FaabRangeChart stats={posStats} />
          <div style={{ overflowX: 'auto' }}>
            {posStats.length === 0 && !faab.isLoading && <Empty>Not enough waiver history yet to price a position.</Empty>}
            {posStats.length > 0 && (
              <table className="w-full text-left war-table">
                <thead>
                  <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                    {['POS', 'N', 'p25', 'p50', 'p75', 'p90'].map((h) => (
                      <th key={h} className="py-2 px-3" style={{ color: INK.dim, fontSize: 10, fontWeight: 600, letterSpacing: '0.2em' }}>
                        {h}
                        {FAAB_COL_INFO[h] && <InfoTip text={FAAB_COL_INFO[h]} label={h} />}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {posStats.map((s) => <PositionRow key={s.position} stats={s} />)}
                </tbody>
              </table>
            )}
            {faab.isLoading && <Loading label="WALKING LEAGUE HISTORY…" />}
          </div>

          <div className="px-5 pt-3 pb-2 tracking-[0.15em] uppercase" style={{ fontSize: 10, color: INK.dim }}>
            Owner bid aggressiveness
          </div>
          <div className="px-5 pb-6">
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
                <span style={{ fontSize: 13, color: INK.primary, width: 160, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {nameByRoster.get(o.roster_id) ?? `Roster ${o.roster_id}`}
                </span>
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 7px', color: AGGRO_COLOR[o.aggressiveness], background: `${AGGRO_COLOR[o.aggressiveness]}18`, borderRadius: 1 }}>
                  {o.aggressiveness}
                </span>
                <span className="tabular-nums" style={{ fontSize: 12, color: INK.muted, fontFamily: "'DM Mono', monospace" }}>
                  median ${o.median_bid?.toFixed(0) ?? '—'}
                </span>
                <span style={{ fontSize: 11, color: INK.dim }}>{o.n_bids} bids</span>
              </motion.div>
            ))}
          </div>

          <SectionTitle sub={scheduleLuck.data ? `season ${scheduleLuck.data.season} · raw vs DvP-adjusted FP` : ''}>
            Schedule Luck
            <InfoTip text={GLOSSARY.scheduleLuck} label="schedule luck" />
          </SectionTitle>
          <div className="grid gap-px pb-8" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.bad}>SOFTEST SCHEDULE — raw stats most inflated</ColHead>
              {(scheduleLuck.data?.softest_schedule ?? []).length === 0 && !scheduleLuck.isLoading && <Empty>Not enough data this season.</Empty>}
              {(scheduleLuck.data?.softest_schedule ?? []).map((e) => <ScheduleLuckRow key={e.player_id} e={e} tone="soft" />)}
            </div>
            <div style={{ background: '#060a12' }}>
              <ColHead color={STATUS.good}>TOUGHEST SCHEDULE — raw stats most deflated</ColHead>
              {(scheduleLuck.data?.toughest_schedule ?? []).length === 0 && !scheduleLuck.isLoading && <Empty>Not enough data this season.</Empty>}
              {(scheduleLuck.data?.toughest_schedule ?? []).map((e) => <ScheduleLuckRow key={e.player_id} e={e} tone="tough" />)}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
