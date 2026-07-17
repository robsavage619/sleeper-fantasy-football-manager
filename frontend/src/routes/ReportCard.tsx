import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import {
  api,
  type ManagerReportCard,
  type ReportCardDimension,
  type OwnerSkillIndex,
  type OwnerGMMetrics,
  type DraftProfile,
  type TransactionValue,
  type OwnerHistory,
  type DraftClassStrength,
  type Scoreboard,
  type ScoreboardKind,
} from '@/lib/api'
import {
  Scatter,
  RankedBar,
  Radar,
  BumpChart,
  InfoTip,
  tierColor,
  OWNER_HUES,
  type ScatterPoint,
  type RankedItem,
  type BumpSeries,
} from '@/components/viz'

const C = {
  bg: '#060a12',
  card: '#09111f',
  panel: '#0c1625',
  border: '#162035',
  text: '#e8eef6',
  muted: '#6a8098',
  dim: '#3d5070',
  green: '#1a9b5e',
  cyan: '#00b8cc',
  amber: '#d4860c',
  red: '#c93328',
  blue: '#3a8cd4',
  violet: '#9085e9',
}
const barlow = "'Barlow Condensed', sans-serif"
const mono = "'DM Mono', monospace"

function gradeColor(grade: string): string {
  const g = grade[0]
  if (g === 'A') return C.green
  if (g === 'B') return C.cyan
  if (g === 'C') return C.amber
  return C.red
}

/** Curve percentile from a 1-based rank (1 = best). Higher is better. */
function pctFromRank(rank: number, of: number): number {
  return of <= 1 ? 1 : (of - rank + 1) / of
}

/** 1 → "1st", 2 → "2nd", 11 → "11th", etc. */
function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`
}

// Plain-English definitions — one source for the inline ⓘ tips and the glossary.
const DIM_INFO: Record<string, string> = {
  value: "Roster Value — the combined dynasty value of every player on the roster. Higher means more long-term talent on hand.",
  skill: 'Manager Skill — how well this GM plays regardless of luck: all-play win rate, lineup efficiency, and luck-adjusted results.',
  track: 'Track Record — historical results: career win % plus championships won.',
  build: 'Roster Build — positional balance and depth across QB / RB / WR / TE. Rewards depth, penalizes holes at a position.',
  capital: 'Draft Capital — future draft picks currently stockpiled. More picks = more ammo to build or trade.',
  activity: 'Activity — how engaged the GM is: trades, waiver adds, and FAAB spent per season.',
}

const M = {
  dv: "Dynasty Value (DV) — the model's estimate of a player's long-term worth in a keeper/dynasty league, blending current production with age. A roster's value is the sum across all its players.",
  allplay: 'All-Play % — your win rate if you played EVERY team every week, not just your scheduled opponent. It strips out schedule luck; 50% is exactly average.',
  luck: "Luck (wins) — actual wins minus what all-play says you should have won. Positive = you've won more than your scores earned. Directional only (see caveat).",
  lineup: 'Lineup Efficiency — points your starters scored vs the best legal lineup you could have set that week. 100% = perfect start/sit calls.',
  ledger: 'Trade Ledger P&L — retrospective value gained vs given up across all trades. UNCALIBRATED: a rough production-based estimate, and some historical assets can’t be matched by name.',
  hit: 'Draft Hit Rate — the share of a GM’s draft picks that returned real, startable fantasy value.',
  waiver: 'Waiver Value Added — fantasy points from waiver/free-agent pickups that actually reached the starting lineup.',
  faab: 'FAAB — Free-Agent Acquisition Budget, the fake money each team bids to claim players off waivers.',
  curve: 'Graded on the curve — every grade is ranked WITHIN your league (#1 = A+, last = D). It answers “who’s best here,” not an absolute score.',
  classStrength: 'Draft Class Strength — how loaded an upcoming rookie class is, read live from the pick market (FantasyCalc): what the market pays for that class’s picks vs a neutral, time-discounted baseline. A premium = the crowd treats the class as stacked. This is already baked into every pick’s value and Draft Capital grade — shown here so it’s visible, not applied twice.',
}

const GLOSSARY: [string, string][] = [
  ['Graded on the curve', M.curve],
  ['The six grades', 'VALUE · SKILL · TRACK RECORD · ROSTER BUILD · DRAFT CAPITAL · ACTIVITY — each ranked #1–last, then weighted into one overall grade.'],
  ['Dynasty Value (DV)', M.dv],
  ['All-Play %', M.allplay],
  ['Luck (wins)', M.luck],
  ['Lineup Efficiency', M.lineup],
  ['Trade Ledger P&L', M.ledger],
  ['Draft Hit Rate', M.hit],
  ['Waiver Value Added', M.waiver],
  ['FAAB', M.faab],
  ['Draft Class Strength', M.classStrength],
]

function Avatar({ avatar, name, size = 34 }: { avatar: string | null; name: string; size?: number }) {
  if (avatar) {
    return (
      <img
        src={`https://sleepercdn.com/avatars/thumbs/${avatar}`}
        alt={name}
        style={{ width: size, height: size, borderRadius: 3, objectFit: 'cover', border: `1px solid ${C.border}`, flexShrink: 0 }}
      />
    )
  }
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 3,
        background: C.panel,
        border: `1px solid ${C.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: mono,
        fontSize: size * 0.32,
        color: C.muted,
        flexShrink: 0,
      }}
    >
      {name.slice(0, 2).toUpperCase()}
    </div>
  )
}

function GradeBadge({ grade, size = 44 }: { grade: string; size?: number }) {
  const color = gradeColor(grade)
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 4,
        background: `${color}18`,
        border: `1.5px solid ${color}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: barlow,
        fontWeight: 800,
        fontSize: size * 0.46,
        color,
        flexShrink: 0,
        letterSpacing: '-0.02em',
      }}
    >
      {grade}
    </div>
  )
}

function MiniGrade({ dim }: { dim: ReportCardDimension }) {
  const color = gradeColor(dim.grade)
  return (
    <div
      title={`${dim.label}: ${dim.grade} (#${dim.rank} of ${dim.of}) — ${dim.detail}`}
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, minWidth: 42 }}
    >
      <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 15, color, lineHeight: 1 }}>{dim.grade}</span>
      <span className="tracking-wide uppercase" style={{ fontSize: 7, color: C.dim }}>
        {dim.label.split(' ').pop()}
      </span>
    </div>
  )
}

// ── Section chrome ─────────────────────────────────────────────────────────────

function Band({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <section style={{ borderBottom: `1px solid ${C.border}`, padding: '20px' }}>
      <div className="flex items-baseline gap-3" style={{ marginBottom: 16 }}>
        <h2 className="uppercase" style={{ fontFamily: barlow, fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: '0.03em', lineHeight: 1 }}>
          {title}
        </h2>
        {sub && (
          <span className="tracking-[0.22em] uppercase" style={{ fontSize: 9, color: C.dim }}>
            {sub}
          </span>
        )}
      </div>
      {children}
    </section>
  )
}

function ChartCard({ title, sub, caveat, info, children }: { title: string; sub?: string; caveat?: string; info?: string; children: ReactNode }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, background: C.card, borderRadius: 4, padding: '14px 16px' }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: 12 }}>
        <span className="flex items-center gap-1.5 tracking-[0.16em] uppercase" style={{ fontFamily: barlow, fontWeight: 700, fontSize: 13, color: C.text }}>
          {title}
          {info && <InfoTip text={info} label={title} />}
        </span>
        {sub && <span className="tracking-wide uppercase" style={{ fontSize: 8.5, color: C.dim }}>{sub}</span>}
      </div>
      {children}
      {caveat && (
        <div className="tracking-wide uppercase" style={{ marginTop: 10, fontSize: 8, color: C.amber, opacity: 0.8, display: 'flex', gap: 5, alignItems: 'center' }}>
          <span style={{ fontSize: 9 }}>⚠</span>
          {caveat}
        </div>
      )}
    </div>
  )
}

// ── Glossary ────────────────────────────────────────────────────────────────────

function Glossary({ benchmarks }: { benchmarks?: Record<string, string> }) {
  const [open, setOpen] = useState(false)
  return (
    <section style={{ borderBottom: `1px solid ${C.border}`, padding: '0 20px' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 uppercase"
        style={{ width: '100%', textAlign: 'left', background: 'transparent', border: 'none', cursor: 'pointer', padding: '11px 0', color: C.muted, fontFamily: barlow, fontWeight: 700, fontSize: 12, letterSpacing: '0.16em' }}
      >
        <span style={{ display: 'inline-flex', width: 14, height: 14, borderRadius: '50%', border: `1px solid ${C.dim}`, alignItems: 'center', justifyContent: 'center', fontFamily: mono, fontSize: 9, color: C.muted }}>
          i
        </span>
        What The Numbers Mean
        <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 11, color: C.dim, transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }}>›</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} style={{ overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '10px 24px', paddingBottom: 18, paddingTop: 4 }}>
              {GLOSSARY.map(([term, def]) => (
                <div key={term} style={{ borderLeft: `2px solid ${C.border}`, paddingLeft: 12 }}>
                  <div className="uppercase" style={{ fontFamily: barlow, fontWeight: 700, fontSize: 13, color: C.text, letterSpacing: '0.03em', marginBottom: 2 }}>
                    {term}
                  </div>
                  <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>{def}</div>
                  {benchmarks?.[term] && (
                    <div className="uppercase tracking-wide" style={{ color: C.cyan, fontSize: 9.5, marginTop: 4 }}>
                      In your league: {benchmarks[term]}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

// ── Superlative award cards ────────────────────────────────────────────────────

type Award = { title: string; card: ManagerReportCard | undefined; value: string; note: string; accent: string; benchmark?: string }

function AwardCard({ award, onOpen }: { award: Award; onOpen: (c: ManagerReportCard) => void }) {
  const { card } = award
  return (
    <button
      onClick={() => card && onOpen(card)}
      style={{
        textAlign: 'left',
        border: `1px solid ${C.border}`,
        borderTop: `2px solid ${award.accent}`,
        background: C.card,
        borderRadius: 3,
        padding: '11px 12px',
        cursor: card ? 'pointer' : 'default',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minWidth: 0,
      }}
    >
      <span className="tracking-[0.18em] uppercase" style={{ fontSize: 8.5, color: award.accent, fontWeight: 700 }}>
        {award.title}
      </span>
      <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
        <Avatar avatar={card?.avatar ?? null} name={card?.display_name ?? '—'} size={26} />
        <span className="uppercase" style={{ fontFamily: barlow, fontWeight: 700, fontSize: 15, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {card?.display_name ?? '—'}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 24, color: award.accent, lineHeight: 1 }}>{award.value}</span>
        <span className="uppercase tracking-wide" style={{ fontSize: 8, color: C.muted }}>{award.note}</span>
      </div>
      {award.benchmark && (
        <span className="uppercase tracking-wide" style={{ fontSize: 8, color: C.dim, marginTop: -2 }}>
          {award.benchmark}
        </span>
      )}
    </button>
  )
}

// ── Draft class strength ─────────────────────────────────────────────────────────

function classTierColor(label: DraftClassStrength['label']): string {
  switch (label) {
    case 'STACKED':
      return C.green
    case 'STRONG':
      return C.cyan
    case 'AVERAGE':
      return C.blue
    case 'SOFT':
      return C.amber
    case 'WEAK':
      return C.red
    default:
      return C.dim
  }
}

function DraftClassCard({ cls }: { cls: DraftClassStrength }) {
  const color = classTierColor(cls.label)
  // Diverging bar around a neutral center; ±15% maps to a full half.
  const mag = Math.max(0, Math.min(1, Math.abs(cls.pct) / 15))
  const pos = cls.pct >= 0
  return (
    <div style={{ border: `1px solid ${C.border}`, borderTop: `2px solid ${color}`, background: C.card, borderRadius: 3, padding: '12px 14px' }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: 8 }}>
        <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 22, color: C.text, letterSpacing: '0.02em' }}>{cls.season}</span>
        <span className="uppercase tracking-[0.14em]" style={{ fontSize: 10, fontWeight: 700, color, border: `1px solid ${color}55`, borderRadius: 2, padding: '2px 6px' }}>
          {cls.label}
        </span>
      </div>
      {cls.rated ? (
        <>
          <div className="flex items-center" style={{ height: 10, marginBottom: 6 }}>
            <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
              {!pos && <div style={{ width: `${mag * 100}%`, height: 6, background: color, borderRadius: '3px 0 0 3px' }} />}
            </div>
            <div style={{ width: 1, height: 10, background: C.dim, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>{pos && <div style={{ width: `${mag * 100}%`, height: 6, background: color, borderRadius: '0 3px 3px 0' }} />}</div>
          </div>
          <div className="flex items-baseline gap-1.5" style={{ marginBottom: 6 }}>
            <span style={{ fontFamily: mono, fontSize: 13, color, fontWeight: 500 }}>
              {cls.pct >= 0 ? '+' : ''}
              {cls.pct.toFixed(0)}%
            </span>
            <span className="uppercase tracking-wide" style={{ fontSize: 8, color: C.dim }}>vs neutral class</span>
          </div>
        </>
      ) : (
        <div className="uppercase tracking-wide" style={{ fontSize: 9, color: C.dim, margin: '6px 0' }}>no market pricing yet</div>
      )}
      <div style={{ color: C.muted, fontSize: 11, lineHeight: 1.45 }}>{cls.note}</div>
    </div>
  )
}

// ── Compare mode ───────────────────────────────────────────────────────────────

const DIM_AXES = ['VAL', 'SKL', 'TRK', 'BLD', 'CAP', 'ACT']

function CompareMode({ cards, selected, onToggle }: { cards: ManagerReportCard[]; selected: number[]; onToggle: (rid: number) => void }) {
  const chosen = cards.filter((c) => selected.includes(c.roster_id))
  const series = chosen.map((c, i) => ({
    id: String(c.roster_id),
    name: c.display_name,
    color: OWNER_HUES[i % OWNER_HUES.length],
    values: c.dimensions.map((d) => pctFromRank(d.rank, d.of)),
  }))
  return (
    <div>
      <div className="flex flex-wrap gap-2" style={{ marginBottom: 16 }}>
        {cards.map((c) => {
          const on = selected.includes(c.roster_id)
          const idx = selected.indexOf(c.roster_id)
          const accent = on ? OWNER_HUES[idx % OWNER_HUES.length] : C.border
          return (
            <button
              key={c.roster_id}
              onClick={() => onToggle(c.roster_id)}
              disabled={!on && selected.length >= 3}
              className="flex items-center gap-2 uppercase"
              style={{
                fontFamily: barlow,
                fontWeight: 700,
                fontSize: 12,
                letterSpacing: '0.03em',
                color: on ? C.text : C.muted,
                background: on ? `${accent}1a` : C.card,
                border: `1px solid ${accent}`,
                borderRadius: 3,
                padding: '5px 9px',
                cursor: !on && selected.length >= 3 ? 'not-allowed' : 'pointer',
                opacity: !on && selected.length >= 3 ? 0.4 : 1,
              }}
            >
              <Avatar avatar={c.avatar} name={c.display_name} size={18} />
              {c.display_name}
            </button>
          )
        })}
      </div>
      {chosen.length < 2 ? (
        <div className="tracking-widest uppercase" style={{ color: C.dim, fontSize: 11, padding: '20px 0' }}>
          PICK 2–3 MANAGERS TO COMPARE ↑
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 340px) 1fr', gap: 20, alignItems: 'center' }}>
          <div style={{ maxWidth: 340 }}>
            <Radar axes={DIM_AXES} series={series} />
          </div>
          <div style={{ display: 'grid', gap: 1, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: `120px repeat(${chosen.length}, 1fr)`, gap: 1 }}>
              <div style={{ background: C.card }} />
              {chosen.map((c, i) => (
                <div key={c.roster_id} className="flex items-center gap-2" style={{ background: C.card, padding: '8px 10px' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: OWNER_HUES[i % OWNER_HUES.length], flexShrink: 0 }} />
                  <span className="uppercase" style={{ fontFamily: barlow, fontWeight: 700, fontSize: 13, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {c.display_name}
                  </span>
                </div>
              ))}
            </div>
            {[
              { label: 'Overall', get: (c: ManagerReportCard) => `${c.overall_grade} · #${c.overall_rank}` },
              { label: 'Record', get: (c: ManagerReportCard) => c.record },
              { label: 'Win %', get: (c: ManagerReportCard) => `${(c.win_pct * 100).toFixed(0)}%` },
              { label: 'Titles', get: (c: ManagerReportCard) => String(c.titles) },
              ...c0dims(chosen),
            ].map((row) => (
              <div key={row.label} style={{ display: 'grid', gridTemplateColumns: `120px repeat(${chosen.length}, 1fr)`, gap: 1 }}>
                <div className="tracking-wide uppercase" style={{ background: C.card, padding: '6px 10px', fontSize: 9, color: C.muted }}>
                  {row.label}
                </div>
                {chosen.map((c) => (
                  <div key={c.roster_id} style={{ background: C.card, padding: '6px 10px', fontFamily: mono, fontSize: 11.5, color: C.text }}>
                    {row.get(c)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Per-dimension grade rows for the compare table (keyed off the first owner's dims). */
function c0dims(chosen: ManagerReportCard[]): { label: string; get: (c: ManagerReportCard) => string }[] {
  if (!chosen.length) return []
  return chosen[0].dimensions.map((d, idx) => ({
    label: d.label,
    get: (c: ManagerReportCard) => {
      const dd = c.dimensions[idx]
      return dd ? `${dd.grade} · #${dd.rank}` : '—'
    },
  }))
}

// ── Leaderboard row ─────────────────────────────────────────────────────────────

function CardRow({ card, onOpen }: { card: ManagerReportCard; onOpen: (c: ManagerReportCard) => void }) {
  const color = gradeColor(card.overall_grade)
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: Math.min(card.overall_rank * 0.02, 0.3) }}
      onClick={() => onOpen(card)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '12px 16px',
        borderBottom: `1px solid ${C.border}`,
        cursor: 'pointer',
        boxShadow: card.is_me ? `inset 3px 0 0 ${C.cyan}` : `inset 3px 0 0 ${color}`,
        background: card.is_me ? 'rgba(0,184,204,0.04)' : 'transparent',
      }}
    >
      <span style={{ width: 22, textAlign: 'right', color: C.dim, fontFamily: mono, fontSize: 13 }}>{card.overall_rank}</span>
      <GradeBadge grade={card.overall_grade} />
      <Avatar avatar={card.avatar} name={card.display_name} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: barlow, fontWeight: 700, fontSize: 17, color: C.text, letterSpacing: '0.02em' }}>
            {card.display_name.toUpperCase()}
          </span>
          {card.is_me && (
            <span className="tracking-[0.2em] uppercase" style={{ fontSize: 8, fontWeight: 700, color: C.cyan, padding: '1px 5px', border: `1px solid ${C.cyan}55`, borderRadius: 1 }}>
              YOU
            </span>
          )}
          {card.titles > 0 && <span style={{ fontSize: 11, color: C.amber }}>{'★'.repeat(card.titles)}</span>}
        </div>
        <div style={{ color: C.muted, fontSize: 11, marginTop: 1 }}>
          {card.record} · {(card.win_pct * 100).toFixed(0)}% · {card.playoff_appearances} playoff
          {card.seasons_played ? ` · ${card.seasons_played} seasons` : ''}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        {card.dimensions.map((d) => (
          <MiniGrade key={d.key} dim={d} />
        ))}
      </div>
    </motion.div>
  )
}

// ── Drawer ──────────────────────────────────────────────────────────────────────

function DimensionRow({ dim }: { dim: ReportCardDimension }) {
  const color = gradeColor(dim.grade)
  const fillPct = pctFromRank(dim.rank, dim.of) * 100
  return (
    <div style={{ padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: barlow, fontWeight: 700, fontSize: 15, color: C.text, letterSpacing: '0.03em' }}>
            {dim.label.toUpperCase()}
          </span>
          {DIM_INFO[dim.key] && <InfoTip text={DIM_INFO[dim.key]} label={dim.label} />}
          <span style={{ color: C.dim, fontSize: 11, fontFamily: mono }}>#{dim.rank} of {dim.of}</span>
        </div>
        <GradeBadge grade={dim.grade} size={30} />
      </div>
      <div style={{ height: 5, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
        <motion.div style={{ height: '100%', background: color, borderRadius: 3 }} initial={{ width: 0 }} animate={{ width: `${fillPct}%` }} transition={{ duration: 0.5, ease: 'easeOut' }} />
      </div>
      {dim.detail && <div style={{ color: C.muted, fontSize: 11, marginTop: 5 }}>{dim.detail}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ borderTop: `1px solid ${C.border}`, padding: '14px 18px' }}>
      <div className="tracking-[0.28em] uppercase" style={{ color: C.muted, fontSize: 10, marginBottom: 10, fontWeight: 700 }}>
        {title}
      </div>
      {children}
    </section>
  )
}

function KeyStat({ value, label, color }: { value: string; label: string; color?: string }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, background: C.card, padding: '8px 10px', borderRadius: 2, textAlign: 'center' }}>
      <div style={{ fontFamily: barlow, fontWeight: 800, fontSize: 24, color: color ?? C.text, lineHeight: 1 }}>{value}</div>
      <div className="tracking-[0.15em] uppercase" style={{ color: C.dim, fontSize: 8, marginTop: 3 }}>{label}</div>
    </div>
  )
}

function SeasonTrend({ history }: { history: ManagerReportCard['season_history'] }) {
  if (history.length < 2) return null
  const maxWins = Math.max(...history.map((s) => s.wins + s.losses + s.ties), 1)
  return (
    <div>
      <div className="tracking-[0.18em] uppercase" style={{ color: C.dim, fontSize: 8, marginBottom: 8 }}>WINS BY SEASON</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 90 }}>
        {history.map((s) => {
          const games = s.wins + s.losses + s.ties || 1
          const h = Math.max(4, Math.round((s.wins / maxWins) * 66))
          const col = s.champion ? C.amber : s.made_playoffs ? C.green : C.dim
          return (
            <div key={s.season} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <span style={{ color: s.champion ? C.amber : C.text, fontSize: 11, fontFamily: mono, fontWeight: 700 }}>{s.champion ? '★' : s.wins}</span>
              <div style={{ width: '100%', maxWidth: 34, height: h, background: col, borderRadius: '2px 2px 0 0' }} title={`${s.wins}-${s.losses} of ${games}`} />
              <span style={{ color: C.muted, fontSize: 9, fontFamily: mono }}>{`'${s.season.slice(2)}`}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** GM sabermetric + transaction detail for the drawer, joined from the extra endpoints. */
function DrawerAnalytics({ ctx, rid }: { ctx: Ctx; rid: number }) {
  const saber = ctx.saber.get(rid)
  const skill = ctx.skill.get(rid)
  const draft = ctx.draft.get(rid)
  const tx = ctx.tx.get(rid)
  return (
    <>
      {(saber || skill) && (
        <Section title="GM Sabermetrics">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
            {saber && (
              <KeyStat
                value={`${saber.luck.luck_index >= 0 ? '+' : ''}${saber.luck.luck_index.toFixed(1)}`}
                label="Luck (W)"
                color={saber.luck.luck_index >= 0 ? C.green : C.red}
              />
            )}
            {skill && <KeyStat value={`${(skill.allplay_pct * 100).toFixed(0)}%`} label="All-Play" />}
            {skill && (
              <KeyStat
                value={skill.lineup_efficiency ? `${(skill.lineup_efficiency * 100).toFixed(0)}%` : 'n/a'}
                label="Lineup Eff"
                color={skill.lineup_efficiency ? tierColor(skill.lineup_efficiency) : C.dim}
              />
            )}
            {saber && (
              <KeyStat
                value={saber.faab.used != null ? String(saber.faab.used) : 'n/a'}
                label="FAAB Used"
              />
            )}
          </div>
          {saber && (
            <div className="tracking-wide uppercase" style={{ marginTop: 8, fontSize: 8.5, color: C.muted }}>
              {saber.luck.close_wins}-{saber.luck.close_losses} in one-score games · all-play {(saber.luck.allplay_pct * 100).toFixed(0)}% over {saber.luck.skill_season}
            </div>
          )}
          <div className="tracking-wide uppercase" style={{ marginTop: 4, fontSize: 8, color: C.amber, opacity: 0.75 }}>
            ⚠ luck blends career wins with single-season all-play — read as directional
          </div>
        </Section>
      )}

      {saber && saber.trade_ledger.trade_count > 0 && (
        <Section title="Trade Ledger P&L">
          <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
            <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 30, color: saber.trade_ledger.net >= 0 ? C.green : C.red, lineHeight: 1 }}>
              {saber.trade_ledger.net >= 0 ? '+' : ''}{saber.trade_ledger.net.toFixed(0)}
            </span>
            <div className="text-right" style={{ fontFamily: mono, fontSize: 10, color: C.muted }}>
              <div>in {saber.trade_ledger.value_in.toFixed(0)} · out {saber.trade_ledger.value_out.toFixed(0)}</div>
              <div>{saber.trade_ledger.trade_count} trades · {saber.trade_ledger.resolved} resolved / {saber.trade_ledger.unresolved} unresolved</div>
            </div>
          </div>
          <div className="tracking-wide uppercase" style={{ fontSize: 8, color: C.amber, opacity: 0.8 }}>
            ⚠ UNCALIBRATED — retrospective FPAR; {saber.trade_ledger.unresolved} assets unresolved by name
          </div>
        </Section>
      )}

      {tx && (tx.waiver_started_points > 0 || tx.trade_net_points !== 0) && (
        <Section title={`Transaction Value · ${tx.season}`}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            <KeyStat value={`+${tx.waiver_started_points.toFixed(0)}`} label="Waiver Pts Started" color={C.cyan} />
            <KeyStat value={`${tx.trade_net_points >= 0 ? '+' : ''}${tx.trade_net_points.toFixed(0)}`} label="Trade Net Pts" color={tx.trade_net_points >= 0 ? C.green : C.red} />
            <KeyStat value={String(tx.waiver_adds)} label="Waiver Adds" />
          </div>
          {tx.top_pickups.length > 0 && (
            <div className="tracking-wide uppercase" style={{ marginTop: 8, fontSize: 8.5, color: C.muted }}>
              TOP PICKUP · {tx.top_pickups[0].name} ({tx.top_pickups[0].points.toFixed(0)} pts)
            </div>
          )}
        </Section>
      )}

      {draft && draft.best_picks.length > 0 && (
        <Section title={`Draft · ${draft.position_lean} · ${(draft.hit_rate * 100).toFixed(0)}% hit rate`}>
          <div style={{ display: 'grid', gap: 1, background: C.border }}>
            {draft.best_picks.slice(0, 4).map((p) => (
              <div key={p.player_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8, padding: '6px 10px', background: C.card, fontSize: 12, alignItems: 'center' }}>
                <span style={{ color: C.text, fontFamily: barlow, fontWeight: 700, fontSize: 14 }}>{p.name}</span>
                <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>{p.season} R{p.round}</span>
                <span style={{ fontFamily: mono, fontSize: 11, color: C.green }}>{p.value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function GradeDrawerBody({ card, ctx }: { card: ManagerReportCard; ctx: Ctx }) {
  const color = gradeColor(card.overall_grade)
  return (
    <>
      <div style={{ padding: '18px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <GradeBadge grade={card.overall_grade} size={62} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar avatar={card.avatar} name={card.display_name} size={22} />
              <span style={{ color: C.dim, fontFamily: mono, fontSize: 11 }}>#{card.overall_rank} in league · score {card.overall_score.toFixed(0)}</span>
            </div>
            <h2 className="uppercase leading-none" style={{ color: C.text, fontFamily: barlow, fontSize: 32, fontWeight: 800, marginTop: 5 }}>
              {card.display_name}
            </h2>
            {card.headline && <div style={{ color, fontSize: 12, marginTop: 4, fontStyle: 'italic' }}>{card.headline}</div>}
          </div>
        </div>
      </div>

      <Section title="Grades vs Your League">
        <div>
          {card.dimensions.map((d) => (
            <DimensionRow key={d.key} dim={d} />
          ))}
        </div>
      </Section>

      <DrawerAnalytics ctx={ctx} rid={card.roster_id} />

      <Section title="Track Record">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginBottom: card.season_history.length >= 2 ? 16 : 0 }}>
          <KeyStat value={card.record} label="Career" />
          <KeyStat value={`${(card.win_pct * 100).toFixed(0)}%`} label="Win Rate" />
          <KeyStat value={String(card.titles)} label="Titles" color={card.titles ? C.amber : undefined} />
          <KeyStat value={String(card.playoff_appearances)} label="Playoffs" />
        </div>
        <SeasonTrend history={card.season_history} />
      </Section>

      {card.season_history.length > 0 && (
        <Section title="Season By Season">
          <div style={{ display: 'grid', gap: 1, background: C.border }}>
            <div className="tracking-wide" style={{ display: 'grid', gridTemplateColumns: '52px 1fr 1fr 1.4fr', gap: 6, padding: '4px 10px', color: C.dim, fontSize: 8, fontFamily: mono }}>
              <span>YR</span>
              <span style={{ textAlign: 'right' }}>W-L</span>
              <span style={{ textAlign: 'right' }}>FINISH</span>
              <span style={{ textAlign: 'right' }}>RESULT</span>
            </div>
            {[...card.season_history].reverse().map((s) => (
              <div key={s.season} style={{ display: 'grid', gridTemplateColumns: '52px 1fr 1fr 1.4fr', gap: 6, padding: '7px 10px', background: C.card, fontSize: 12, fontFamily: mono, alignItems: 'center' }}>
                <span style={{ color: C.text, fontWeight: 700 }}>{s.season}</span>
                <span style={{ textAlign: 'right', color: C.muted }}>
                  {s.wins}-{s.losses}
                  {s.ties ? `-${s.ties}` : ''}
                </span>
                <span style={{ textAlign: 'right', color: C.muted }}>#{s.reg_finish}/{s.of_teams}</span>
                <span style={{ textAlign: 'right', color: s.champion ? C.amber : s.made_playoffs ? C.green : C.dim }}>
                  {s.champion ? '★ CHAMPION' : s.made_playoffs ? 'PLAYOFFS' : 'MISSED'}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function GradeDrawer({ card, ctx, onClose }: { card: ManagerReportCard | null; ctx: Ctx; onClose: () => void }) {
  return (
    <AnimatePresence>
      {card && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 40 }} />
          <motion.aside
            initial={{ x: 540 }}
            animate={{ x: 0 }}
            exit={{ x: 540 }}
            transition={{ type: 'spring', damping: 30, stiffness: 260 }}
            style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(540px, 100vw)', background: C.bg, borderLeft: `1px solid ${C.border}`, zIndex: 50, overflowY: 'auto', boxShadow: '-24px 0 60px rgba(0,0,0,0.45)' }}
          >
            <button onClick={onClose} aria-label="Close report card" style={{ position: 'absolute', top: 12, right: 12, border: '1px solid #24344f', background: C.card, color: C.muted, width: 28, height: 28, borderRadius: 2, cursor: 'pointer', zIndex: 2 }}>
              X
            </button>
            <GradeDrawerBody card={card} ctx={ctx} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Joined context ───────────────────────────────────────────────────────────────

type Ctx = {
  skill: Map<number, OwnerSkillIndex>
  saber: Map<number, OwnerGMMetrics>
  draft: Map<number, DraftProfile>
  tx: Map<number, TransactionValue>
  history: Map<number, OwnerHistory>
}

function argmax<T>(items: T[], score: (t: T) => number | null): T | undefined {
  let best: T | undefined
  let bestScore = -Infinity
  for (const it of items) {
    const s = score(it)
    if (s != null && s > bestScore) {
      bestScore = s
      best = it
    }
  }
  return best
}

function buildAwards(cards: ManagerReportCard[], ctx: Ctx): Award[] {
  const byId = new Map(cards.map((c) => [c.roster_id, c]))
  const awards: Award[] = []

  const drafter = argmax([...ctx.draft.values()], (d) => (d.total_picks >= 3 ? d.hit_rate : null))
  if (drafter) {
    const med = median([...ctx.draft.values()].filter((d) => d.total_picks >= 3).map((d) => d.hit_rate))
    awards.push({ title: 'Best Drafter', card: byId.get(drafter.roster_id), value: `${(drafter.hit_rate * 100).toFixed(0)}%`, note: `hit rate · ${drafter.hits}/${drafter.total_picks}`, accent: C.blue, benchmark: `league median ${(med * 100).toFixed(0)}%` })
  }

  const trader = argmax([...ctx.tx.values()], (t) => t.trade_net_points)
  if (trader && trader.trade_net_points > 0) {
    const med = median([...ctx.tx.values()].map((t) => t.trade_net_points))
    awards.push({ title: 'Best Trader', card: byId.get(trader.roster_id), value: `+${trader.trade_net_points.toFixed(0)}`, note: `net pts · ${trader.trade_count} deals`, accent: C.green, benchmark: `league median ${med >= 0 ? '+' : ''}${med.toFixed(0)}` })
  }

  const lucky = argmax([...ctx.saber.values()], (s) => s.luck.luck_index)
  if (lucky) awards.push({ title: 'Luckiest', card: byId.get(lucky.roster_id), value: `+${lucky.luck.luck_index.toFixed(1)}`, note: 'wins vs all-play', accent: C.amber, benchmark: '0 = won exactly as earned' })

  const active = argmax([...ctx.history.values()], (h) => h.trades_per_season + h.adds_per_season / 5)
  if (active) {
    const med = median([...ctx.history.values()].map((h) => h.trades_per_season))
    awards.push({ title: 'Most Active', card: byId.get(active.roster_id), value: `${active.trades_per_season.toFixed(1)}`, note: `trades/yr · ${active.adds_per_season.toFixed(0)} adds`, accent: C.cyan, benchmark: `league median ${med.toFixed(1)}/yr` })
  }

  const riser = argmax(cards, (c) => {
    if (c.season_history.length < 2) return null
    const first = c.season_history[0]
    const last = c.season_history[c.season_history.length - 1]
    return first.reg_finish - last.reg_finish
  })
  if (riser && riser.season_history.length >= 2) {
    const delta = riser.season_history[0].reg_finish - riser.season_history[riser.season_history.length - 1].reg_finish
    if (delta > 0) awards.push({ title: 'Biggest Riser', card: riser, value: `+${delta}`, note: 'places climbed', accent: C.violet, benchmark: `${ordinal(riser.season_history[0].reg_finish)} → ${ordinal(riser.season_history[riser.season_history.length - 1].reg_finish)} finish` })
  }

  const roster = argmax([...ctx.skill.values()], (s) => s.roster_value)
  if (roster) {
    const vals = [...ctx.skill.values()].map((s) => s.roster_value).filter(Boolean)
    const avg = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0
    awards.push({ title: 'Best Roster', card: byId.get(roster.roster_id), value: roster.roster_value.toLocaleString(), note: 'dynasty value', accent: C.green, benchmark: `league avg ${avg.toLocaleString()}` })
  }

  return awards
}

function leagueStory(cards: ManagerReportCard[], ctx: Ctx): string[] {
  if (!cards.length) return []
  const top = cards[0]
  const lines: string[] = []

  const topTitles = top.titles ? `${top.titles}× champ ` : ''
  lines.push(`${top.display_name} is the class of the league — a ${top.overall_grade} franchise ${topTitles}at ${top.record} (${(top.win_pct * 100).toFixed(0)}%).`)

  // Rebuilder: most draft capital held, bottom-half overall.
  const capitalDim = (c: ManagerReportCard) => c.dimensions.find((d) => d.key === 'capital')
  const rebuilder = argmax(
    cards.filter((c) => c.overall_rank > cards.length / 2),
    (c) => capitalDim(c)?.value ?? null,
  )
  if (rebuilder) {
    const picks = capitalDim(rebuilder)?.value ?? 0
    lines.push(`${rebuilder.display_name} is playing the long game — stockpiling ${picks} picks while the win column lags.`)
  }

  // Sharpest contrast: best team by all-play with the most negative luck (good but robbed).
  const robbed = argmax([...ctx.saber.values()], (s) => (s.luck.luck_index < 0 ? s.luck.allplay_pct : null))
  const robbedCard = robbed ? cards.find((c) => c.roster_id === robbed.roster_id) : undefined
  if (robbedCard && robbed) {
    lines.push(`Sharpest split: ${robbedCard.display_name} grades out elite (${(robbed.luck.allplay_pct * 100).toFixed(0)}% all-play) but the schedule has cost them ${Math.abs(robbed.luck.luck_index).toFixed(1)} wins.`)
  }

  return lines
}

// ── GM track record (the AI's own calls, graded) ────────────────────────────────

function kindAccent(kind: string): string {
  if (kind === 'lineup') return C.cyan
  if (kind === 'waiver') return C.green
  if (kind === 'trade') return C.violet
  if (kind === 'draft') return C.blue
  return C.amber
}

function TrackRecordTile({ k }: { k: ScoreboardKind }) {
  const accent = kindAccent(k.kind)
  const graded = k.graded > 0
  const pending = k.total - k.graded
  return (
    <div style={{ border: `1px solid ${C.border}`, borderTop: `2px solid ${accent}`, background: C.card, borderRadius: 3, padding: '11px 13px' }}>
      <div className="tracking-[0.16em] uppercase" style={{ fontSize: 9, color: accent, fontWeight: 700, marginBottom: 6 }}>
        {k.kind}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 26, color: graded ? C.text : C.dim, lineHeight: 1 }}>
          {graded ? `${Math.round((k.hit_rate ?? 0) * 100)}%` : '—'}
        </span>
        <span className="uppercase tracking-wide" style={{ fontSize: 8, color: C.muted }}>
          {graded ? `hit rate · ${k.correct}/${k.graded}` : 'not yet graded'}
        </span>
      </div>
      {pending > 0 && (
        <div className="uppercase tracking-wide" style={{ fontSize: 8, color: C.dim, marginTop: 4 }}>
          {pending} pending
        </div>
      )}
    </div>
  )
}

function TrackRecord({ board }: { board: Scoreboard }) {
  const overall = board.overall_hit_rate
  const graded = board.by_kind.filter((k) => k.total > 0)
  return (
    <Band title="GM Track Record" sub="THE ENGINE'S OWN CALLS · GRADED AGAINST WHAT HAPPENED">
      <div className="flex items-baseline gap-3" style={{ marginBottom: 14, maxWidth: 780 }}>
        <span style={{ fontFamily: barlow, fontWeight: 800, fontSize: 34, color: overall != null ? C.text : C.dim, lineHeight: 1 }}>
          {overall != null ? `${Math.round(overall * 100)}%` : '—'}
        </span>
        <span style={{ color: C.muted, fontSize: 13 }}>
          overall lineup + waiver hit rate · {board.graded_count} graded, {board.pending_count} pending
        </span>
      </div>
      {graded.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
          {graded.map((k) => (
            <TrackRecordTile key={k.kind} k={k} />
          ))}
        </div>
      ) : (
        <div className="tracking-wide uppercase" style={{ color: C.dim, fontSize: 10, padding: '8px 0' }}>
          No recommendations posted yet — the track record fills in as the war room runs.
        </div>
      )}
      {board.warnings.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 11, color: C.muted, lineHeight: 1.5, maxWidth: 780 }}>
          {board.warnings.map((w, i) => (
            <div key={i} className="flex gap-1.5" style={{ opacity: 0.85 }}>
              <span style={{ color: C.dim }}>·</span>
              {w}
            </div>
          ))}
        </div>
      )}
    </Band>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────────

export function ReportCard() {
  const [selected, setSelected] = useState<ManagerReportCard | null>(null)
  const [compare, setCompare] = useState<number[]>([])

  const rc = useQuery({ queryKey: ['report-card'], queryFn: () => api.reportCard(), staleTime: 5 * 60 * 1000 })
  const skillQ = useQuery({ queryKey: ['owner-skill'], queryFn: () => api.ownerSkill(), staleTime: 5 * 60 * 1000 })
  const saberQ = useQuery({ queryKey: ['owner-saber'], queryFn: () => api.ownersSabermetrics(), staleTime: 5 * 60 * 1000 })
  const draftQ = useQuery({ queryKey: ['owner-draft'], queryFn: () => api.draftProfile(), staleTime: 5 * 60 * 1000 })
  const txQ = useQuery({ queryKey: ['owner-tx'], queryFn: () => api.transactionValue(), staleTime: 5 * 60 * 1000 })
  const histQ = useQuery({ queryKey: ['owner-history'], queryFn: () => api.leagueHistory(), staleTime: 5 * 60 * 1000 })
  const classQ = useQuery({ queryKey: ['draft-class-strength'], queryFn: () => api.draftClassStrength(), staleTime: 5 * 60 * 1000 })
  const scoreQ = useQuery({ queryKey: ['gm-scoreboard'], queryFn: () => api.scoreboard(), staleTime: 5 * 60 * 1000 })

  const cards = rc.data ?? []

  const ctx: Ctx = useMemo(
    () => ({
      skill: new Map((skillQ.data ?? []).map((s) => [s.roster_id, s])),
      saber: new Map((saberQ.data ?? []).map((s) => [s.roster_id, s])),
      draft: new Map((draftQ.data ?? []).map((d) => [d.roster_id, d])),
      tx: new Map((txQ.data ?? []).map((t) => [t.roster_id, t])),
      history: new Map((histQ.data?.owners ?? []).map((h) => [h.roster_id, h])),
    }),
    [skillQ.data, saberQ.data, draftQ.data, txQ.data, histQ.data],
  )

  const awards = useMemo(() => (cards.length ? buildAwards(cards, ctx) : []), [cards, ctx])
  const story = useMemo(() => (cards.length ? leagueStory(cards, ctx) : []), [cards, ctx])

  // Live league scale so raw numbers (esp. dynasty value) have a reference point.
  const glossaryBenchmarks = useMemo(() => {
    const dv = [...ctx.skill.values()].map((s) => s.roster_value).filter(Boolean)
    if (!dv.length) return undefined
    return {
      'Dynasty Value (DV)': `${Math.min(...dv).toLocaleString()} lowest · ${Math.round(median(dv)).toLocaleString()} median · ${Math.max(...dv).toLocaleString()} top`,
    }
  }, [ctx])

  // Default compare selection: me + top overall (once data lands).
  const meId = cards.find((c) => c.is_me)?.roster_id
  const compareInit = compare.length === 0 && cards.length >= 2
  const compareSel = compareInit ? [cards[0].roster_id, meId && meId !== cards[0].roster_id ? meId : cards[1].roster_id] : compare
  const toggleCompare = (rid: number) =>
    setCompare((prev) => {
      const base = prev.length === 0 ? compareSel : prev
      if (base.includes(rid)) return base.filter((x) => x !== rid)
      if (base.length >= 3) return base
      return [...base, rid]
    })

  // Scatter: all-play skill (x) vs luck (y), from the saber suite.
  const scatterPts: ScatterPoint[] = useMemo(() => {
    return cards
      .map((c) => {
        const s = ctx.saber.get(c.roster_id)
        if (!s) return null
        return {
          id: String(c.roster_id),
          x: s.luck.allplay_pct,
          y: s.luck.luck_index,
          name: c.display_name,
          avatar: c.avatar,
          me: c.is_me,
          ring: tierColor(s.luck.allplay_pct),
          tip: `${c.display_name}: ${(s.luck.allplay_pct * 100).toFixed(0)}% all-play · ${s.luck.luck_index >= 0 ? '+' : ''}${s.luck.luck_index.toFixed(1)} luck`,
        } as ScatterPoint
      })
      .filter(Boolean) as ScatterPoint[]
  }, [cards, ctx])
  const medAllplay = median(scatterPts.map((p) => p.x))

  const tradeBars: RankedItem[] = useMemo(
    () =>
      [...ctx.saber.values()]
        .filter((s) => s.trade_ledger.trade_count > 0)
        .map((s) => ({ id: String(s.roster_id), label: s.display_name ?? `R${s.roster_id}`, avatar: cards.find((c) => c.roster_id === s.roster_id)?.avatar ?? null, value: s.trade_ledger.net, me: cards.find((c) => c.roster_id === s.roster_id)?.is_me, sub: `${s.trade_ledger.trade_count} deals` }))
        .sort((a, b) => b.value - a.value),
    [ctx, cards],
  )

  const lineupBars: RankedItem[] = useMemo(
    () =>
      [...ctx.skill.values()]
        .filter((s) => s.lineup_efficiency)
        .map((s) => ({ id: String(s.roster_id), label: s.display_name ?? `R${s.roster_id}`, avatar: cards.find((c) => c.roster_id === s.roster_id)?.avatar ?? null, value: s.lineup_efficiency * 100, me: cards.find((c) => c.roster_id === s.roster_id)?.is_me }))
        .sort((a, b) => b.value - a.value),
    [ctx, cards],
  )

  const draftBars: RankedItem[] = useMemo(
    () =>
      [...ctx.draft.values()]
        .filter((d) => d.total_picks >= 3)
        .map((d) => ({ id: String(d.roster_id), label: d.display_name, avatar: cards.find((c) => c.roster_id === d.roster_id)?.avatar ?? null, value: d.hit_rate * 100, me: cards.find((c) => c.roster_id === d.roster_id)?.is_me, sub: `${d.hits}/${d.total_picks}` }))
        .sort((a, b) => b.value - a.value),
    [ctx, cards],
  )

  const waiverBars: RankedItem[] = useMemo(
    () =>
      [...ctx.tx.values()]
        .map((t) => ({ id: String(t.roster_id), label: t.display_name, avatar: cards.find((c) => c.roster_id === t.roster_id)?.avatar ?? null, value: t.waiver_started_points, me: cards.find((c) => c.roster_id === t.roster_id)?.is_me, sub: `${t.waiver_adds} adds` }))
        .filter((t) => t.value > 0)
        .sort((a, b) => b.value - a.value),
    [ctx, cards],
  )

  // Bump chart: reg_finish across all seasons present in season_history.
  const { bumpSeasons, bumpSeries, bumpOf } = useMemo(() => {
    const seasonSet = new Set<string>()
    let of = 0
    for (const c of cards) for (const s of c.season_history) {
      seasonSet.add(s.season)
      of = Math.max(of, s.of_teams)
    }
    const seasons = [...seasonSet].sort()
    const series: BumpSeries[] = cards
      .filter((c) => c.season_history.length > 0)
      .map((c) => {
        const bySeason = new Map(c.season_history.map((s) => [s.season, s.reg_finish]))
        return { id: String(c.roster_id), name: c.display_name, me: c.is_me, ranks: seasons.map((s) => bySeason.get(s) ?? null) }
      })
    return { bumpSeasons: seasons, bumpSeries: series, bumpOf: of || cards.length }
  }, [cards])

  const anyLoading = rc.isLoading
  const extrasReady = saberQ.data && skillQ.data

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: barlow, fontSize: 40, fontWeight: 800, color: C.text }}>
            LEAGUE REPORT CARD
          </h1>
          <span className="flex items-center gap-1.5 tracking-[0.3em] uppercase" style={{ fontSize: 11, color: C.muted }}>
            FRANCHISE GRADES · RANKED · GRADED ON THE CURVE
            <InfoTip text={M.curve} label="graded on the curve" />
          </span>
        </div>
      </div>

      {cards.length > 0 && <Glossary benchmarks={glossaryBenchmarks} />}

      {anyLoading && (
        <div className="p-8 text-center tracking-widest uppercase" style={{ color: C.dim, fontSize: 12 }}>
          GRADING THE LEAGUE…
        </div>
      )}
      {rc.error && (
        <div className="mx-5 mt-4 p-3" style={{ background: 'rgba(201,51,40,0.06)', border: '1px solid rgba(201,51,40,0.2)', borderLeft: `3px solid ${C.red}`, borderRadius: 2, color: '#e07060', fontSize: 13 }}>
          {String(rc.error)}
        </div>
      )}

      {cards.length > 0 && (
        <>
          {/* ── STORY ── */}
          {story.length > 0 && (
            <Band title="The League" sub="AT A GLANCE">
              <div style={{ maxWidth: 780 }}>
                {story.map((line, i) => (
                  <p key={i} style={{ color: i === 0 ? C.text : C.muted, fontSize: i === 0 ? 16 : 13.5, lineHeight: 1.55, marginBottom: 6 }}>
                    {line}
                  </p>
                ))}
              </div>
            </Band>
          )}

          {/* ── GM TRACK RECORD ── */}
          {scoreQ.data && <TrackRecord board={scoreQ.data} />}

          {/* ── SUPERLATIVES ── */}
          {awards.length > 0 && (
            <Band title="Superlatives" sub="LEAGUE AWARDS · CLICK FOR THE FULL CARD">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>
                {awards.map((a) => (
                  <AwardCard key={a.title} award={a} onOpen={setSelected} />
                ))}
              </div>
            </Band>
          )}

          {/* ── HEADLINE CHARTS ── */}
          {extrasReady && (
            <Band title="Good, or Just Lucky?" sub="ALL-PLAY SKILL vs SCHEDULE LUCK">
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 16 }}>
                <ChartCard
                  title="Skill vs Luck"
                  sub={`${scatterPts.length} managers`}
                  info={`${M.allplay} ${M.luck} Right = better team; up = luckier.`}
                  caveat="luck blends career wins with single-season all-play — directional, not exact"
                >
                  {scatterPts.length > 0 ? (
                    <Scatter
                      points={scatterPts}
                      xLabel="All-Play %"
                      yLabel="Luck (wins)"
                      xRef={medAllplay}
                      yRef={0}
                      quadrants={['LUCKY', 'GOOD & LUCKY', 'GOOD, ROBBED', 'COLD']}
                    />
                  ) : (
                    <Empty />
                  )}
                </ChartCard>
                <ChartCard title="Trade Ledger P&L" sub="net value" info={M.ledger} caveat="UNCALIBRATED — retrospective FPAR; partial resolution">
                  {tradeBars.length > 0 ? <RankedBar items={tradeBars} diverging format={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}`} /> : <Empty />}
                </ChartCard>
              </div>
            </Band>
          )}

          {/* ── DEEP DIVE ── */}
          {extrasReady && (
            <Band title="Deep Dive" sub="OWNER-BY-OWNER COMPARISONS">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
                <ChartCard title="Lineup Efficiency" sub="actual / optimal" info={M.lineup}>
                  {lineupBars.length > 0 ? <RankedBar items={lineupBars} format={(v) => `${v.toFixed(0)}%`} colorFor={(v) => tierColor(v / 100)} /> : <Empty note="no lineup data" />}
                </ChartCard>
                <ChartCard title="Draft Hit Rate" sub="value-returning picks" info={M.hit}>
                  {draftBars.length > 0 ? <RankedBar items={draftBars} format={(v) => `${v.toFixed(0)}%`} colorFor={(v) => tierColor(v / 100)} /> : <Empty />}
                </ChartCard>
                <ChartCard title="Waiver Value Added" sub="points that reached lineups" info={M.waiver}>
                  {waiverBars.length > 0 ? <RankedBar items={waiverBars} format={(v) => `+${v.toFixed(0)}`} colorFor={() => C.cyan} /> : <Empty note="off-season — thin waiver data" />}
                </ChartCard>
              </div>
              {bumpSeasons.length >= 2 && (
                <div style={{ marginTop: 16 }}>
                  <ChartCard title="Finish By Season" sub="regular-season rank · 1 = best">
                    <BumpChart seasons={bumpSeasons} series={bumpSeries} ofTeams={bumpOf} />
                  </ChartCard>
                </div>
              )}
            </Band>
          )}

          {/* ── DRAFT CLASSES ── */}
          {classQ.data && classQ.data.length > 0 && (
            <Band title="Upcoming Draft Classes" sub="MARKET-IMPLIED STRENGTH · ALREADY PRICED INTO PICK VALUES">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                {classQ.data.map((cls) => (
                  <DraftClassCard key={cls.season} cls={cls} />
                ))}
              </div>
              <div className="tracking-wide uppercase" style={{ marginTop: 12, fontSize: 8, color: C.amber, opacity: 0.8, display: 'flex', gap: 5, alignItems: 'center' }}>
                <span style={{ fontSize: 9 }}>⚠</span>
                market-implied read (FantasyCalc, refreshed) vs the model’s time-discounted baseline — directional, and already reflected in pick values
              </div>
            </Band>
          )}

          {/* ── COMPARE ── */}
          <Band title="Head to Head" sub="PICK 2–3 MANAGERS">
            <CompareMode cards={cards} selected={compareSel} onToggle={toggleCompare} />
          </Band>

          {/* ── LEADERBOARD ── */}
          <div className="flex items-center gap-2 px-5 py-2 tracking-wide uppercase" style={{ borderBottom: `1px solid ${C.border}`, background: C.card, color: C.dim, fontSize: 9 }}>
            <span style={{ width: 22 }} />
            <span style={{ width: 44 }}>GRADE</span>
            <span style={{ flex: 1, marginLeft: 48 }}>MANAGER · CAREER</span>
            <span>VAL · SKL · TRK · BLD · CAP · ACT</span>
          </div>
          {cards.map((card) => (
            <CardRow key={card.roster_id} card={card} onOpen={setSelected} />
          ))}
          <div className="px-5 py-3 tracking-wider uppercase" style={{ borderTop: `1px solid ${C.border}`, fontSize: 10, color: C.dim }}>
            VALUE · SKILL · TRACK RECORD · ROSTER BUILD · DRAFT CAPITAL · ACTIVITY — each graded #1–last within your league
          </div>
        </>
      )}

      <GradeDrawer card={selected} ctx={ctx} onClose={() => setSelected(null)} />
    </div>
  )
}

function Empty({ note }: { note?: string }) {
  return (
    <div className="tracking-widest uppercase" style={{ color: C.dim, fontSize: 10, padding: '24px 0', textAlign: 'center' }}>
      {note ?? 'NO DATA'}
    </div>
  )
}

function median(xs: number[]): number {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}
