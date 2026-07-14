/**
 * Shared visualization primitives — inline SVG marks that match the war-room
 * design system (dark surfaces, position hues, Barlow Condensed / DM Mono).
 * Built to the data-viz mark specs: thin marks, rounded data-ends, recessive
 * grid, direct labels, status/position color by role (never by rank).
 */
import { useState } from 'react'

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
}: {
  label: string
  pct01: number
  value: string
  color?: string
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
