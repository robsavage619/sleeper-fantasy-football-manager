/**
 * Shared visualization primitives — inline SVG marks that match the war-room
 * design system (dark surfaces, position hues, Barlow Condensed / DM Mono).
 * Built to the data-viz mark specs: thin marks, rounded data-ends, recessive
 * grid, direct labels, status/position color by role (never by rank).
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// --- design tokens (single source, mirrors index.css) ---------------------
export const INK = { primary: '#e8eef6', secondary: '#8aa0b8', muted: '#6a8098', dim: '#3d5070' }
export const SURFACE = { card: '#09111f', card2: '#0c1625', border: '#162035', border2: '#24344f' }
export const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}
export const STATUS = { good: '#1a9b5e', ok: '#3a8cd4', warn: '#d4860c', bad: '#c93328', info: '#00b8cc' }

/**
 * Inline "ⓘ" affordance that reveals a plain-English metric definition on hover
 * or tap. Popover anchors below-left of the icon; click toggles for touch.
 */
export function InfoTip({ text, label, align = 'left' }: { text: string; label?: string; align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false)
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle' }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label ? `What is ${label}?` : 'Explain this metric'}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        style={{
          width: 13,
          height: 13,
          borderRadius: '50%',
          border: `1px solid ${SURFACE.border2}`,
          background: 'transparent',
          color: INK.muted,
          fontFamily: "'DM Mono', monospace",
          fontSize: 9,
          lineHeight: 1,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 0,
          flexShrink: 0,
        }}
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            [align]: 0,
            width: 244,
            zIndex: 60,
            background: SURFACE.card2,
            border: `1px solid ${SURFACE.border2}`,
            borderRadius: 4,
            padding: '9px 11px',
            color: INK.secondary,
            fontSize: 11.5,
            lineHeight: 1.5,
            fontWeight: 400,
            letterSpacing: 'normal',
            textTransform: 'none',
            boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            pointerEvents: 'none',
          }}
        >
          {text}
        </span>
      )}
    </span>
  )
}

/**
 * Collapsible "What The Numbers Mean" glossary panel — the term/definition
 * list a page's InfoTips draw from, laid out for scanning rather than hover.
 * Same interaction pattern across every page that uses it.
 */
export function GlossaryPanel({
  title = 'What The Numbers Mean',
  entries,
  benchmarks,
}: {
  title?: string
  entries: [string, string][]
  benchmarks?: Record<string, string>
}) {
  const [open, setOpen] = useState(false)
  const barlow = "'Barlow Condensed', sans-serif"
  const mono = "'DM Mono', monospace"
  if (entries.length === 0) return null
  return (
    <section style={{ borderBottom: `1px solid ${SURFACE.border}`, padding: '0 20px' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 uppercase"
        style={{ width: '100%', textAlign: 'left', background: 'transparent', border: 'none', cursor: 'pointer', padding: '11px 0', color: INK.muted, fontFamily: barlow, fontWeight: 700, fontSize: 12, letterSpacing: '0.16em' }}
      >
        <span style={{ display: 'inline-flex', width: 14, height: 14, borderRadius: '50%', border: `1px solid ${INK.dim}`, alignItems: 'center', justifyContent: 'center', fontFamily: mono, fontSize: 9, color: INK.muted }}>
          i
        </span>
        {title}
        <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 11, color: INK.dim, transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }}>›</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} style={{ overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '10px 24px', paddingBottom: 18, paddingTop: 4 }}>
              {entries.map(([term, def]) => (
                <div key={term} style={{ borderLeft: `2px solid ${SURFACE.border}`, paddingLeft: 12 }}>
                  <div className="uppercase" style={{ fontFamily: barlow, fontWeight: 700, fontSize: 13, color: INK.primary, letterSpacing: '0.03em', marginBottom: 2 }}>
                    {term}
                  </div>
                  <div style={{ color: INK.muted, fontSize: 12, lineHeight: 1.5 }}>{def}</div>
                  {benchmarks?.[term] && (
                    <div className="uppercase tracking-wide" style={{ color: STATUS.info, fontSize: 9.5, marginTop: 4 }}>
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

/** Tier color for a 0..1 "higher-is-better" score (diverging poor→elite). */
export function tierColor(pct01: number): string {
  if (pct01 >= 0.7) return STATUS.good
  if (pct01 >= 0.45) return STATUS.ok
  if (pct01 >= 0.25) return STATUS.warn
  return STATUS.bad
}

// --- player headshot with position-colored ring + initials fallback -------
export function PlayerHeadshot({
  playerId,
  name,
  position,
  size = 34,
}: {
  playerId: string
  name: string
  position?: string
  size?: number
}) {
  const [err, setErr] = useState(false)
  const ring = position ? POS_COLOR[position] ?? SURFACE.border2 : SURFACE.border2
  const initials = name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
  if (err) {
    return (
      <span
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: SURFACE.card2,
          border: `1.5px solid ${ring}`,
          color: INK.muted,
          fontSize: size * 0.34,
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 700,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        {initials}
      </span>
    )
  }
  return (
    <img
      src={`https://sleepercdn.com/content/nfl/players/thumb/${playerId}.jpg`}
      alt={name}
      onError={() => setErr(true)}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        objectFit: 'cover',
        background: SURFACE.card2,
        border: `1.5px solid ${ring}`,
        flexShrink: 0,
      }}
    />
  )
}

/** Sleeper owner avatar with initials fallback. */
export function OwnerAvatar({
  avatar,
  name,
  size = 34,
}: {
  avatar: string | null
  name: string
  size?: number
}) {
  const [err, setErr] = useState(false)
  if (!avatar || err) {
    return (
      <span
        style={{
          width: size,
          height: size,
          borderRadius: 3,
          background: SURFACE.card2,
          border: `1px solid ${SURFACE.border2}`,
          color: INK.muted,
          fontSize: size * 0.4,
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 700,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        {(name[0] ?? '?').toUpperCase()}
      </span>
    )
  }
  return (
    <img
      src={`https://sleepercdn.com/avatars/thumbs/${avatar}`}
      alt={name}
      onError={() => setErr(true)}
      style={{ width: size, height: size, borderRadius: 3, objectFit: 'cover', flexShrink: 0 }}
    />
  )
}

/** Percentile/score bar — fills to `pct01`, colored by tier, with a value label. */
export function PercentileBar({
  label,
  pct01,
  value,
  color,
  info,
}: {
  label: string
  pct01: number
  value: string
  color?: string
  info?: string
}) {
  const clamped = Math.max(0, Math.min(1, pct01))
  const fill = color ?? tierColor(clamped)
  return (
    <div>
      <div className="flex items-baseline justify-between" style={{ marginBottom: 3 }}>
        <span
          className="tracking-[0.12em] uppercase"
          style={{ color: INK.muted, fontSize: 9.5 }}
        >
          {label}
          {info && <InfoTip text={info} label={label} />}
        </span>
        <span
          style={{
            color: INK.primary,
            fontFamily: "'DM Mono', monospace",
            fontSize: 11,
            fontWeight: 500,
          }}
        >
          {value}
        </span>
      </div>
      <div style={{ height: 6, background: SURFACE.border, borderRadius: 3, overflow: 'hidden' }}>
        <div
          style={{
            width: `${clamped * 100}%`,
            height: '100%',
            background: fill,
            borderRadius: 3,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
    </div>
  )
}

/** Floor → median → ceiling range bar (weekly outcome spread). */
export function RangeBar({
  floor,
  median,
  ceiling,
  max,
  color = STATUS.info,
}: {
  floor: number
  median: number
  ceiling: number
  max: number
  color?: string
}) {
  const scale = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`
  return (
    <div style={{ padding: '4px 0' }}>
      <div style={{ position: 'relative', height: 10 }}>
        <div
          style={{
            position: 'absolute',
            top: 3,
            left: scale(floor),
            width: `calc(${scale(ceiling)} - ${scale(floor)})`,
            height: 4,
            background: `${color}55`,
            borderRadius: 2,
          }}
        />
        <div
          title={`median ${median.toFixed(1)}`}
          style={{
            position: 'absolute',
            top: 0,
            left: scale(median),
            width: 3,
            height: 10,
            background: color,
            borderRadius: 1,
            transform: 'translateX(-1.5px)',
          }}
        />
      </div>
      <div className="flex justify-between" style={{ marginTop: 3 }}>
        <span style={{ color: INK.dim, fontSize: 9 }}>{floor.toFixed(0)}</span>
        <span style={{ color: INK.secondary, fontSize: 9 }}>med {median.toFixed(1)}</span>
        <span style={{ color: INK.dim, fontSize: 9 }}>{ceiling.toFixed(0)}</span>
      </div>
    </div>
  )
}

/** Sparkline-style bars (e.g. weekly fantasy points), colored good→bad by value. */
export function MiniBars({
  values,
  labels,
  boomLine,
  bustLine,
  height = 40,
}: {
  values: number[]
  labels?: string[]
  boomLine?: number
  bustLine?: number
  height?: number
}) {
  const max = Math.max(1, ...values)
  return (
    <div className="flex items-end gap-1" style={{ height }}>
      {values.map((v, i) => {
        const h = Math.max(2, (v / max) * height)
        const color =
          boomLine != null && v >= boomLine
            ? STATUS.good
            : bustLine != null && v < bustLine
              ? STATUS.bad
              : INK.muted
        return (
          <div
            key={i}
            title={labels?.[i] ? `${labels[i]}: ${v.toFixed(1)}` : v.toFixed(1)}
            style={{
              flex: 1,
              height: h,
              background: color,
              borderRadius: '2px 2px 0 0',
              minWidth: 3,
            }}
          />
        )
      })}
    </div>
  )
}

/** Small donut gauge for a 0..1 rate (boom%, hit rate, etc.). */
export function Donut({
  pct01,
  color,
  size = 52,
  label,
}: {
  pct01: number
  color: string
  size?: number
  label: string
}) {
  const r = size / 2 - 5
  const circ = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(1, pct01))
  return (
    <div className="flex flex-col items-center" style={{ gap: 4 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={SURFACE.border} strokeWidth={5} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={`${clamped * circ} ${circ}`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          transform={`rotate(90 ${size / 2} ${size / 2})`}
          style={{ fill: INK.primary, fontSize: 13, fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800 }}
        >
          {Math.round(clamped * 100)}
        </text>
      </svg>
      <span className="tracking-[0.14em] uppercase" style={{ color: INK.muted, fontSize: 8.5 }}>
        {label}
      </span>
    </div>
  )
}

// --- owner-comparison primitives ------------------------------------------
// Color follows the *entity* (avatar carries identity) or a *role* (sign / tier),
// never rank. Compare-mode assigns these three well-separated hues in fixed order.
export const OWNER_HUES = ['#00b8cc', '#d4860c', '#9085e9'] // cyan · amber · violet

const BARLOW = "'Barlow Condensed', sans-serif"
const MONO = "'DM Mono', monospace"

/** Clipped owner-avatar disc used as a scatter mark (falls back to a ring dot). */
function AvatarDisc({
  avatar,
  cx,
  cy,
  r,
  ring,
  id,
}: {
  avatar: string | null
  cx: number
  cy: number
  r: number
  ring: string
  id: string
}) {
  if (!avatar) {
    return <circle cx={cx} cy={cy} r={r * 0.7} fill={ring} stroke={SURFACE.card} strokeWidth={1.5} />
  }
  const clip = `disc-${id}`
  return (
    <>
      <clipPath id={clip}>
        <circle cx={cx} cy={cy} r={r} />
      </clipPath>
      <circle cx={cx} cy={cy} r={r + 1.5} fill={SURFACE.card} />
      <image
        href={`https://sleepercdn.com/avatars/thumbs/${avatar}`}
        x={cx - r}
        y={cy - r}
        width={r * 2}
        height={r * 2}
        clipPath={`url(#${clip})`}
        preserveAspectRatio="xMidYMid slice"
      />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={ring} strokeWidth={2} />
    </>
  )
}

export type ScatterPoint = {
  id: string
  x: number
  y: number
  name: string
  avatar: string | null
  ring?: string
  me?: boolean
  tip?: string
}

/**
 * Quadrant scatter — two measures, avatar marks, median reference lines that
 * split the plane into four labeled quadrants. Identity via the avatar, so no
 * per-owner color is needed; the ring encodes an optional role/status.
 */
export function Scatter({
  points,
  xLabel,
  yLabel,
  xRef,
  yRef,
  quadrants,
  height = 300,
}: {
  points: ScatterPoint[]
  xLabel: string
  yLabel: string
  xRef: number
  yRef: number
  quadrants?: [string, string, string, string] // TL, TR, BR, BL
  height?: number
}) {
  const W = 620
  const H = height
  const pad = { l: 46, r: 18, t: 16, b: 34 }
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const xmin = Math.min(...xs, xRef)
  const xmax = Math.max(...xs, xRef)
  const ymin = Math.min(...ys, yRef)
  const ymax = Math.max(...ys, yRef)
  const xpad = (xmax - xmin || 1) * 0.12
  const ypad = (ymax - ymin || 1) * 0.12
  const sx = (v: number) =>
    pad.l + ((v - (xmin - xpad)) / (xmax - xmin + 2 * xpad || 1)) * (W - pad.l - pad.r)
  const sy = (v: number) =>
    H - pad.b - ((v - (ymin - ypad)) / (ymax - ymin + 2 * ypad || 1)) * (H - pad.t - pad.b)
  const rx = sx(xRef)
  const ry = sy(yRef)
  const qLabel = (t: string, x: number, y: number, anchor: 'start' | 'end') => (
    <text
      x={x}
      y={y}
      textAnchor={anchor}
      style={{ fill: INK.dim, fontSize: 8.5, fontFamily: BARLOW, letterSpacing: '0.18em' }}
      className="uppercase"
    >
      {t}
    </text>
  )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} role="img" aria-label={`${yLabel} versus ${xLabel}`}>
      {/* quadrant reference lines (median split) */}
      <line x1={rx} y1={pad.t} x2={rx} y2={H - pad.b} stroke={SURFACE.border2} strokeWidth={1} strokeDasharray="3 4" />
      <line x1={pad.l} y1={ry} x2={W - pad.r} y2={ry} stroke={SURFACE.border2} strokeWidth={1} strokeDasharray="3 4" />
      {quadrants && (
        <>
          {qLabel(quadrants[0], pad.l + 4, pad.t + 10, 'start')}
          {qLabel(quadrants[1], W - pad.r - 4, pad.t + 10, 'end')}
          {qLabel(quadrants[2], W - pad.r - 4, H - pad.b - 6, 'end')}
          {qLabel(quadrants[3], pad.l + 4, H - pad.b - 6, 'start')}
        </>
      )}
      {/* axis titles */}
      <text x={pad.l + (W - pad.l - pad.r) / 2} y={H - 4} textAnchor="middle" style={{ fill: INK.muted, fontSize: 9.5, fontFamily: BARLOW, letterSpacing: '0.16em' }} className="uppercase">
        {xLabel} →
      </text>
      <text transform={`rotate(-90 12 ${pad.t + (H - pad.t - pad.b) / 2})`} x={12} y={pad.t + (H - pad.t - pad.b) / 2} textAnchor="middle" style={{ fill: INK.muted, fontSize: 9.5, fontFamily: BARLOW, letterSpacing: '0.16em' }} className="uppercase">
        {yLabel} →
      </text>
      {points.map((p) => (
        <g key={p.id}>
          <title>{p.tip ?? `${p.name}: ${xLabel} ${p.x.toFixed(2)}, ${yLabel} ${p.y.toFixed(2)}`}</title>
          <AvatarDisc avatar={p.avatar} cx={sx(p.x)} cy={sy(p.y)} r={p.me ? 15 : 12} ring={p.me ? STATUS.info : p.ring ?? SURFACE.border2} id={p.id} />
        </g>
      ))}
    </svg>
  )
}

export type RankedItem = {
  id: string
  label: string
  avatar: string | null
  value: number
  me?: boolean
  sub?: string
}

/**
 * Horizontal ranked bars. `diverging` anchors bars at a center zero line and
 * colors by sign (good/critical); otherwise bars are left-anchored and colored
 * by `colorFor` (default status.info). Avatar + label carry identity.
 */
export function RankedBar({
  items,
  format = (v) => v.toFixed(0),
  diverging = false,
  colorFor,
  maxRows,
}: {
  items: RankedItem[]
  format?: (v: number) => string
  diverging?: boolean
  colorFor?: (v: number) => string
  maxRows?: number
}) {
  const rows = maxRows ? items.slice(0, maxRows) : items
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.value)))
  const color = (v: number) => (colorFor ? colorFor(v) : diverging ? (v >= 0 ? STATUS.good : STATUS.bad) : STATUS.info)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {rows.map((r) => {
        const w = (Math.abs(r.value) / maxAbs) * 100
        const c = color(r.value)
        return (
          <div key={r.id} title={`${r.label}: ${format(r.value)}${r.sub ? ` · ${r.sub}` : ''}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 20, textAlign: 'right', flexShrink: 0 }}>
              <OwnerAvatar avatar={r.avatar} name={r.label} size={18} />
            </div>
            <span style={{ width: 92, flexShrink: 0, fontFamily: BARLOW, fontWeight: 700, fontSize: 12.5, color: r.me ? STATUS.info : INK.primary, letterSpacing: '0.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="uppercase">
              {r.label}
            </span>
            {diverging ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', height: 12 }}>
                <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
                  {r.value < 0 && <div style={{ width: `${w}%`, height: 8, background: c, borderRadius: '3px 0 0 3px' }} />}
                </div>
                <div style={{ width: 1, height: 12, background: SURFACE.border2, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  {r.value >= 0 && <div style={{ width: `${w}%`, height: 8, background: c, borderRadius: '0 3px 3px 0' }} />}
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, height: 8, background: SURFACE.border, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${w}%`, height: '100%', background: c, borderRadius: 3, transition: 'width 0.5s ease' }} />
              </div>
            )}
            <span style={{ width: 58, flexShrink: 0, textAlign: 'right', fontFamily: MONO, fontSize: 11, color: r.me ? STATUS.info : INK.secondary }}>
              {format(r.value)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export type RadarSeries = { id: string; name: string; color: string; values: number[] }

/** Radar / spider chart comparing 2–3 owners across N normalized (0..1) axes. */
export function Radar({ axes, series, size = 300 }: { axes: string[]; series: RadarSeries[]; size?: number }) {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 46
  const n = axes.length
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const pt = (i: number, v: number) => [cx + Math.cos(angle(i)) * r * v, cy + Math.sin(angle(i)) * r * v]
  const rings = [0.25, 0.5, 0.75, 1]
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" role="img" aria-label="Owner dimension comparison radar">
      {rings.map((rr) => (
        <polygon
          key={rr}
          points={axes.map((_, i) => pt(i, rr).join(',')).join(' ')}
          fill="none"
          stroke={SURFACE.border}
          strokeWidth={1}
        />
      ))}
      {axes.map((a, i) => {
        const [ex, ey] = pt(i, 1)
        const [lx, ly] = pt(i, 1.18)
        return (
          <g key={a}>
            <line x1={cx} y1={cy} x2={ex} y2={ey} stroke={SURFACE.border} strokeWidth={1} />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central" style={{ fill: INK.muted, fontSize: 8.5, fontFamily: BARLOW, letterSpacing: '0.12em' }} className="uppercase">
              {a}
            </text>
          </g>
        )
      })}
      {series.map((s) => (
        <g key={s.id}>
          <polygon
            points={s.values.map((v, i) => pt(i, Math.max(0.02, Math.min(1, v))).join(',')).join(' ')}
            fill={`${s.color}22`}
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {s.values.map((v, i) => {
            const [px, py] = pt(i, Math.max(0.02, Math.min(1, v)))
            return <circle key={i} cx={px} cy={py} r={2.5} fill={s.color} />
          })}
        </g>
      ))}
    </svg>
  )
}

export type BumpSeries = { id: string; name: string; ranks: (number | null)[]; me?: boolean; highlight?: boolean }

/** Rank/bump chart — finish position (1 = top) across seasons, one line per owner. */
export function BumpChart({
  seasons,
  series,
  ofTeams,
  height = 260,
}: {
  seasons: string[]
  series: BumpSeries[]
  ofTeams: number
  height?: number
}) {
  const W = 620
  const H = height
  const pad = { l: 30, r: 96, t: 16, b: 24 }
  const n = seasons.length
  const sx = (i: number) => pad.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - pad.l - pad.r))
  const sy = (rank: number) => pad.t + ((rank - 1) / Math.max(1, ofTeams - 1)) * (H - pad.t - pad.b)
  const anyHi = series.some((s) => s.highlight || s.me)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Season finish by owner">
      {[1, Math.ceil(ofTeams / 2), ofTeams].map((rk) => (
        <g key={rk}>
          <line x1={pad.l} y1={sy(rk)} x2={W - pad.r} y2={sy(rk)} stroke={SURFACE.border} strokeWidth={1} strokeDasharray="2 5" />
          <text x={pad.l - 6} y={sy(rk)} textAnchor="end" dominantBaseline="central" style={{ fill: INK.dim, fontSize: 9, fontFamily: MONO }}>
            {rk}
          </text>
        </g>
      ))}
      {seasons.map((s, i) => (
        <text key={s} x={sx(i)} y={H - 6} textAnchor="middle" style={{ fill: INK.muted, fontSize: 9, fontFamily: MONO }}>
          {`'${s.slice(2)}`}
        </text>
      ))}
      {series.map((s) => {
        const hi = s.highlight || s.me
        const col = s.me ? STATUS.info : hi ? STATUS.warn : INK.dim
        const op = anyHi && !hi ? 0.28 : 1
        const pts = s.ranks
          .map((rk, i) => (rk == null ? null : [sx(i), sy(rk)]))
          .filter(Boolean) as number[][]
        if (!pts.length) return null
        const last = pts[pts.length - 1]
        const lastRank = [...s.ranks].reverse().find((x) => x != null)
        return (
          <g key={s.id} opacity={op}>
            <title>{s.name}</title>
            <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={col} strokeWidth={hi ? 2.5 : 1.5} strokeLinejoin="round" strokeLinecap="round" />
            {pts.map((p, i) => (
              <circle key={i} cx={p[0]} cy={p[1]} r={hi ? 3 : 2.2} fill={col} stroke={SURFACE.card} strokeWidth={1} />
            ))}
            {hi && (
              <text x={last[0] + 8} y={last[1]} dominantBaseline="central" style={{ fill: col, fontSize: 10, fontFamily: BARLOW, fontWeight: 700, letterSpacing: '0.04em' }} className="uppercase">
                {s.name}
                {lastRank != null ? ` #${lastRank}` : ''}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

// --- shared page chrome (was redefined per-route; consolidated here) ------

const BARLOW_FONT = "'Barlow Condensed', sans-serif"

/** Section header used at the top of every dense page section. */
export function SectionTitle({ children, sub }: { children: import('react').ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline gap-3 px-5 pt-6 pb-2">
      <h2
        className="uppercase tracking-wide leading-none"
        style={{ fontFamily: BARLOW_FONT, fontSize: 22, fontWeight: 800, color: INK.primary }}
      >
        {children}
      </h2>
      {sub && (
        <span className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: INK.dim }}>
          {sub}
        </span>
      )}
    </div>
  )
}

/** Small colored position badge (QB/RB/WR/TE). */
export function PosTag({ position }: { position: string }) {
  const c = POS_COLOR[position] ?? INK.muted
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.12em',
        padding: '1px 5px',
        color: c,
        background: `${c}18`,
        borderRadius: 1,
      }}
    >
      {position}
    </span>
  )
}

/** Colored two-column-grid section sub-header (e.g. BUY / SELL column headers). */
export function ColHead({ children, color }: { children: import('react').ReactNode; color: string }) {
  return (
    <div
      className="px-3 py-2 tracking-[0.15em] uppercase"
      style={{ fontSize: 10, fontWeight: 700, color, borderBottom: `1px solid ${color}30` }}
    >
      {children}
    </div>
  )
}

/** Centered loading label for a table/section still fetching. */
export function Loading({ label }: { label: string }) {
  return (
    <div className="py-6 text-center tracking-widest uppercase" style={{ color: INK.dim, fontSize: 12 }}>
      {label}
    </div>
  )
}

/** Left-aligned empty-state note inside a section. */
export function Empty({ children }: { children: import('react').ReactNode }) {
  return <div style={{ color: INK.dim, fontSize: 12, padding: '10px 20px' }}>{children}</div>
}

/** Minimal inline-SVG line sparkline for a price/value series over time. */
export function Sparkline({
  values,
  width = 84,
  height = 26,
  color = STATUS.info,
}: {
  values: number[]
  width?: number
  height?: number
  color?: string
}) {
  if (values.length < 2) {
    return (
      <span style={{ color: INK.dim, fontSize: 10, fontFamily: "'DM Mono', monospace" }}>—</span>
    )
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const step = width / (values.length - 1)
  const pts = values.map((v, i) => [i * step, height - ((v - min) / range) * height])
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]
  const rising = values[values.length - 1] >= values[0]
  const stroke = color === STATUS.info ? (rising ? STATUS.good : STATUS.bad) : color
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="value trend">
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={2} fill={stroke} />
    </svg>
  )
}

/** Horizontal stacked value bar for roster/position composition. */
export function StackBar({
  segments,
  height = 10,
}: {
  segments: { label: string; value: number; color: string }[]
  height?: number
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1
  return (
    <div className="flex" style={{ height, gap: 2, borderRadius: 3, overflow: 'hidden' }}>
      {segments.map((s) => (
        <div
          key={s.label}
          title={`${s.label}: ${Math.round((s.value / total) * 100)}%`}
          style={{ width: `${(s.value / total) * 100}%`, background: s.color, minWidth: s.value > 0 ? 3 : 0 }}
        />
      ))}
    </div>
  )
}
