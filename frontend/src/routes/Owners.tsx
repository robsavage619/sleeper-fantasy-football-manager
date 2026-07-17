import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { Group } from '@visx/group'
import { ParentSize } from '@visx/responsive'
import { scaleLinear } from '@visx/scale'
import { Circle, Line } from '@visx/shape'
import { Text } from '@visx/text'
import {
  api,
  type FaabEntry,
  type OwnerProfile,
  type OwnerSkillIndex,
  type OwnerDossier,
  type OwnerHistory,
  type DossierPlayer,
  type PositionRank,
  type DossierPick,
  type TransactionValue,
  type DraftProfile,
} from '@/lib/api'
import { POS_COLOR } from '@/components/viz'

function useMyRosterId(): number | null {
  const { data } = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60 * 1000 })
  return data?.roster_id ?? null
}

// ── palette ────────────────────────────────────────────────────────────────
const C = {
  bg: '#060a12', panel: '#0c1625', deep: '#070c16', border: '#162035', borderHi: '#1e3050',
  cyan: '#00b8cc', amber: '#d4860c', green: '#1a9b5e', red: '#c93328',
  text: '#e8eef6', muted: '#6a8098', dim: '#3d5070', faint: '#2a4a60',
}

const ARCH_STYLE: Record<OwnerProfile['archetype'], { color: string; bg: string; border: string }> = {
  REBUILDER: { color: '#d4860c', bg: 'rgba(212,134,12,0.1)', border: 'rgba(212,134,12,0.25)' },
  CONTENDER: { color: '#1a9b5e', bg: 'rgba(26,155,94,0.1)', border: 'rgba(26,155,94,0.25)' },
  BALANCED:  { color: '#00b8cc', bg: 'rgba(0,184,204,0.1)',  border: 'rgba(0,184,204,0.25)' },
  UNKNOWN:   { color: '#6a8098', bg: 'rgba(106,128,152,0.08)', border: 'rgba(106,128,152,0.2)' },
}
const ARCH_BORDER: Record<OwnerProfile['archetype'], string> = {
  REBUILDER: '#d4860c', CONTENDER: '#1a9b5e', BALANCED: '#00b8cc', UNKNOWN: '#3d5070',
}
const TRADE_NODE_COLOR: Record<OwnerProfile['archetype'], string> = {
  REBUILDER: '#3a8cd4', CONTENDER: '#d4860c', BALANCED: '#6a8098', UNKNOWN: '#3d5070',
}
const TIER_COLOR: Record<OwnerSkillIndex['skill_tier'], string> = {
  ELITE: '#00b8cc', STRONG: '#1a9b5e', AVERAGE: '#d4860c', WEAK: '#c93328',
}
const THREAT: Record<OwnerSkillIndex['skill_tier'], { label: string; color: string }> = {
  ELITE:   { label: 'DANGEROUS', color: '#c93328' },
  STRONG:  { label: 'SOLID',     color: '#d4860c' },
  AVERAGE: { label: 'BEATABLE',  color: '#00b8cc' },
  WEAK:    { label: 'PREY',      color: '#1a9b5e' },
}
const WINDOW_COLOR: Record<string, string> = {
  ASCENDING: '#1a9b5e', OPENING: '#24a870', OPEN: '#00b8cc', CLOSING: '#d4860c', RETOOLING: '#c93328',
}
const AGE_BAND_COLOR = ['#1a9b5e', '#24a870', '#00b8cc', '#d4860c', '#c93328']
const POS_TIER_COLOR: Record<PositionRank['tier'], string> = {
  DEEP: '#1a9b5e', SOLID: '#24a870', AVERAGE: '#6a8098', THIN: '#c93328',
}
const APPROACH_COLOR: Record<string, string> = {
  OPEN: '#1a9b5e', SELECTIVE: '#00b8cc', INSULAR: '#d4860c', DORMANT: '#6a8098',
}
const ROUND_LABEL: Record<number, string> = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' }

const barlow = "'Barlow Condensed', sans-serif"
const mono = "'DM Mono', monospace"

// ── shared bits ──────────────────────────────────────────────────────────────
function getInitials(name: string | null): string {
  if (!name) return '?'
  return name.split(/[\s_-]/).map(p => p[0]).join('').toUpperCase().slice(0, 2)
}

function Avatar({ avatar, name, size = 40 }: { avatar: string | null; name: string; size?: number }) {
  const [err, setErr] = useState(false)
  return avatar && !err ? (
    <img src={`https://sleepercdn.com/avatars/thumbs/${avatar}`} alt={name} onError={() => setErr(true)}
      style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover', border: `1px solid ${C.border}`, flexShrink: 0 }} />
  ) : (
    <div style={{
      width: size, height: size, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,184,204,0.08)', border: '1px solid rgba(0,184,204,0.3)', color: C.cyan,
      fontSize: size * 0.32, fontWeight: 700, fontFamily: barlow, letterSpacing: '0.05em', flexShrink: 0,
    }}>{getInitials(name)}</div>
  )
}

function PlayerHeadshot({ playerId, name, size = 32 }: { playerId: string; name: string; size?: number }) {
  const [err, setErr] = useState(false)
  return !err ? (
    <img src={`https://sleepercdn.com/content/nfl/players/thumb/${playerId}.jpg`} alt={name} onError={() => setErr(true)}
      style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover', objectPosition: 'top', background: C.deep, border: `1px solid ${C.border}`, flexShrink: 0 }} />
  ) : (
    <div style={{
      width: size, height: size, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: C.deep, border: `1px solid ${C.border}`, color: C.dim, fontSize: size * 0.3, fontWeight: 700, fontFamily: barlow, flexShrink: 0,
    }}>{getInitials(name)}</div>
  )
}

function ArchetypeBadge({ archetype, size = 'sm' }: { archetype: OwnerProfile['archetype']; size?: 'sm' | 'md' }) {
  const s = ARCH_STYLE[archetype]
  return (
    <span style={{
      fontSize: size === 'md' ? 10 : 9, fontWeight: 700, letterSpacing: '0.2em', padding: size === 'md' ? '3px 8px' : '2px 6px',
      borderRadius: 1, textTransform: 'uppercase', flexShrink: 0, color: s.color, background: s.bg, border: `1px solid ${s.border}`,
    }}>{archetype}</span>
  )
}

function Chip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 2, padding: '6px 11px', borderRadius: 2,
      background: `${color}12`, border: `1px solid ${color}35`,
    }}>
      <span style={{ fontFamily: barlow, fontSize: 9, letterSpacing: '0.18em', color: C.muted, textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontFamily: barlow, fontSize: 14, fontWeight: 700, letterSpacing: '0.06em', color, textTransform: 'uppercase', lineHeight: 1 }}>{value}</span>
    </div>
  )
}

function TagPill({ text }: { text: string }) {
  return (
    <span style={{
      fontFamily: mono, fontSize: 10, letterSpacing: '0.06em', padding: '3px 8px', borderRadius: 1,
      color: C.muted, background: C.deep, border: `1px solid ${C.border}`,
    }}>{text}</span>
  )
}

function PosPills({ positions }: { positions: Record<string, number> }) {
  const ORDER = ['QB', 'RB', 'WR', 'TE']
  return (
    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
      {ORDER.filter(p => positions[p]).map(pos => (
        <span key={pos} style={{
          fontSize: 11, fontFamily: mono, fontWeight: 500, padding: '2px 7px', borderRadius: 2,
          color: POS_COLOR[pos], background: `${POS_COLOR[pos]}18`, border: `1px solid ${POS_COLOR[pos]}30`,
        }}>{positions[pos]} {pos}</span>
      ))}
    </div>
  )
}

function Label({ children, color = C.dim }: { children: React.ReactNode; color?: string }) {
  return <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.2em', color, textTransform: 'uppercase' }}>{children}</span>
}

function Stat({ value, label, color = C.text }: { value: React.ReactNode; label: string; color?: string }) {
  return (
    <div>
      <div style={{ fontFamily: mono, fontSize: 19, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      <div style={{ marginTop: 3 }}><Label>{label}</Label></div>
    </div>
  )
}

// ── card (grid) ──────────────────────────────────────────────────────────────
function CardMetricRow({ label, value, barPct, barColor, note }: {
  label: string; value: string; barPct: number; barColor: string; note?: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.15em', color: '#4a6080', textTransform: 'uppercase', width: 80, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 3, background: C.border, borderRadius: 1, position: 'relative' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${Math.min(barPct * 100, 100)}%`, background: barColor, borderRadius: 1, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontFamily: mono, fontSize: 11, color: barPct > 0.05 ? barColor : '#4a6080', width: 54, textAlign: 'right', flexShrink: 0 }}>{value}</span>
      {note && <span style={{ fontFamily: mono, fontSize: 9, color: C.dim }}>{note}</span>}
    </div>
  )
}

function OwnerCard({ profile, index, skill, history, faab, onClick }: {
  profile: OwnerProfile; index: number; skill?: OwnerSkillIndex; history?: OwnerHistory; faab?: FaabEntry; onClick: () => void
}) {
  const [hovered, setHovered] = useState(false)
  const displayName = profile.display_name ?? profile.user_id
  const isMe = profile.is_me
  const rvRaw = skill?.roster_value_pct ?? 1
  const nickname = history?.behavioral_type

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }}
      onClick={onClick} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? '#0f1d30' : C.panel, border: `1px solid ${hovered ? C.borderHi : C.border}`,
        boxShadow: `inset 3px 0 0 ${ARCH_BORDER[profile.archetype]}`, borderRadius: 2,
        padding: '14px 16px 14px 18px', display: 'flex', flexDirection: 'column', gap: 10,
        cursor: 'pointer', transition: 'background 0.12s, border-color 0.12s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Avatar avatar={profile.avatar} name={displayName} size={40} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: barlow, fontSize: 18, fontWeight: 700, color: C.text, letterSpacing: '0.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{displayName}</span>
            <ArchetypeBadge archetype={profile.archetype} />
            {isMe && <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.25em', padding: '2px 6px', color: C.cyan, background: 'rgba(0,184,204,0.1)', border: '1px solid rgba(0,184,204,0.3)', borderRadius: 1, textTransform: 'uppercase' }}>YOUR TEAM</span>}
          </div>
          {nickname && <div style={{ fontFamily: barlow, fontSize: 11, letterSpacing: '0.14em', color: '#5a7ba0', textTransform: 'uppercase', marginTop: 2 }}>{nickname}</div>}
        </div>
        {skill && (
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontFamily: mono, fontSize: 20, fontWeight: 700, color: TIER_COLOR[skill.skill_tier], lineHeight: 1 }}>{Math.round(skill.skill_score)}</div>
            <div style={{ fontFamily: barlow, fontSize: 9, letterSpacing: '0.15em', color: '#4a6080', textTransform: 'uppercase' }}>SKILL</div>
          </div>
        )}
      </div>

      <PosPills positions={profile.positions} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.amber }}>{profile.picks_owned} picks</span>
          {history && <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>{history.trade_count} trades</span>}
          {faab && <span style={{ fontFamily: mono, fontSize: 11, color: C.green }}>${faab.faab_remaining} FAAB</span>}
        </div>
        <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>{profile.player_count}p · {profile.taxi_count} taxi</span>
      </div>

      {skill && (
        <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <CardMetricRow label="LINEUP EFF" barPct={skill.lineup_efficiency} barColor={C.green} value={`${Math.round(skill.lineup_efficiency * 100)}%`} />
          <CardMetricRow label="ROSTER VAL" barPct={Math.min(rvRaw / 2, 1)} barColor={rvRaw >= 1 ? C.green : C.amber} value={`${rvRaw >= 1 ? '+' : ''}${Math.round((rvRaw - 1) * 100)}%`} />
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: -4 }}>
        <span style={{ fontFamily: barlow, fontSize: 9, letterSpacing: '0.2em', color: hovered ? '#3a7cc0' : '#2d4a5a', textTransform: 'uppercase', transition: 'color 0.12s' }}>SCOUTING REPORT →</span>
      </div>
    </motion.div>
  )
}

// ── drawer: section ──────────────────────────────────────────────────────────
function Section({ title, kicker, children, span = 2, accent = '#3a7cc0' }: { title: string; kicker?: string; children: React.ReactNode; span?: 1 | 2; accent?: string }) {
  return (
    <div style={{ gridColumn: `span ${span}`, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2, padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
        <span style={{ fontFamily: barlow, fontSize: 12, letterSpacing: '0.28em', color: accent, textTransform: 'uppercase' }}>{title}</span>
        {kicker && <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>{kicker}</span>}
      </div>
      {children}
    </div>
  )
}

// ── SCOUTING VERDICT (hero) ──────────────────────────────────────────────────
function ScoutVerdict({ skill, history, dossier }: {
  skill?: OwnerSkillIndex; history?: OwnerHistory; dossier?: OwnerDossier
}) {
  const threat = skill ? THREAT[skill.skill_tier] : null
  const nickname = history?.behavioral_type ?? 'SCOUTING…'
  const approach = history?.approachability
  return (
    <div style={{
      gridColumn: 'span 2', background: 'linear-gradient(180deg, #0e1c30 0%, #0c1625 100%)',
      border: `1px solid ${C.borderHi}`, borderRadius: 2, padding: '18px 20px',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
        <span style={{ fontFamily: barlow, fontSize: 30, fontWeight: 800, letterSpacing: '0.03em', color: C.text, lineHeight: 1 }}>{nickname}</span>
        {dossier && (
          <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>
            {dossier.contention.label} · {dossier.value_rank ? `#${dossier.value_rank}/${dossier.league_size} value` : ''}
          </span>
        )}
      </div>

      {history?.behavioral_summary && (
        <p style={{ fontSize: 14, color: '#b8cfe4', lineHeight: 1.6, margin: '0 0 14px' }}>{history.behavioral_summary}</p>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: history?.behavioral_tags?.length ? 12 : 0 }}>
        {threat && <Chip label="THREAT" value={threat.label} color={threat.color} />}
        {history && <Chip label="ACTIVITY" value={history.trades_per_season >= 2 ? 'HIGH' : history.trades_per_season >= 0.8 ? 'MODERATE' : 'LOW'} color={history.trades_per_season >= 2 ? C.cyan : history.trades_per_season >= 0.8 ? C.amber : C.dim} />}
        {approach && <Chip label="APPROACH" value={approach} color={APPROACH_COLOR[approach] ?? C.muted} />}
        {history && <Chip label="PICKS" value={history.pick_lean} color={history.pick_lean === 'HOARDS' ? C.amber : history.pick_lean === 'SPENDS' ? C.cyan : C.dim} />}
        {history && history.adds_per_season >= 30 && <Chip label="WIRE" value="ACTIVE" color={C.green} />}
      </div>

      {history?.behavioral_tags && history.behavioral_tags.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {history.behavioral_tags.map(t => <TagPill key={t} text={t} />)}
        </div>
      )}
    </div>
  )
}

// ── vs YOU ───────────────────────────────────────────────────────────────────
function VsYou({ history }: { history: OwnerHistory }) {
  const myRosterId = useMyRosterId()
  const withMe = history.trades.filter(t => t.partner_roster_id === myRosterId)
  if (withMe.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontFamily: mono, fontSize: 12, color: C.dim }}>You've never traded with them. Untapped market.</span>
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: mono, fontSize: 20, fontWeight: 700, color: C.cyan, lineHeight: 1 }}>{withMe.length}</span>
        <span style={{ fontFamily: mono, fontSize: 12, color: C.muted }}>deal{withMe.length === 1 ? '' : 's'} with you · last {withMe[0].season} Wk {withMe[0].week}</span>
      </div>
      {withMe.slice(0, 2).map((t, i) => (
        <div key={i} style={{ display: 'flex', gap: 14, fontFamily: mono, fontSize: 11 }}>
          <span style={{ color: C.dim, width: 60, flexShrink: 0 }}>{t.season} W{t.week}</span>
          <span style={{ color: C.green }}>they got: {t.received.join(', ') || '—'}</span>
        </div>
      ))}
    </div>
  )
}

// ── TRADE BEHAVIOR ───────────────────────────────────────────────────────────
function PickLeanMeter({ netPicks }: { netPicks: number }) {
  const pos = Math.max(4, Math.min(96, 50 + netPicks * 6))
  const color = netPicks >= 2 ? C.amber : netPicks <= -2 ? C.cyan : C.muted
  return (
    <div>
      <div style={{ position: 'relative', height: 10, borderRadius: 2, overflow: 'hidden', display: 'flex' }}>
        <div style={{ flex: 1, background: `linear-gradient(90deg, ${C.cyan}55, ${C.panel})` }} />
        <div style={{ flex: 1, background: `linear-gradient(90deg, ${C.panel}, ${C.amber}55)` }} />
        <div style={{ position: 'absolute', top: -2, bottom: -2, left: `calc(${pos}% - 1.5px)`, width: 3, background: color, boxShadow: `0 0 6px ${color}` }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: netPicks <= -2 ? C.cyan : C.muted }}>◄ SPENDS (win-now)</span>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: netPicks >= 2 ? C.amber : C.muted }}>HOARDS (rebuild) ►</span>
      </div>
    </div>
  )
}

function SeasonBars({ data }: { data: Array<{ season: string; count: number }> }) {
  const max = Math.max(1, ...data.map(d => d.count))
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 52 }}>
      {data.map(d => (
        <div key={d.season} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
          <div style={{ width: '100%', display: 'flex', alignItems: 'flex-end', height: 36 }}>
            <div style={{ width: '100%', height: `${(d.count / max) * 100}%`, minHeight: d.count ? 3 : 0, background: d.count === max && max > 0 ? C.cyan : '#2a5878', borderRadius: 1, transition: 'height 0.4s ease' }} />
          </div>
          <span style={{ fontFamily: mono, fontSize: 10, color: d.count ? C.muted : C.faint }}>{d.count}</span>
          <span style={{ fontFamily: mono, fontSize: 9, color: C.faint }}>'{d.season.slice(2)}</span>
        </div>
      ))}
    </div>
  )
}

function TradeBehavior({ history }: { history: OwnerHistory }) {
  const partners = history.trade_partners.slice(0, 6)
  const hasWireData = history.adds_per_season > 0 || history.faab_spent > 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* trade stats */}
      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
        <Stat value={history.trade_count} label="TOTAL TRADES" color={C.cyan} />
        <Stat value={history.trades_per_season.toFixed(1)} label="PER SEASON" />
        <Stat value={`${history.net_picks >= 0 ? '+' : ''}${history.net_picks}`} label="NET PICKS" color={history.net_picks >= 0 ? C.amber : C.cyan} />
        <Stat value={history.avg_trade_size.toFixed(1)} label="ASSETS / DEAL" />
      </div>

      {/* pick philosophy */}
      <div>
        <div style={{ marginBottom: 8 }}><Label>PICK PHILOSOPHY</Label></div>
        <PickLeanMeter netPicks={history.net_picks} />
      </div>

      {/* season activity bars */}
      {history.trades_by_season && history.trades_by_season.length > 0 && (
        <div>
          <div style={{ marginBottom: 8 }}><Label>TRADE ACTIVITY BY SEASON</Label></div>
          <SeasonBars data={history.trades_by_season} />
        </div>
      )}

      {/* trade partners */}
      {partners.length > 0 && (
        <div>
          <div style={{ marginBottom: 8, display: 'flex', gap: 8, alignItems: 'baseline' }}>
            <Label>TRADE PARTNERS</Label>
            <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>
              {history.top_partner_share >= 0.6 ? 'concentrated — one crony' : 'spreads deals around'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {partners.map((p, i) => (
              <span key={i} style={{ fontFamily: mono, fontSize: 11, padding: '3px 9px', borderRadius: 2, color: C.text, background: C.deep, border: `1px solid ${C.border}` }}>
                {p.name ?? `roster ${p.roster_id}`} <span style={{ color: C.cyan }}>×{p.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* waiver / wire activity */}
      {hasWireData && (
        <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
          <div style={{ marginBottom: 10 }}><Label>WAIVER WIRE</Label></div>
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
            <Stat value={history.adds_per_season.toFixed(1)} label="ADDS / SEASON" />
            {history.faab_per_season > 0 && (
              <Stat value={`$${Math.round(history.faab_per_season)}`} label="FAAB / SEASON" color={C.amber} />
            )}
            {history.waiver_adds > 0 && history.free_agent_adds > 0 && (
              <Stat value={`${Math.round(history.waiver_adds / Math.max(1, history.waiver_adds + history.free_agent_adds) * 100)}%`} label="WAIVER USE" color={C.dim} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── PICK INVENTORY ───────────────────────────────────────────────────────────
function pickColor(round: number) {
  if (round === 1) return { text: C.amber, bg: 'rgba(212,134,12,0.1)', border: 'rgba(212,134,12,0.3)' }
  if (round === 2) return { text: C.cyan, bg: 'rgba(0,184,204,0.08)', border: 'rgba(0,184,204,0.2)' }
  return { text: C.muted, bg: C.deep, border: C.border }
}

function PickInventory({ picksOwned, picksTraded }: { picksOwned: DossierPick[]; picksTraded: DossierPick[] }) {
  const ownPicks = picksOwned.filter(p => p.source !== 'acquired')
  const acquiredPicks = picksOwned.filter(p => p.source === 'acquired')

  // Group a list of picks by season
  function bySeason(picks: DossierPick[]) {
    const map: Record<string, DossierPick[]> = {}
    for (const p of picks) {
      if (!map[p.season]) map[p.season] = []
      map[p.season].push(p)
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
  }

  if (picksOwned.length === 0 && picksTraded.length === 0) {
    return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>No future picks on hand.</span>
  }

  function PickGroup({ picks, label }: { picks: DossierPick[]; label: string }) {
    if (picks.length === 0) return null
    return (
      <div>
        <div style={{ marginBottom: 8 }}><Label>{label}</Label></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {bySeason(picks).map(([season, sPicksRaw]) => {
            const sPicks = [...sPicksRaw].sort((a, b) => a.round - b.round)
            return (
              <div key={season} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: barlow, fontSize: 11, letterSpacing: '0.12em', color: C.dim, width: 32, flexShrink: 0 }}>{season}</span>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {sPicks.map((p, i) => {
                    const col = pickColor(p.round)
                    return (
                      <span key={i} style={{
                        fontFamily: mono, fontSize: 11, padding: '3px 9px', borderRadius: 2,
                        color: col.text, background: col.bg, border: `1px solid ${col.border}`,
                      }}>{ROUND_LABEL[p.round] ?? `R${p.round}`}</span>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <PickGroup picks={ownPicks} label="OWN PICKS" />
      {acquiredPicks.length > 0 && ownPicks.length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}` }} />
      )}
      <PickGroup picks={acquiredPicks} label="ACQUIRED" />

      {picksTraded.length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
          <div style={{ marginBottom: 8 }}><Label color={C.red}>TRADED AWAY</Label></div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[...picksTraded].sort((a, b) => a.season.localeCompare(b.season) || a.round - b.round).map((p, i) => (
              <span key={i} style={{
                fontFamily: mono, fontSize: 11, padding: '3px 9px', borderRadius: 2,
                color: C.dim, background: C.deep, border: `1px solid ${C.border}`,
                textDecoration: 'line-through',
              }}>{p.season} {ROUND_LABEL[p.round] ?? `R${p.round}`}</span>
            ))}
          </div>
        </div>
      )}

      <span style={{ fontFamily: mono, fontSize: 10, color: C.faint }}>
        {ownPicks.length} own · {acquiredPicks.length} acquired · {picksTraded.length} traded away
      </span>
    </div>
  )
}

// ── POSITIONAL NEEDS ─────────────────────────────────────────────────────────
function PositionalNeeds({ ranks }: { ranks: PositionRank[] }) {
  const max = Math.max(1, ...ranks.map(r => Math.max(r.value, r.league_avg)))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {ranks.map(r => (
        <div key={r.position}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 700, color: POS_COLOR[r.position], width: 26, flexShrink: 0 }}>{r.position}</span>
            <div style={{ flex: 1, height: 13, background: C.deep, borderRadius: 1, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${(r.value / max) * 100}%`, background: POS_COLOR[r.position], opacity: 0.8, borderRadius: 1, transition: 'width 0.4s ease' }} />
              <div style={{ position: 'absolute', top: -1, bottom: -1, left: `calc(${(r.league_avg / max) * 100}% - 1px)`, width: 2, background: C.muted, opacity: 0.7 }} />
            </div>
            <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, width: 40, textAlign: 'right', flexShrink: 0 }}>#{r.rank}/{r.of}</span>
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 7px', borderRadius: 1, width: 58, textAlign: 'center', flexShrink: 0, color: POS_TIER_COLOR[r.tier], background: `${POS_TIER_COLOR[r.tier]}18`, border: `1px solid ${POS_TIER_COLOR[r.tier]}35` }}>{r.tier}</span>
          </div>
        </div>
      ))}
      <span style={{ fontFamily: mono, fontSize: 10, color: C.faint }}>bar = their value · tick = league avg · rank across {ranks[0]?.of ?? 10} teams</span>
    </div>
  )
}

// ── CONTENTION GAUGE ─────────────────────────────────────────────────────────
function ContentionGauge({ c }: { c: OwnerDossier['contention'] }) {
  const color = WINDOW_COLOR[c.label] ?? C.cyan
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span style={{ fontFamily: barlow, fontSize: 22, fontWeight: 800, color, letterSpacing: '0.04em', lineHeight: 1 }}>{c.label}</span>
        <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>{c.window}</span>
        <span style={{ fontFamily: mono, fontSize: 11, color, marginLeft: 'auto' }}>{Math.round(c.score)}/100</span>
      </div>
      <div style={{ position: 'relative', height: 10, borderRadius: 2, overflow: 'hidden', display: 'flex' }}>
        {['#c93328', '#d4860c', '#00b8cc', '#24a870', '#1a9b5e'].map((cc, i) => <div key={i} style={{ flex: 1, background: cc, opacity: 0.32 }} />)}
        <div style={{ position: 'absolute', top: -2, bottom: -2, left: `calc(${Math.min(Math.max(c.score, 0), 100)}% - 1.5px)`, width: 3, background: color, boxShadow: `0 0 6px ${color}` }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: C.muted }}>RETOOLING</span>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: C.muted }}>WIN-NOW</span>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: C.muted }}>ASCENDING</span>
      </div>
      <p style={{ fontSize: 12, color: C.muted, lineHeight: 1.55, margin: '10px 0 0' }}>{c.rationale}</p>
    </div>
  )
}

// ── AGE PYRAMID ──────────────────────────────────────────────────────────────
function AgePyramid({ buckets, avgAge, avgStarterAge }: { buckets: OwnerDossier['age_buckets']; avgAge: number; avgStarterAge: number }) {
  const maxVal = Math.max(1, ...buckets.map(b => b.value))
  return (
    <div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {buckets.map((b, i) => {
          const w = (b.value / maxVal) * 100
          const color = AGE_BAND_COLOR[i] ?? C.cyan
          return (
            <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, width: 42, textAlign: 'right', flexShrink: 0 }}>{b.label}</span>
              <div style={{ flex: 1, display: 'flex', justifyContent: 'center', height: 17, alignItems: 'center' }}>
                <div style={{ width: `${Math.max(w, b.count ? 4 : 0)}%`, height: 17, borderRadius: 1, background: color, opacity: b.count ? 0.85 : 0.12, display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: b.count ? 20 : 0, transition: 'width 0.4s ease' }}>
                  {b.count > 0 && <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: '#08111c' }}>{b.count}</span>}
                </div>
              </div>
              <span style={{ fontFamily: mono, fontSize: 10, color: b.count ? color : C.faint, width: 48, flexShrink: 0 }}>{b.value ? Math.round(b.value) : '—'}</span>
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 12, borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
        <Stat value={avgAge.toFixed(1)} label="AVG AGE" />
        <Stat value={avgStarterAge.toFixed(1)} label="STARTER AGE" />
        <div style={{ marginLeft: 'auto', alignSelf: 'flex-end' }}>
          <span style={{ fontFamily: mono, fontSize: 10, color: C.faint }}>bar = value · number = players</span>
        </div>
      </div>
    </div>
  )
}

// ── TOP ASSETS ───────────────────────────────────────────────────────────────
function slotBadge(p: DossierPlayer): { text: string; color: string } | null {
  if (p.is_taxi) return { text: 'TAXI', color: C.amber }
  if (p.is_reserve) return { text: 'IR', color: C.red }
  if (p.is_starter) return { text: 'START', color: C.cyan }
  return null
}
function TopAssets({ players, topHeavy }: { players: DossierPlayer[]; topHeavy?: number }) {
  const top = players.slice(0, 8)
  const maxVal = Math.max(1, ...top.map(p => p.dynasty_value))
  return (
    <div>
      {topHeavy !== undefined && (
        <p style={{ fontSize: 12, color: C.muted, margin: '0 0 12px', lineHeight: 1.5 }}>
          Top 3 assets hold <span style={{ color: C.amber, fontFamily: mono }}>{Math.round(topHeavy)}%</span> of total value —{' '}
          {topHeavy >= 45 ? 'stars-and-scrubs; thin if the top gets hurt' : topHeavy >= 30 ? 'solid core with reasonable depth' : 'deep and even across the roster'}
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {top.map((p, i) => {
          const badge = slotBadge(p)
          return (
            <div key={p.player_id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.faint, width: 14, textAlign: 'right', flexShrink: 0 }}>{i + 1}</span>
              <PlayerHeadshot playerId={p.player_id} name={p.name} size={32} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontFamily: barlow, fontSize: 15, fontWeight: 600, color: C.text, letterSpacing: '0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                  {badge && <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.12em', padding: '1px 4px', borderRadius: 1, color: badge.color, background: `${badge.color}18`, border: `1px solid ${badge.color}35` }}>{badge.text}</span>}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 1 }}>
                  <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: POS_COLOR[p.position] }}>{p.position}</span>
                  <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>{p.team || 'FA'}</span>
                  <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>{p.age}y</span>
                </div>
              </div>
              <div style={{ width: 90, flexShrink: 0 }}>
                <div style={{ height: 4, background: C.deep, borderRadius: 1, overflow: 'hidden', marginBottom: 3 }}>
                  <div style={{ width: `${(p.dynasty_value / maxVal) * 100}%`, height: '100%', background: C.amber, opacity: 0.8 }} />
                </div>
                <span style={{ fontFamily: mono, fontSize: 11, color: C.amber, display: 'block', textAlign: 'right' }}>{Math.round(p.dynasty_value)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── SKILL / THREAT ───────────────────────────────────────────────────────────
function SkillBreakdown({ skill, allSkills }: { skill: OwnerSkillIndex; allSkills: OwnerSkillIndex[] }) {
  const n = allSkills.length || 1
  const rankOf = (key: (s: OwnerSkillIndex) => number) => [...allSkills].sort((a, b) => key(b) - key(a)).findIndex(s => s.roster_id === skill.roster_id) + 1
  const offSeason = skill.allplay_pct === 0
  const allplayLabel = offSeason ? '—' : `${Math.round(skill.allplay_pct * 100)}%`
  const allplayRecord = !offSeason && skill.allplay_games > 0
    ? `${skill.allplay_wins}W · ${skill.allplay_games - skill.allplay_wins}L`
    : null
  const rows = [
    { label: 'ALL-PLAY', color: C.cyan, pct: skill.allplay_pct, val: allplayLabel, record: allplayRecord, rank: offSeason ? null : rankOf(s => s.allplay_pct), help: 'win rate vs whole league each week' },
    { label: 'LINEUP EFF', color: C.green, pct: skill.lineup_efficiency, val: `${Math.round(skill.lineup_efficiency * 100)}%`, record: null, rank: rankOf(s => s.lineup_efficiency), help: 'started value ÷ optimal lineup' },
    { label: 'ROSTER VAL', color: skill.roster_value_pct >= 1 ? C.green : C.amber, pct: Math.min(skill.roster_value_pct / 2, 1), val: `${skill.roster_value_pct >= 1 ? '+' : ''}${Math.round((skill.roster_value_pct - 1) * 100)}%`, record: null, rank: rankOf(s => s.roster_value_pct), help: 'dynasty value vs league avg' },
  ]
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
        <span style={{ fontFamily: mono, fontSize: 30, fontWeight: 700, color: TIER_COLOR[skill.skill_tier], lineHeight: 1 }}>{Math.round(skill.skill_score)}</span>
        <span style={{ fontFamily: barlow, fontSize: 12, color: C.muted, letterSpacing: '0.05em' }}>/100 · {skill.skill_tier} · #{rankOf(s => s.skill_score)} of {n}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {rows.map(r => (
          <div key={r.label}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.15em', color: '#4a6080', textTransform: 'uppercase', width: 72, flexShrink: 0 }}>{r.label}</span>
              <div style={{ flex: 1, height: 4, background: C.deep, borderRadius: 1, overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(r.pct * 100, 100)}%`, height: '100%', background: r.color, opacity: 0.85 }} />
              </div>
              <span style={{ fontFamily: mono, fontSize: 11, color: r.color, width: 46, textAlign: 'right', flexShrink: 0 }}>{r.val}</span>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.dim, width: 40, textAlign: 'right', flexShrink: 0 }}>{r.rank ? `#${r.rank}` : 'off-szn'}</span>
            </div>
            <div style={{ display: 'flex', gap: 12, marginLeft: 80, marginTop: 2 }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.faint }}>{r.help}</span>
              {r.record && <span style={{ fontFamily: mono, fontSize: 10, color: C.muted }}>{r.record}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── SKILL VS LUCK ────────────────────────────────────────────────────────────
function SkillLuckQuadrant({ skills, profiles, onSelect }: {
  skills: OwnerSkillIndex[]
  profiles: OwnerProfile[]
  onSelect: (rosterId: number) => void
}) {
  const myRosterId = useMyRosterId()
  const profileByRoster = new Map(profiles.map(p => [p.roster_id, p]))
  const plotted = skills.filter(s => Number.isFinite(s.skill_score) && Number.isFinite(s.schedule_luck))
  const widthFloor = 620
  const height = 360
  const margin = { top: 28, right: 28, bottom: 54, left: 58 }
  const innerHeight = height - margin.top - margin.bottom
  const season = plotted.find(s => s.skill_season)?.skill_season

  if (plotted.length === 0) return null

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2,
      boxShadow: `inset 3px 0 0 ${C.cyan}`, overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 8px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: barlow, fontSize: 23, fontWeight: 800, color: C.text, letterSpacing: '0.05em', textTransform: 'uppercase' }}>SKILL VS LUCK</span>
          <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>{season ? `${season} schedule sample` : 'schedule sample'}</span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <TagPill text="RIGHT = LUCKY" />
          <TagPill text="UP = SKILLED" />
        </div>
      </div>

      <ParentSize>
        {({ width }) => {
          const chartWidth = Math.max(widthFloor, width)
          const innerWidth = chartWidth - margin.left - margin.right
          const luckMax = Math.max(2, ...plotted.map(s => Math.abs(s.schedule_luck)))
          const scoreMin = Math.max(0, Math.min(55, ...plotted.map(s => s.skill_score)) - 5)
          const scoreMax = Math.min(100, Math.max(55, ...plotted.map(s => s.skill_score)) + 5)
          const xScale = scaleLinear<number>({
            domain: [-luckMax, luckMax],
            range: [0, innerWidth],
            nice: true,
          })
          const yScale = scaleLinear<number>({
            domain: [scoreMin, scoreMax],
            range: [innerHeight, 0],
            nice: true,
          })
          const xZero = xScale(0)
          const yStrong = yScale(55)

          return (
            <div style={{ overflowX: 'auto' }}>
              <svg width={chartWidth} height={height} role="img" aria-label="Owner skill versus schedule luck quadrant">
                <Group left={margin.left} top={margin.top}>
                  <rect x={0} y={0} width={innerWidth} height={innerHeight} fill={C.deep} opacity={0.72} />
                  <rect x={xZero} y={0} width={innerWidth - xZero} height={yStrong} fill="rgba(26,155,94,0.10)" />
                  <rect x={0} y={0} width={xZero} height={yStrong} fill="rgba(0,184,204,0.09)" />
                  <rect x={xZero} y={yStrong} width={innerWidth - xZero} height={innerHeight - yStrong} fill="rgba(212,134,12,0.08)" />
                  <rect x={0} y={yStrong} width={xZero} height={innerHeight - yStrong} fill="rgba(106,128,152,0.06)" />

                  <Line from={{ x: xZero, y: 0 }} to={{ x: xZero, y: innerHeight }} stroke={C.borderHi} strokeWidth={1} />
                  <Line from={{ x: 0, y: yStrong }} to={{ x: innerWidth, y: yStrong }} stroke={C.borderHi} strokeWidth={1} />

                  <Text x={innerWidth - 10} y={18} textAnchor="end" fontFamily={barlow} fontSize={14} fontWeight={800} fill={C.green} letterSpacing={1}>SKILLED + LUCKY</Text>
                  <Text x={10} y={18} textAnchor="start" fontFamily={barlow} fontSize={14} fontWeight={800} fill={C.cyan} letterSpacing={1}>SKILLED + UNLUCKY</Text>
                  <Text x={innerWidth - 10} y={innerHeight - 10} textAnchor="end" fontFamily={barlow} fontSize={14} fontWeight={800} fill={C.amber} letterSpacing={1}>SELL INTO</Text>
                  <Text x={10} y={innerHeight - 10} textAnchor="start" fontFamily={barlow} fontSize={14} fontWeight={800} fill={C.dim} letterSpacing={1}>WEAK + UNLUCKY</Text>

                  <AxisLeft
                    scale={yScale}
                    numTicks={5}
                    stroke={C.borderHi}
                    tickStroke={C.borderHi}
                    tickLabelProps={() => ({ fill: C.muted, fontFamily: mono, fontSize: 10, textAnchor: 'end', dx: '-0.35em', dy: '0.33em' })}
                  />
                  <AxisBottom
                    top={innerHeight}
                    scale={xScale}
                    numTicks={7}
                    stroke={C.borderHi}
                    tickStroke={C.borderHi}
                    tickFormat={(v) => `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(1)}`}
                    tickLabelProps={() => ({ fill: C.muted, fontFamily: mono, fontSize: 10, textAnchor: 'middle', dy: '0.45em' })}
                  />

                  <Text x={innerWidth / 2} y={innerHeight + 42} textAnchor="middle" fontFamily={barlow} fontSize={11} fill={C.dim} letterSpacing={2}>SCHEDULE LUCK · ACTUAL WINS - ALL-PLAY EXPECTED WINS</Text>
                  <Text x={-44} y={innerHeight / 2} angle={-90} textAnchor="middle" fontFamily={barlow} fontSize={11} fill={C.dim} letterSpacing={2}>TRUE OWNER SKILL INDEX</Text>

                  {plotted.map(skill => {
                    const profile = profileByRoster.get(skill.roster_id)
                    const name = profile?.display_name ?? skill.display_name ?? `Roster ${skill.roster_id}`
                    const isMe = skill.roster_id === myRosterId
                    const color = TIER_COLOR[skill.skill_tier]
                    const x = xScale(skill.schedule_luck)
                    const y = yScale(skill.skill_score)
                    return (
                      <Group key={skill.roster_id}>
                        <Circle
                          cx={x}
                          cy={y}
                          r={isMe ? 8 : 6}
                          fill={color}
                          fillOpacity={isMe ? 1 : 0.82}
                          stroke={isMe ? C.text : C.bg}
                          strokeWidth={isMe ? 2 : 1}
                          style={{ cursor: 'pointer' }}
                          onClick={() => onSelect(skill.roster_id)}
                        />
                        <Text
                          x={x + 10}
                          y={y + 4}
                          fontFamily={barlow}
                          fontSize={11}
                          fontWeight={700}
                          fill={isMe ? C.text : C.muted}
                          letterSpacing={0.6}
                          style={{ cursor: 'pointer' }}
                          onClick={() => onSelect(skill.roster_id)}
                        >
                          {name}
                        </Text>
                      </Group>
                    )
                  })}
                </Group>
              </svg>
            </div>
          )
        }}
      </ParentSize>
    </div>
  )
}

type TradeGraphNode = SimulationNodeDatum & {
  id: string
  rosterId: number
  name: string
  archetype: OwnerProfile['archetype']
  tradeCount: number
}

type TradeGraphLink = SimulationLinkDatum<TradeGraphNode> & {
  source: string | TradeGraphNode
  target: string | TradeGraphNode
  count: number
}

function TradeNetworkGraph({ profiles, histories, onSelect }: {
  profiles: OwnerProfile[]
  histories: OwnerHistory[]
  onSelect: (rosterId: number) => void
}) {
  const myRosterId = useMyRosterId()
  const graph = useMemo(() => {
    const profileByRoster = new Map(profiles.map(p => [p.roster_id, p]))
    const historyByRoster = new Map(histories.map(h => [h.roster_id, h]))
    const nodes: TradeGraphNode[] = profiles.map((profile, index) => {
      const angle = (index / Math.max(1, profiles.length)) * Math.PI * 2
      return {
        id: String(profile.roster_id),
        rosterId: profile.roster_id,
        name: profile.display_name ?? profile.user_id,
        archetype: profile.archetype,
        tradeCount: historyByRoster.get(profile.roster_id)?.trade_count ?? 0,
        x: 360 + Math.cos(angle) * 180,
        y: 190 + Math.sin(angle) * 120,
      }
    })

    const edgeMap = new Map<string, TradeGraphLink>()
    for (const history of histories) {
      for (const partner of history.trade_partners) {
        if (!profileByRoster.has(partner.roster_id)) continue
        const a = Math.min(history.roster_id, partner.roster_id)
        const b = Math.max(history.roster_id, partner.roster_id)
        if (a === b) continue
        const key = `${a}:${b}`
        const existing = edgeMap.get(key)
        if (!existing || partner.count > existing.count) {
          edgeMap.set(key, { source: String(a), target: String(b), count: partner.count })
        }
      }
    }

    const links = [...edgeMap.values()]
    const simulation = forceSimulation<TradeGraphNode>(nodes)
      .force('link', forceLink<TradeGraphNode, TradeGraphLink>(links).id(d => d.id).distance(d => 140 - Math.min(d.count, 8) * 8).strength(0.58))
      .force('charge', forceManyBody<TradeGraphNode>().strength(-420))
      .force('center', forceCenter(360, 190))
      .force('collide', forceCollide<TradeGraphNode>().radius(d => 34 + Math.min(d.tradeCount, 30) * 0.25))
      .stop()

    for (let i = 0; i < 220; i += 1) simulation.tick()
    return { nodes, links }
  }, [profiles, histories])

  if (profiles.length === 0 || histories.length === 0) return null

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2,
      boxShadow: `inset 3px 0 0 ${C.amber}`, overflow: 'hidden',
    }}>
      <div style={{ padding: '14px 18px 8px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: barlow, fontSize: 23, fontWeight: 800, color: C.text, letterSpacing: '0.05em', textTransform: 'uppercase' }}>TRADE NETWORK</span>
          <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>edge width = deal count</span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <TagPill text="REBUILDERS BLUE" />
          <TagPill text="CONTENDERS AMBER" />
          <TagPill text="BALANCED MUTED" />
        </div>
      </div>

      <ParentSize>
        {({ width }) => {
          const chartWidth = Math.max(620, width)
          const height = 420
          const scaleX = chartWidth / 720
          const scaleY = height / 380
          const linkMax = Math.max(1, ...graph.links.map(l => l.count))
          const nodeMax = Math.max(1, ...graph.nodes.map(n => n.tradeCount))

          return (
            <div style={{ overflowX: 'auto' }}>
              <svg width={chartWidth} height={height} role="img" aria-label="Owner trade network graph">
                <rect x={0} y={0} width={chartWidth} height={height} fill={C.deep} opacity={0.72} />
                <Group left={0} top={16}>
                  {graph.links.map((link, index) => {
                    const source = link.source as TradeGraphNode
                    const target = link.target as TradeGraphNode
                    return (
                      <g key={`${source.id}-${target.id}-${index}`}>
                        <Line
                          from={{ x: (source.x ?? 0) * scaleX, y: (source.y ?? 0) * scaleY }}
                          to={{ x: (target.x ?? 0) * scaleX, y: (target.y ?? 0) * scaleY }}
                          stroke={C.borderHi}
                          strokeWidth={1 + (link.count / linkMax) * 7}
                          strokeOpacity={0.38 + (link.count / linkMax) * 0.34}
                        />
                        {link.count >= 3 && (
                          <Text
                            x={(((source.x ?? 0) + (target.x ?? 0)) / 2) * scaleX}
                            y={(((source.y ?? 0) + (target.y ?? 0)) / 2) * scaleY - 4}
                            textAnchor="middle"
                            fontFamily={mono}
                            fontSize={10}
                            fill={C.muted}
                          >
                            {link.count}
                          </Text>
                        )}
                      </g>
                    )
                  })}

                  {graph.nodes.map(node => {
                    const x = (node.x ?? 0) * scaleX
                    const y = (node.y ?? 0) * scaleY
                    const isMe = node.rosterId === myRosterId
                    const color = TRADE_NODE_COLOR[node.archetype]
                    const radius = 9 + (node.tradeCount / nodeMax) * 12
                    return (
                      <Group key={node.id}>
                        <Circle
                          cx={x}
                          cy={y}
                          r={radius}
                          fill={color}
                          fillOpacity={isMe ? 1 : 0.86}
                          stroke={isMe ? C.text : C.bg}
                          strokeWidth={isMe ? 2.5 : 1.25}
                          style={{ cursor: 'pointer' }}
                          onClick={() => onSelect(node.rosterId)}
                        />
                        <Text
                          x={x + radius + 7}
                          y={y + 4}
                          fontFamily={barlow}
                          fontSize={12}
                          fontWeight={800}
                          fill={isMe ? C.text : C.muted}
                          letterSpacing={0.7}
                          style={{ cursor: 'pointer' }}
                          onClick={() => onSelect(node.rosterId)}
                        >
                          {node.name}
                        </Text>
                        <Text
                          x={x}
                          y={y + radius + 15}
                          textAnchor="middle"
                          fontFamily={mono}
                          fontSize={9}
                          fill={C.faint}
                        >
                          {node.tradeCount}
                        </Text>
                      </Group>
                    )
                  })}
                </Group>
              </svg>
            </div>
          )
        }}
      </ParentSize>
    </div>
  )
}

// ── TRADE FEED ───────────────────────────────────────────────────────────────
function TradeFeed({ history }: { history?: OwnerHistory }) {
  const myRosterId = useMyRosterId()
  if (!history) return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Loading history…</span>
  if (history.trades.length === 0) {
    return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>No trades on record across {history.seasons_covered.length} seasons</span>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 360, overflowY: 'auto' }}>
      {history.trades.map((t, i) => {
        const isMe = t.partner_roster_id === myRosterId
        return (
          <div key={i} style={{ background: C.deep, border: `1px solid ${isMe ? 'rgba(0,184,204,0.35)' : C.border}`, borderRadius: 2, padding: '9px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.muted }}>{t.season} · Wk {t.week}</span>
              <span style={{ fontFamily: barlow, fontSize: 11, letterSpacing: '0.05em', color: isMe ? C.cyan : '#3a7cc0' }}>
                {isMe ? 'vs YOU' : `vs ${t.partner_name ?? `roster ${t.partner_roster_id ?? '?'}`}`}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {t.received.length > 0 && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: C.green, flexShrink: 0, width: 28, paddingTop: 1 }}>GOT</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {t.received.map((r, j) => <span key={j} style={{ fontFamily: mono, fontSize: 11, color: C.text }}>{r}</span>)}
                  </div>
                </div>
              )}
              {t.sent.length > 0 && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.1em', color: C.red, flexShrink: 0, width: 28, paddingTop: 1 }}>GAVE</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {t.sent.map((s, j) => <span key={j} style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>{s}</span>)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── HOW TO ATTACK ────────────────────────────────────────────────────────────
function buildAttackAngles(dossier?: OwnerDossier, history?: OwnerHistory, skill?: OwnerSkillIndex): string[] {
  const angles: string[] = []
  const label = dossier?.contention.label

  if (label === 'ASCENDING' || label === 'OPENING') {
    angles.push('Building for later — dangle your aging vets and win-now pieces; they should pay in youth or future picks.')
  } else if (label === 'OPEN') {
    angles.push('Win-now buyer — sell them a proven starter at a premium; they value this year over 2027.')
  } else if (label === 'CLOSING' || label === 'RETOOLING') {
    angles.push('Window closing — their veterans will only get cheaper; buy the ones you like low, or wait them out.')
  }

  if (history?.pick_lean === 'HOARDS') {
    angles.push('Loves draft capital — overpay for their studs in spare picks, or expect them to pay up in picks for your win-now players.')
  } else if (history?.pick_lean === 'SPENDS') {
    angles.push('Dumps picks cheap — buy their future firsts before they realize the class is strong.')
  }

  const thin = dossier?.position_ranks?.filter(r => r.tier === 'THIN') ?? []
  const deep = dossier?.position_ranks?.filter(r => r.tier === 'DEEP') ?? []
  if (thin.length) {
    angles.push(`Thin at ${thin.map(r => r.position).join('/')} (${thin.map(r => `#${r.rank}`).join(', ')} in league) — their hole; dangle your depth there for a premium.`)
  }
  if (deep.length) {
    angles.push(`Loaded at ${deep.map(r => r.position).join('/')} — pry a surplus ${deep[0].position} loose; they can afford to move one.`)
  }

  if (skill && skill.roster_value_pct >= 1.1 && skill.skill_tier === 'WEAK') {
    angles.push('Talented roster, weak process — a regression candidate. Sell into their perceived strength.')
  }

  if (history?.approachability === 'DORMANT') {
    angles.push('Barely active — a fair offer may sit ignored, but a clean one-for-one might slip through unattended.')
  } else if (history?.approachability === 'INSULAR') {
    angles.push('Only deals with one crony — hard to break in; lead with an overpay to open the channel.')
  }

  return angles.slice(0, 4)
}

function HowToAttack({ angles }: { angles: string[] }) {
  if (angles.length === 0) return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Gathering intel…</span>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {angles.map((a, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
          <span style={{ fontFamily: mono, fontSize: 12, color: C.amber, flexShrink: 0 }}>▸</span>
          <span style={{ fontSize: 13, color: '#c4d3e4', lineHeight: 1.55 }}>{a}</span>
        </div>
      ))}
    </div>
  )
}

// ── transaction value (waivers + trades) ─────────────────────────────────────
function TxSubHead({ text, accent }: { text: string; accent?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <span style={{ fontFamily: barlow, fontSize: 13, fontWeight: 800, letterSpacing: '0.14em', color: accent ?? C.muted, textTransform: 'uppercase' }}>{text}</span>
      <div style={{ flex: 1, height: 1, background: C.border }} />
    </div>
  )
}

function TxBigStat({ value, label, color, rank }: { value: string; label: string; color: string; rank?: number }) {
  return (
    <div style={{ flex: 1, minWidth: 92, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontFamily: barlow, fontSize: 27, fontWeight: 800, color, lineHeight: 1 }}>{value}</span>
        {rank != null && <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>#{rank}</span>}
      </div>
      <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.06em', color: C.muted, marginTop: 4, textTransform: 'uppercase' }}>{label}</div>
    </div>
  )
}

function LineupSourceBar({ draft, waiver, trade }: { draft: number; waiver: number; trade: number }) {
  const total = draft + waiver + trade || 1
  const segs = [
    { key: 'draft', label: 'DRAFT', pts: draft, color: C.dim },
    { key: 'trade', label: 'TRADE', pts: trade, color: C.cyan },
    { key: 'waiver', label: 'WAIVER', pts: waiver, color: C.green },
  ].filter((s) => s.pts > 0)
  return (
    <div>
      <div style={{ display: 'flex', height: 20, borderRadius: 2, overflow: 'hidden', border: `1px solid ${C.border}` }}>
        {segs.map((s) => (
          <div key={s.key} title={`${s.label}: ${s.pts.toFixed(0)} pts`} style={{ width: `${(s.pts / total) * 100}%`, background: s.color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: mono, fontSize: 9, color: s.key === 'draft' ? C.text : C.bg, fontWeight: 700 }}>
              {Math.round((s.pts / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 6 }}>
        {segs.map((s) => (
          <span key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: mono, fontSize: 10, color: C.muted }}>
            <span style={{ width: 8, height: 8, background: s.color, borderRadius: 1 }} />
            {s.label} {s.pts.toFixed(0)}
          </span>
        ))}
      </div>
    </div>
  )
}

function TradeCard({ deal, label, accent }: { deal: TransactionValue['trade_deals'][number]; label: string; accent: string }) {
  const assets = (list: TransactionValue['trade_deals'][number]['received'], picks: number) => {
    const names = list.map((a) => `${a.name} (${a.points.toFixed(0)})`)
    if (picks) names.push(`${picks} pick${picks > 1 ? 's' : ''}`)
    return names.length ? names.join(', ') : '—'
  }
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, boxShadow: `inset 3px 0 0 ${accent}`, borderRadius: 3, padding: '9px 11px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{ fontFamily: barlow, fontSize: 10, letterSpacing: '0.18em', color: accent, textTransform: 'uppercase' }}>{label} · vs {deal.partner}</span>
        <span style={{ fontFamily: mono, fontSize: 15, fontWeight: 700, color: deal.net_points >= 0 ? C.green : C.red }}>
          {deal.net_points >= 0 ? '+' : ''}{deal.net_points.toFixed(0)}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontFamily: mono, fontSize: 11 }}>
        <div><span style={{ color: C.green, marginRight: 6 }}>GOT</span><span style={{ color: C.text }}>{assets(deal.received, deal.picks_received)}</span></div>
        <div><span style={{ color: C.red, marginRight: 6 }}>GAVE</span><span style={{ color: C.muted }}>{assets(deal.given, deal.picks_given)}</span></div>
      </div>
    </div>
  )
}

function TransactionValuePanel({ rosterId }: { rosterId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['transactionValue'],
    queryFn: api.transactionValue,
    staleTime: 5 * 60 * 1000,
  })
  const tv: TransactionValue | undefined = data?.find((t) => t.roster_id === rosterId)

  if (isLoading && !data)
    return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Crunching weekly box scores…</span>
  if (!tv)
    return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>No transaction data.</span>

  const all = data ?? []
  const rankOf = (val: number, key: (t: TransactionValue) => number) =>
    all.filter((t) => key(t) > val).length + 1
  const waiverRank = rankOf(tv.waiver_started_points, (t) => t.waiver_started_points)
  const netRank = rankOf(tv.trade_net_points, (t) => t.trade_net_points)
  const netColor = tv.trade_net_points >= 0 ? C.green : C.red
  const maxPickup = Math.max(...tv.top_pickups.map((p) => p.points), 1)
  const best = tv.trade_deals[0]
  const worst = tv.trade_deals.length > 1 ? tv.trade_deals[tv.trade_deals.length - 1] : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontFamily: mono, fontSize: 10, color: C.dim, marginTop: -2 }}>
        {tv.season} season · ranked vs {all.length} managers
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <TxBigStat value={tv.waiver_started_points.toFixed(0)} label="waiver pts started" color={C.green} rank={waiverRank} />
        <TxBigStat value={`${tv.trade_net_points >= 0 ? '+' : ''}${tv.trade_net_points.toFixed(0)}`} label="trade net pts" color={netColor} rank={netRank} />
        <TxBigStat value={`${tv.waiver_adds}`} label="waiver adds" color={C.muted} />
        <TxBigStat value={`${tv.trade_count}`} label="trades made" color={C.muted} />
      </div>

      <div>
        <TxSubHead text="Lineup Production Source" />
        <LineupSourceBar draft={tv.draft_started_points} waiver={tv.waiver_started_points} trade={tv.trade_started_points} />
      </div>

      {tv.top_pickups.length > 0 && (
        <div>
          <TxSubHead text="Top Waiver Pickups" accent={C.green} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {tv.top_pickups.map((p, i) => (
              <div key={p.player_id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: mono, fontSize: 11, color: C.dim, width: 14 }}>{i + 1}</span>
                <PlayerHeadshot playerId={p.player_id} name={p.name} size={26} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: barlow, fontSize: 13, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                  <div style={{ height: 3, background: C.border, borderRadius: 1, marginTop: 2 }}>
                    <div style={{ width: `${(p.points / maxPickup) * 100}%`, height: '100%', background: C.green, borderRadius: 1 }} />
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 700, color: C.green }}>{p.points.toFixed(0)}</span>
                  <span style={{ fontFamily: mono, fontSize: 9, color: C.dim, marginLeft: 5 }}>{p.started_points.toFixed(0)} ST</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tv.trade_deals.length > 0 && (
        <div>
          <TxSubHead text={`Trades · ${tv.trade_deals.length}`} accent={C.cyan} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {best && <TradeCard deal={best} label={worst ? 'Best trade' : 'Trade'} accent={C.green} />}
            {worst && <TradeCard deal={worst} label="Worst trade" accent={C.red} />}
          </div>
          <div style={{ fontFamily: mono, fontSize: 9, color: C.dim, marginTop: 6 }}>
            Net = post-trade points received − points given away, that season.
          </div>
        </div>
      )}
    </div>
  )
}

// ── draft profile (how they draft + best picks) ──────────────────────────────
function PositionMixBar({ mix }: { mix: Record<string, number> }) {
  const order = ['RB', 'WR', 'TE', 'QB']
  const total = order.reduce((s, p) => s + (mix[p] ?? 0), 0) || 1
  const segs = order.filter((p) => (mix[p] ?? 0) > 0)
  return (
    <div>
      <div style={{ display: 'flex', height: 18, borderRadius: 2, overflow: 'hidden', border: `1px solid ${C.border}` }}>
        {segs.map((p) => (
          <div key={p} title={`${p}: ${mix[p]}`} style={{ width: `${((mix[p] ?? 0) / total) * 100}%`, background: POS_COLOR[p], display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: mono, fontSize: 9, color: C.bg, fontWeight: 700 }}>{p}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
        {segs.map((p) => (
          <span key={p} style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: mono, fontSize: 10, color: C.muted }}>
            <span style={{ width: 8, height: 8, background: POS_COLOR[p], borderRadius: 1 }} />
            {p} {mix[p]}
          </span>
        ))}
      </div>
    </div>
  )
}

function DraftPickRow({ pick, index, maxVal }: { pick: DraftProfile['best_picks'][number]; index: number; maxVal: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ fontFamily: mono, fontSize: 11, color: C.dim, width: 14 }}>{index + 1}</span>
      <PlayerHeadshot playerId={pick.player_id} name={pick.name} size={26} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: barlow, fontSize: 13, fontWeight: 600, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{pick.name}</span>
          <span style={{ fontFamily: mono, fontSize: 9, color: POS_COLOR[pick.position] ?? C.dim }}>{pick.position}</span>
          {pick.rostered && <span title="still on their roster" style={{ width: 6, height: 6, borderRadius: '50%', background: C.cyan, flexShrink: 0 }} />}
        </div>
        <div style={{ height: 3, background: C.border, borderRadius: 1, marginTop: 2 }}>
          <div style={{ width: `${(pick.value / maxVal) * 100}%`, height: '100%', background: C.amber, borderRadius: 1 }} />
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 700, color: C.amber }}>{pick.value.toLocaleString()}</span>
        <span style={{ fontFamily: mono, fontSize: 9, color: C.dim, marginLeft: 5 }}>{`'${pick.season.slice(2)} R${pick.round}`}</span>
      </div>
    </div>
  )
}

function DraftProfilePanel({ rosterId }: { rosterId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['draftProfile'],
    queryFn: api.draftProfile,
    staleTime: 5 * 60 * 1000,
  })
  const dp: DraftProfile | undefined = data?.find((d) => d.roster_id === rosterId)

  if (isLoading && !data)
    return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Grading their draft history…</span>
  if (!dp) return <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>No draft data.</span>

  const all = data ?? []
  const hitRank = all.filter((d) => d.hit_rate > dp.hit_rate).length + 1
  const maxVal = Math.max(...dp.best_picks.map((p) => p.value), 1)
  const steal = dp.best_steal

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        <TxBigStat value={`${Math.round(dp.hit_rate * 100)}%`} label="hit rate" color={C.green} rank={hitRank} />
        <TxBigStat value={dp.hits.toString()} label="dynasty hits" color={C.amber} />
        <TxBigStat value={dp.avg_pick_value.toLocaleString()} label="avg pick value" color={C.muted} />
        <TxBigStat value={dp.total_picks.toString()} label={`picks · ${dp.seasons_drafted}yr`} color={C.muted} />
      </div>

      {Object.keys(dp.position_mix).length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontFamily: barlow, fontSize: 13, fontWeight: 800, letterSpacing: '0.14em', color: C.muted, textTransform: 'uppercase' }}>How They Draft</span>
            <span style={{ fontFamily: mono, fontSize: 10, color: C.cyan, border: `1px solid ${C.cyan}55`, borderRadius: 1, padding: '1px 5px' }}>{dp.position_lean}</span>
            <div style={{ flex: 1, height: 1, background: C.border }} />
          </div>
          <PositionMixBar mix={dp.position_mix} />
        </div>
      )}

      {dp.best_picks.length > 0 && (
        <div>
          <TxSubHead text="Best Draft Picks" accent={C.amber} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {dp.best_picks.map((p, i) => (
              <DraftPickRow key={`${p.player_id}-${p.season}`} pick={p} index={i} maxVal={maxVal} />
            ))}
          </div>
          <div style={{ fontFamily: mono, fontSize: 9, color: C.dim, marginTop: 6 }}>
            Value = current dynasty market value (FantasyCalc) · <span style={{ color: C.cyan }}>●</span> still rostered
          </div>
        </div>
      )}

      {steal && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', background: C.panel, border: `1px solid ${C.border}`, boxShadow: `inset 3px 0 0 ${C.green}`, borderRadius: 3 }}>
          <PlayerHeadshot playerId={steal.player_id} name={steal.name} size={30} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: barlow, fontSize: 9, letterSpacing: '0.2em', color: C.green, textTransform: 'uppercase' }}>
              DRAFT STEAL · {steal.season} ROUND {steal.round}
            </div>
            <div style={{ fontFamily: barlow, fontSize: 16, fontWeight: 700, color: C.text }}>{steal.name}</div>
          </div>
          <div style={{ fontFamily: mono, fontSize: 16, fontWeight: 700, color: C.green }}>{steal.value.toLocaleString()}</div>
        </div>
      )}
    </div>
  )
}

function GMDrawer({ profile, skill, allSkills, history, onClose }: {
  profile: OwnerProfile; skill?: OwnerSkillIndex; allSkills: OwnerSkillIndex[]; history?: OwnerHistory; onClose: () => void
}) {
  const displayName = profile.display_name ?? profile.user_id
  const isMe = profile.is_me
  const borderColor = ARCH_BORDER[profile.archetype]

  const { data: dossier, isLoading: dossierLoading, error: dossierError } = useQuery({
    queryKey: ['ownerDossier', profile.roster_id],
    queryFn: () => api.ownerDossier(profile.roster_id),
  })

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const attackAngles = buildAttackAngles(dossier, history, skill)

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(6,10,18,0.78)', zIndex: 100, backdropFilter: 'blur(2px)' }} />
      <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', damping: 30, stiffness: 320 }}
        style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(940px, 95vw)', background: C.bg, boxShadow: `inset 3px 0 0 ${borderColor}`, zIndex: 101, overflowY: 'auto' }}>

        {/* sticky header */}
        <div style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(7,12,22,0.96)', backdropFilter: 'blur(8px)', borderBottom: `1px solid ${C.border}`, padding: '16px 22px', display: 'flex', alignItems: 'center', gap: 16 }}>
          <Avatar avatar={profile.avatar} name={displayName} size={56} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
              <span style={{ fontFamily: barlow, fontSize: 30, fontWeight: 800, color: C.text, letterSpacing: '0.02em', lineHeight: 1 }}>{displayName.toUpperCase()}</span>
              <ArchetypeBadge archetype={profile.archetype} size="md" />
              {isMe && <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.25em', padding: '2px 6px', color: C.cyan, background: 'rgba(0,184,204,0.1)', border: '1px solid rgba(0,184,204,0.3)', borderRadius: 1, textTransform: 'uppercase' }}>YOUR TEAM</span>}
            </div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              {dossier ? (
                <>
                  <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>{dossier.player_count} players</span>
                  <span style={{ fontFamily: mono, fontSize: 11, color: C.amber }}>#{dossier.value_rank}/{dossier.league_size} value</span>
                  <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>{Math.round(dossier.total_dynasty_value)} pts</span>
                  <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>avg age {dossier.avg_age.toFixed(1)}</span>
                </>
              ) : (
                <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Dynasty scouting report</span>
              )}
            </div>
          </div>
          {skill && (
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontFamily: mono, fontSize: 26, fontWeight: 700, color: TIER_COLOR[skill.skill_tier], lineHeight: 1 }}>{Math.round(skill.skill_score)}</div>
              <Label>SKILL · {skill.skill_tier}</Label>
            </div>
          )}
          <button onClick={onClose} style={{ background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 2, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: C.muted, flexShrink: 0 }}>
            <X size={15} />
          </button>
        </div>

        {/* body */}
        <div style={{ padding: 18, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'start' }}>
          <ScoutVerdict skill={skill} history={history} dossier={dossier} />

          {!isMe && history && (
            <Section title="HEAD TO HEAD" kicker="you vs them" span={2} accent={C.cyan}>
              <VsYou history={history} />
            </Section>
          )}

          <Section title="HOW THEY TRADE" kicker="7-season transaction history" span={2}>
            {history ? <TradeBehavior history={history} /> : <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>Loading transaction history…</span>}
          </Section>

          <Section title="TRANSACTION VALUE" kicker="fantasy points added via waivers & trades" span={2} accent={C.green}>
            <TransactionValuePanel rosterId={profile.roster_id} />
          </Section>

          <Section title="DRAFT PROFILE" kicker="how they draft · best picks all-time" span={2} accent={C.amber}>
            <DraftProfilePanel rosterId={profile.roster_id} />
          </Section>

          {dossierError && (
            <Section title="ROSTER" span={2}>
              <span style={{ fontFamily: mono, fontSize: 12, color: C.red }}>{dossierError instanceof Error ? dossierError.message : 'Failed to load'}</span>
            </Section>
          )}
          {dossierLoading && !dossier && (
            <Section title="ROSTER" span={2}>
              <span style={{ fontFamily: barlow, fontSize: 13, letterSpacing: '0.3em', color: C.dim, textTransform: 'uppercase' }}>ANALYZING ROSTER…</span>
            </Section>
          )}

          {dossier && (
            <>
              <Section title="CONTENTION WINDOW" kicker="value-weighted age model" span={1}>
                <ContentionGauge c={dossier.contention} />
              </Section>
              <Section title="POSITIONAL NEEDS" kicker="strengths & holes vs league" span={1}>
                {dossier.position_ranks?.length ? <PositionalNeeds ranks={dossier.position_ranks} /> : <span style={{ fontFamily: mono, fontSize: 11, color: C.dim }}>—</span>}
              </Section>

              <Section title="ROSTER AGE" kicker="dynasty value by age band" span={1}>
                <AgePyramid buckets={dossier.age_buckets} avgAge={dossier.avg_age} avgStarterAge={dossier.avg_starter_age} />
              </Section>
              {skill && (
                <Section title="THREAT ASSESSMENT" kicker="skill vs luck decomposition" span={1}>
                  <SkillBreakdown skill={skill} allSkills={allSkills} />
                </Section>
              )}

              <Section title="TOP ASSETS" kicker="by dynasty value" span={2}>
                <TopAssets players={dossier.players} topHeavy={dossier.top_heavy_pct} />
              </Section>

              <Section title="PICK INVENTORY" kicker="current future capital" span={2} accent={C.amber}>
                <PickInventory picksOwned={dossier.picks_owned} picksTraded={dossier.picks_traded_away} />
              </Section>
            </>
          )}

          <Section title="HOW TO ATTACK" kicker="the angle" span={2} accent={C.amber}>
            <HowToAttack angles={attackAngles} />
          </Section>

          <Section title="RECENT DEALS" kicker={history ? `${history.trade_count} on record` : undefined} span={2}>
            <TradeFeed history={history} />
          </Section>
        </div>
      </motion.div>
    </>
  )
}

// ── page ─────────────────────────────────────────────────────────────────────
export function Owners() {
  const [selectedRosterId, setSelectedRosterId] = useState<number | null>(null)

  const { data: profiles, isLoading, error } = useQuery({ queryKey: ['ownerProfiles'], queryFn: api.ownerProfiles })
  const { data: skillData } = useQuery({ queryKey: ['ownerSkill'], queryFn: api.ownerSkill })
  const { data: historyData } = useQuery({ queryKey: ['leagueHistory'], queryFn: api.leagueHistory })
  const { data: faabData } = useQuery({ queryKey: ['league-faab'], queryFn: api.faab, staleTime: 5 * 60 * 1000 })

  const skillByRosterId = new Map(skillData?.map(s => [s.roster_id, s]) ?? [])
  const historyByRosterId = new Map(historyData?.owners.map(o => [o.roster_id, o]) ?? [])
  const faabByRosterId = new Map(faabData?.map(f => [f.roster_id, f]) ?? [])
  const selectedProfile = profiles?.find(p => p.roster_id === selectedRosterId) ?? null

  if (isLoading) {
    return (
      <div style={{ padding: '40px 20px', textAlign: 'center' }}>
        <span style={{ fontFamily: barlow, fontSize: 14, letterSpacing: '0.3em', color: C.dim, textTransform: 'uppercase' }}>LOADING GM PROFILES…</span>
      </div>
    )
  }
  if (error) {
    return (
      <div style={{ padding: 20 }}>
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, boxShadow: `inset 3px 0 0 ${C.red}`, borderRadius: 2, padding: '14px 16px 14px 18px', color: C.red, fontFamily: mono, fontSize: 12 }}>
          {error instanceof Error ? error.message : 'Failed to load owner profiles'}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: barlow, fontSize: 40, fontWeight: 800, color: C.text }}>GM PROFILES</h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: C.muted }}>SCOUT YOUR COMPETITION</span>
        </div>
      </div>

      <div className="p-5 flex flex-col gap-4">
        {skillData && profiles && (
          <SkillLuckQuadrant
            skills={skillData}
            profiles={profiles}
            onSelect={setSelectedRosterId}
          />
        )}
        {historyData && profiles && (
          <TradeNetworkGraph
            profiles={profiles}
            histories={historyData.owners}
            onSelect={setSelectedRosterId}
          />
        )}
      </div>

      <div className="px-5 pb-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {(profiles ?? []).map((profile, i) => (
          <OwnerCard
            key={profile.user_id}
            profile={profile}
            index={i}
            skill={skillByRosterId.get(profile.roster_id)}
            history={historyByRosterId.get(profile.roster_id)}
            faab={faabByRosterId.get(profile.roster_id)}
            onClick={() => setSelectedRosterId(profile.roster_id)}
          />
        ))}
      </div>

      <AnimatePresence>
        {selectedProfile && (
          <GMDrawer profile={selectedProfile} skill={skillByRosterId.get(selectedProfile.roster_id)} allSkills={skillData ?? []} history={historyByRosterId.get(selectedProfile.roster_id)} onClose={() => setSelectedRosterId(null)} />
        )}
      </AnimatePresence>
    </div>
  )
}
