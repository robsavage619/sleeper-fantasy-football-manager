import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import {
  api,
  type Finding,
  type ProspectAthleticism,
  type ProspectMarket,
  type ProspectProfile,
  type ProspectScoutFinding,
  type ProspectScoutingReport,
  type ProspectSignal,
} from '@/lib/api'

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

const C = {
  bg: '#060a12',
  card: '#09111f',
  border: '#162035',
  text: '#e8eef6',
  muted: '#6a8098',
  dim: '#3d5070',
  green: '#1a9b5e',
  amber: '#d4860c',
  cyan: '#00b8cc',
  red: '#c93328',
  blue: '#3a8cd4',
}

const TONE_COLOR: Record<string, string> = {
  positive: C.green,
  caution: C.amber,
  neutral: C.blue,
}

const TIMELINE_COLOR: Record<string, string> = {
  ASCENDING: C.green,
  DEVELOPING: C.cyan,
  'READY-NOW': C.amber,
  'WIN-NOW': C.red,
}

const CAPITAL_COLOR: Record<string, string> = {
  PREMIUM: C.amber,
  'DAY 2': C.blue,
  'DAY 3': C.muted,
}

const GRADE_COLOR: Record<string, string> = {
  ELITE: C.green,
  GOOD: C.blue,
  AVERAGE: C.muted,
  BELOW: C.amber,
}

function inchesToFtIn(inches: number | null): string {
  if (!inches) return '—'
  return `${Math.floor(inches / 12)}'${inches % 12}"`
}

function Section({ title, accent, children }: { title: string; accent?: string; children: ReactNode }) {
  return (
    <section style={{ borderTop: `1px solid ${C.border}`, padding: '14px 18px' }}>
      <div
        className="tracking-[0.28em] uppercase"
        style={{ color: accent ?? C.muted, fontSize: 10, marginBottom: 10, fontWeight: 700 }}
      >
        {title}
      </div>
      {children}
    </section>
  )
}

function StatCell({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, background: C.card, padding: '8px 10px', borderRadius: 2 }}>
      <div className="tracking-[0.2em] uppercase" style={{ color: C.dim, fontSize: 8 }}>
        {label}
      </div>
      <div
        style={{
          color: color ?? C.text,
          fontFamily: "'DM Mono', monospace",
          fontSize: 17,
          fontWeight: 700,
          lineHeight: 1.1,
          marginTop: 3,
        }}
      >
        {value}
      </div>
      {sub && <div style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Chip({ text, color }: { text: string; color: string }) {
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: '2px 6px',
        color,
        background: `${color}1c`,
        border: `1px solid ${color}55`,
        borderRadius: 1,
        letterSpacing: '0.08em',
        fontFamily: "'DM Mono', monospace",
        whiteSpace: 'nowrap',
      }}
    >
      {text}
    </span>
  )
}

// Vertical trajectory bars — shows a metric rising/falling across seasons.
function BarChart({
  data,
  color,
  caption,
}: {
  data: Array<{ label: string; value: number }>
  color: string
  caption: string
}) {
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div>
      <div className="tracking-[0.18em] uppercase" style={{ color: C.dim, fontSize: 8, marginBottom: 8 }}>
        {caption}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, height: 96 }}>
        {data.map((d) => {
          const h = Math.max(4, Math.round((d.value / max) * 74))
          return (
            <div key={d.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <span style={{ color: C.text, fontSize: 11, fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                {d.value.toLocaleString()}
              </span>
              <div
                style={{
                  width: '100%',
                  maxWidth: 46,
                  height: h,
                  background: `linear-gradient(180deg, ${color}, ${color}55)`,
                  borderRadius: '2px 2px 0 0',
                }}
              />
              <span style={{ color: C.muted, fontSize: 10, fontFamily: "'DM Mono', monospace" }}>{d.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Horizontal meter — a value positioned within a [min,max] range.
function Meter({
  value,
  min,
  max,
  color,
  markers,
}: {
  value: number
  min: number
  max: number
  color: string
  markers?: Array<{ at: number; label: string }>
}) {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100))
  return (
    <div style={{ position: 'relative', height: 6, background: C.border, borderRadius: 3, marginTop: 6 }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
      {markers?.map((m) => {
        const mpct = Math.max(0, Math.min(100, ((m.at - min) / (max - min)) * 100))
        return (
          <div
            key={m.label}
            style={{ position: 'absolute', left: `${mpct}%`, top: -3, transform: 'translateX(-50%)' }}
          >
            <div style={{ width: 1, height: 12, background: C.dim }} />
            <span style={{ position: 'absolute', top: 13, left: '50%', transform: 'translateX(-50%)', fontSize: 7, color: C.dim, whiteSpace: 'nowrap' }}>
              {m.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// Aligned per-season stat table with a header row.
function StatTable({
  columns,
  rows,
  accent,
}: {
  columns: Array<{ key: string; label: string }>
  rows: Array<Record<string, string | number>>
  accent: string
}) {
  const grid = `48px repeat(${columns.length}, 1fr)`
  return (
    <div style={{ fontFamily: "'DM Mono', monospace" }}>
      <div
        className="tracking-wide"
        style={{ display: 'grid', gridTemplateColumns: grid, gap: 6, padding: '4px 8px', color: C.dim, fontSize: 8 }}
      >
        <span>YR</span>
        {columns.map((c) => (
          <span key={c.key} style={{ textAlign: 'right' }}>
            {c.label}
          </span>
        ))}
      </div>
      <div style={{ display: 'grid', gap: 1, background: C.border }}>
        {rows.map((row, i) => (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: grid,
              gap: 6,
              padding: '6px 8px',
              background: C.card,
              fontSize: 12,
              boxShadow: `inset 2px 0 0 ${accent}`,
            }}
          >
            <span style={{ color: C.text, fontWeight: 700 }}>{row.season}</span>
            {columns.map((c) => (
              <span key={c.key} style={{ textAlign: 'right', color: c.key.includes('td') ? accent : C.muted }}>
                {row[c.key]}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Signals strip — the sharp-manager fast read ───────────────────────────────

function SignalsStrip({ signals }: { signals: ProspectSignal[] }) {
  if (signals.length === 0) return null
  return (
    <div style={{ padding: '14px 18px', borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 6 }}>
      {signals.map((s, i) => {
        const color = TONE_COLOR[s.tone] ?? C.muted
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, boxShadow: `inset 2px 0 0 ${color}`, paddingLeft: 10 }}>
            <span style={{ color, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{s.label}</span>
            <span style={{ color: C.muted, fontSize: 11, lineHeight: 1.4 }}>{s.detail}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Market consensus ──────────────────────────────────────────────────────────

function MarketSection({ market }: { market: ProspectMarket }) {
  const trend = market.trend_30day
  const timeline = market.player_timeline
  return (
    <Section title="Market Consensus · FantasyCalc" accent={C.cyan}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 8 }}>
        <StatCell label="Dyn Value" value={market.value != null ? String(market.value) : '—'} color={C.amber} />
        <StatCell
          label="Overall"
          value={market.overall_rank != null ? `#${market.overall_rank}` : '—'}
          sub={market.tier != null ? `tier ${market.tier}` : undefined}
        />
        <StatCell label="Positional" value={market.position_rank != null ? `#${market.position_rank}` : '—'} />
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {trend != null && trend !== 0 && (
          <Chip
            text={`${trend > 0 ? '▲' : '▼'} ${trend > 0 ? '+' : ''}${trend} 30d`}
            color={trend > 0 ? C.green : C.red}
          />
        )}
        {timeline && (
          <Chip
            text={`${timeline}${market.dynasty_premium_pct != null ? ` (${market.dynasty_premium_pct > 0 ? '+' : ''}${market.dynasty_premium_pct}%)` : ''}`}
            color={TIMELINE_COLOR[timeline] ?? C.muted}
          />
        )}
        {market.roster_pct != null && <Chip text={`rostered ${(market.roster_pct * 100).toFixed(0)}%`} color={C.muted} />}
        {market.adp != null && <Chip text={`ADP ${market.adp.toFixed(1)}`} color={C.muted} />}
        {market.volatility_pct != null && market.volatility_pct >= 8 && (
          <Chip text={`volatile ${market.volatility_pct}%`} color={C.amber} />
        )}
      </div>
    </Section>
  )
}

// ── Draft capital ─────────────────────────────────────────────────────────────

function DraftCapitalSection({ report }: { report: ProspectScoutingReport }) {
  const cap = report.draft_capital
  return (
    <Section title="NFL Draft Capital" accent={C.amber}>
      {cap && cap.round ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <Chip text={cap.capital_tier ?? 'DRAFTED'} color={CAPITAL_COLOR[cap.capital_tier ?? ''] ?? C.muted} />
          <span style={{ color: C.text, fontSize: 14, fontFamily: "'DM Mono', monospace" }}>
            Round {cap.round}
            {cap.pick != null ? ` · Pick ${cap.pick}` : ''}
            {cap.team ? ` → ${cap.team}` : ''}
          </span>
          {cap.year != null && <span style={{ color: C.dim, fontSize: 11 }}>{cap.year} draft</span>}
        </div>
      ) : (
        <div style={{ color: C.dim, fontSize: 12 }}>Undrafted / no draft capital on record.</div>
      )}
    </Section>
  )
}

// ── Athletic profile ──────────────────────────────────────────────────────────

function AthleticSection({ ath }: { ath: ProspectAthleticism }) {
  const cells: Array<[string, string]> = []
  if (ath.forty) cells.push(['40-YD', ath.forty.toFixed(2)])
  if (ath.vertical) cells.push(['VERT', `${ath.vertical}"`])
  if (ath.broad_jump) cells.push(['BROAD', `${ath.broad_jump}"`])
  if (ath.bench) cells.push(['BENCH', String(ath.bench)])
  if (ath.cone) cells.push(['3-CONE', ath.cone.toFixed(2)])
  if (ath.shuttle) cells.push(['SHUTTLE', ath.shuttle.toFixed(2)])

  const gradeColor = ath.athletic_grade ? (GRADE_COLOR[ath.athletic_grade] ?? C.muted) : C.muted

  return (
    <Section title="Athletic Profile · Combine" accent={C.blue}>
      {ath.speed_score != null && (
        <div style={{ marginBottom: cells.length ? 12 : 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }}>
            <span className="tracking-[0.18em] uppercase" style={{ color: C.dim, fontSize: 8 }}>
              Speed score
            </span>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ color: gradeColor, fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
                {ath.speed_score}
              </span>
              {ath.athletic_grade && <Chip text={ath.athletic_grade} color={gradeColor} />}
            </span>
          </div>
          {/* ~90 = below avg, 100 = avg NFL RB, 110+ = elite */}
          <Meter
            value={ath.speed_score}
            min={85}
            max={125}
            color={gradeColor}
            markers={[
              { at: 100, label: 'avg' },
              { at: 110, label: 'elite' },
            ]}
          />
        </div>
      )}
      {cells.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(cells.length, 3)}, 1fr)`, gap: 6, marginTop: ath.speed_score != null ? 20 : 0 }}>
          {cells.map(([label, value]) => (
            <StatCell key={label} label={label} value={value} />
          ))}
        </div>
      ) : (
        <div style={{ color: C.dim, fontSize: 12, marginTop: 8 }}>Did not run combine drills (measurables only).</div>
      )}
    </Section>
  )
}

// ── College production ────────────────────────────────────────────────────────

const RECEIVING_COLS = [
  { key: 'receptions', label: 'REC' },
  { key: 'yards', label: 'YDS' },
  { key: 'touchdowns', label: 'TD' },
  { key: 'ypr', label: 'YPR' },
]
const RUSHING_COLS = [
  { key: 'carries', label: 'CAR' },
  { key: 'yards', label: 'YDS' },
  { key: 'touchdowns', label: 'TD' },
  { key: 'ypc', label: 'YPC' },
]
const PASSING_COLS = [
  { key: 'yards', label: 'YDS' },
  { key: 'touchdowns', label: 'TD' },
  { key: 'interceptions', label: 'INT' },
  { key: 'comp_pct', label: 'CMP%' },
  { key: 'ypa', label: 'YPA' },
]

function CollegeSection({ report }: { report: ProspectScoutingReport }) {
  const college = report.college
  const pos = report.identity.position

  // Oldest → newest so the trajectory reads left-to-right.
  const chrono = [...college.seasons].sort((a, b) => a.season - b.season)

  // Which category is this player's headline? Drives the trajectory chart.
  const headline: 'passing' | 'rushing' | 'receiving' =
    pos === 'QB' ? 'passing' : pos === 'RB' ? 'rushing' : 'receiving'
  const headlineLabel =
    headline === 'passing' ? 'PASS YDS BY SEASON' : headline === 'rushing' ? 'RUSH YDS BY SEASON' : 'REC YDS BY SEASON'

  const trajectory = chrono
    .map((s) => ({ label: `'${String(s.season).slice(2)}`, value: s[headline]?.yards ?? 0 }))
    .filter((d) => d.value > 0)

  const rows = (cat: 'receiving' | 'rushing' | 'passing') =>
    chrono
      .filter((s) => s[cat])
      .map((s) => ({ season: s.season, ...(s[cat] as Record<string, number>) }))

  const recRows = rows('receiving')
  const rushRows = rows('rushing')
  const passRows = rows('passing')

  return (
    <Section title="College Production · ESPN" accent={C.green}>
      {college.has_data ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {trajectory.length >= 2 && (
            <BarChart data={trajectory} color={C.green} caption={headlineLabel} />
          )}

          {passRows.length > 0 && (
            <div>
              <TableLabel text="Passing" />
              <StatTable columns={PASSING_COLS} rows={passRows} accent={C.blue} />
            </div>
          )}
          {rushRows.length > 0 && (
            <div>
              <TableLabel text="Rushing" />
              <StatTable columns={RUSHING_COLS} rows={rushRows} accent={C.green} />
            </div>
          )}
          {recRows.length > 0 && (
            <div>
              <TableLabel text="Receiving" />
              <StatTable columns={RECEIVING_COLS} rows={recRows} accent={C.amber} />
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', color: C.dim, fontSize: 9 }}>
            {college.recruiting_rank != null ? (
              <span>
                Recruiting #{college.recruiting_rank}
                {college.stars != null ? ` · ${college.stars}★` : ''}
              </span>
            ) : (
              <span />
            )}
            {college.source && <span>via {college.source}</span>}
          </div>
        </div>
      ) : (
        <div style={{ color: C.dim, fontSize: 12, lineHeight: 1.5 }}>
          No college box-score data matched for this player.
        </div>
      )}
    </Section>
  )
}

function TableLabel({ text }: { text: string }) {
  return (
    <div className="tracking-[0.18em] uppercase" style={{ color: C.muted, fontSize: 9, marginBottom: 4, fontWeight: 700 }}>
      {text}
    </div>
  )
}

// ── Roster fit ────────────────────────────────────────────────────────────────

function RosterFitSection({ report }: { report: ProspectScoutingReport }) {
  const fit = report.roster_fit
  const pos = report.identity.position
  if (!fit) return null
  const verdictColor = fit.timeline_verdict?.startsWith('ALIGNED')
    ? C.green
    : fit.timeline_verdict?.startsWith('OFF')
      ? C.amber
      : C.muted
  return (
    <Section title="Fit For My Roster" accent={C.amber}>
      <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>
        {fit.position_rank != null ? (
          <div style={{ marginBottom: 8 }}>
            My {pos} depth ranks{' '}
            <span style={{ color: C.text, fontFamily: "'DM Mono', monospace" }}>
              #{fit.position_rank} of {fit.position_of}
            </span>{' '}
            ({fit.position_tier} tier, league avg {fit.position_league_avg})
          </div>
        ) : null}
        <div style={{ marginBottom: fit.timeline_verdict ? 8 : 0 }}>
          Contention window: <span style={{ color: C.text }}>{fit.contention_label}</span> ({fit.contention_window}) —{' '}
          {fit.contention_rationale}
        </div>
        {fit.timeline_verdict && (
          <div style={{ boxShadow: `inset 2px 0 0 ${verdictColor}`, paddingLeft: 10, color: verdictColor, fontWeight: 600 }}>
            {fit.timeline_verdict}
          </div>
        )}
      </div>
    </Section>
  )
}

// ── AI scouting & comps ───────────────────────────────────────────────────────

function AiScoutingSection({ prospect }: { prospect: ProspectProfile }) {
  const [showPrompt, setShowPrompt] = useState(false)
  const [copied, setCopied] = useState(false)

  const { data: promptData } = useQuery({
    queryKey: ['prospect-scouting-prompt', prospect.name, prospect.college, prospect.year],
    queryFn: () =>
      api.prospectScoutingPrompt({
        name: prospect.name,
        position: prospect.position,
        college: prospect.college,
        year: prospect.year,
        age: prospect.age,
        player_id: prospect.player_id,
        recruiting_rank: prospect.recruiting_rank,
        stars: prospect.stars,
        dynasty_prospect_score: prospect.dynasty_prospect_score,
      }),
    staleTime: 10 * 60 * 1000,
  })

  const { data: findings } = useQuery({
    queryKey: ['findings', 'prospect_scout'],
    queryFn: () => api.findings('prospect_scout'),
    staleTime: 60 * 1000,
  })

  const scout = useMemo(() => {
    if (!findings) return null
    const matches = findings.filter((f: Finding) => {
      const body = f.body as unknown as ProspectScoutFinding
      if (prospect.player_id && body.player_id) return body.player_id === prospect.player_id
      return body.name === prospect.name && body.college === prospect.college
    })
    if (matches.length === 0) return null
    const newest = matches.reduce((a, b) => (b.created_at > a.created_at ? b : a))
    return newest.body as unknown as ProspectScoutFinding
  }, [findings, prospect])

  function copyPrompt() {
    if (promptData?.prompt) {
      navigator.clipboard.writeText(promptData.prompt)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <Section title="AI Scouting & NFL Comps" accent={C.cyan}>
      {scout ? (
        <div>
          <div style={{ marginBottom: 12 }}>
            <div className="tracking-[0.18em] uppercase" style={{ color: C.cyan, fontSize: 9, marginBottom: 4 }}>
              Verdict
            </div>
            <div style={{ color: C.text, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{scout.verdict}</div>
            <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>{scout.case}</div>
          </div>
          {scout.comps.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div className="tracking-[0.18em] uppercase" style={{ color: C.cyan, fontSize: 9, marginBottom: 6 }}>
                NFL Comps
              </div>
              <div style={{ display: 'grid', gap: 1, background: C.border }}>
                {scout.comps.map((comp, i) => (
                  <div key={i} style={{ background: C.card, padding: '8px 10px' }}>
                    <div style={{ color: C.text, fontSize: 12, fontWeight: 700 }}>{comp.name}</div>
                    <div style={{ color: C.muted, fontSize: 11, marginTop: 2, lineHeight: 1.4 }}>{comp.rationale}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {scout.consensus_check && (
            <div style={{ marginBottom: 12 }}>
              <div className="tracking-[0.18em] uppercase" style={{ color: C.cyan, fontSize: 9, marginBottom: 4 }}>
                Consensus Check
              </div>
              <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>{scout.consensus_check}</div>
            </div>
          )}
          {scout.risk_notes.length > 0 && (
            <div>
              <div className="tracking-[0.18em] uppercase" style={{ color: C.amber, fontSize: 9, marginBottom: 4 }}>
                Risk Factors
              </div>
              <ul style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, paddingLeft: 16, margin: 0 }}>
                {scout.risk_notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </div>
          )}
          {scout.sources && scout.sources.length > 0 && (
            <div style={{ color: C.dim, fontSize: 10, marginTop: 10 }}>Sources: {scout.sources.join(', ')}</div>
          )}
          <div style={{ color: C.dim, fontSize: 10, marginTop: 6, fontStyle: 'italic' }}>
            AI-generated — not a reproduction of any paywalled scouting service.
          </div>
        </div>
      ) : (
        <div>
          <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5, marginBottom: 10 }}>
            No AI report yet. Copy this prompt into a Claude Code session — it web-searches consensus rankings and
            scouting coverage, then reasons over the market, draft capital, athleticism, and your roster fit to post
            NFL comps and a verdict back.
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <button
              onClick={copyPrompt}
              disabled={!promptData}
              style={{
                background: 'none',
                border: `1px solid ${C.border}`,
                borderRadius: 2,
                padding: '5px 12px',
                cursor: promptData ? 'pointer' : 'default',
                color: copied ? C.green : C.cyan,
                fontSize: 10,
                letterSpacing: '0.06em',
                fontFamily: "'DM Mono', monospace",
              }}
            >
              {copied ? 'COPIED' : 'COPY PROMPT'}
            </button>
            <button
              onClick={() => setShowPrompt((v) => !v)}
              style={{
                background: 'none',
                border: `1px solid ${C.border}`,
                borderRadius: 2,
                padding: '5px 12px',
                cursor: 'pointer',
                color: C.muted,
                fontSize: 10,
                letterSpacing: '0.06em',
                fontFamily: "'DM Mono', monospace",
              }}
            >
              {showPrompt ? 'HIDE' : 'SHOW'}
            </button>
          </div>
          {showPrompt && promptData && (
            <pre
              style={{
                background: C.card,
                border: `1px solid ${C.border}`,
                borderRadius: 2,
                padding: 12,
                margin: 0,
                fontSize: 10,
                color: C.muted,
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: "'DM Mono', monospace",
                lineHeight: 1.6,
                maxHeight: 320,
                overflowY: 'auto',
              }}
            >
              {promptData.prompt}
            </pre>
          )}
        </div>
      )}
    </Section>
  )
}

// ── Body ──────────────────────────────────────────────────────────────────────

function ScoutingBody({ prospect }: { prospect: ProspectProfile }) {
  const color = POS_COLOR[prospect.position] ?? C.muted

  const { data: report, isLoading, error } = useQuery({
    queryKey: ['prospect-scouting', prospect.player_id ?? prospect.name, prospect.year],
    queryFn: () =>
      api.prospectScouting({
        name: prospect.name,
        position: prospect.position,
        college: prospect.college,
        year: prospect.year,
        age: prospect.age,
        player_id: prospect.player_id,
        recruiting_rank: prospect.recruiting_rank,
        stars: prospect.stars,
        dynasty_prospect_score: prospect.dynasty_prospect_score,
      }),
    staleTime: 10 * 60 * 1000,
  })

  const id = report?.identity
  const dqColor = report
    ? report.data_quality === 'FULL'
      ? C.green
      : report.data_quality === 'PARTIAL'
        ? C.cyan
        : C.amber
    : C.muted

  const subline = [
    prospect.position,
    id?.nfl_team ? `→ ${id.nfl_team}` : prospect.college,
    id?.age != null ? `age ${id.age.toFixed(1)}` : prospect.age != null ? `age ${prospect.age.toFixed(1)}` : null,
    id?.height_in ? inchesToFtIn(id.height_in) : null,
    id?.weight ? `${id.weight} lbs` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <div style={{ padding: '18px', borderBottom: `1px solid ${C.border}` }}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="tracking-[0.3em] uppercase" style={{ color, fontSize: 10 }}>
              {subline}
            </div>
            <h2
              className="uppercase leading-none"
              style={{
                color: C.text,
                fontFamily: "'Barlow Condensed', sans-serif",
                fontSize: 34,
                fontWeight: 800,
                marginTop: 5,
              }}
            >
              {prospect.name}
            </h2>
            <div style={{ color: C.dim, fontSize: 11, marginTop: 4 }}>
              {prospect.college} · {prospect.year} class · heuristic {prospect.dynasty_prospect_score.toFixed(1)}
            </div>
          </div>
          {report && <Chip text={report.data_quality} color={dqColor} />}
        </div>
      </div>

      {isLoading && (
        <div className="p-8 tracking-widest uppercase" style={{ color: C.dim, fontSize: 12 }}>
          Assembling scouting report…
        </div>
      )}
      {error && (
        <div className="p-8" style={{ color: C.red, fontSize: 13 }}>
          {String(error)}
        </div>
      )}

      {report && (
        <>
          <SignalsStrip signals={report.signals} />
          {report.market && <MarketSection market={report.market} />}
          <DraftCapitalSection report={report} />
          {report.athleticism && <AthleticSection ath={report.athleticism} />}
          <CollegeSection report={report} />
          <RosterFitSection report={report} />
          <AiScoutingSection prospect={prospect} />
          {report.sources_used.length > 0 && (
            <div
              className="tracking-wide uppercase"
              style={{ borderTop: `1px solid ${C.border}`, padding: '10px 18px', fontSize: 9, color: C.dim }}
            >
              Sources: {report.sources_used.join(' · ')}
            </div>
          )}
        </>
      )}
    </>
  )
}

export function ProspectScoutingDrawer({
  prospect,
  onClose,
}: {
  prospect: ProspectProfile | null
  onClose: () => void
}) {
  return (
    <AnimatePresence>
      {prospect && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.45)', zIndex: 40 }}
          />
          <motion.aside
            initial={{ x: 560 }}
            animate={{ x: 0 }}
            exit={{ x: 560 }}
            transition={{ type: 'spring', damping: 30, stiffness: 260 }}
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 'min(560px, 100vw)',
              background: C.bg,
              borderLeft: `1px solid ${C.border}`,
              zIndex: 50,
              overflowY: 'auto',
              boxShadow: '-24px 0 60px rgba(0,0,0,0.45)',
            }}
          >
            <button
              onClick={onClose}
              aria-label="Close prospect scouting report"
              style={{
                position: 'absolute',
                top: 12,
                right: 12,
                border: `1px solid #24344f`,
                background: C.card,
                color: C.muted,
                width: 28,
                height: 28,
                borderRadius: 2,
                cursor: 'pointer',
                zIndex: 2,
              }}
            >
              X
            </button>
            <ScoutingBody prospect={prospect} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
