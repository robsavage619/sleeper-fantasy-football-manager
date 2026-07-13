import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import { api, type ManagerReportCard, type ReportCardDimension } from '@/lib/api'

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
      <span
        style={{
          fontFamily: barlow,
          fontWeight: 800,
          fontSize: 15,
          color,
          lineHeight: 1,
        }}
      >
        {dim.grade}
      </span>
      <span className="tracking-wide uppercase" style={{ fontSize: 7, color: C.dim }}>
        {dim.label.split(' ').pop()}
      </span>
    </div>
  )
}

// ── Leaderboard row ───────────────────────────────────────────────────────────

function CardRow({ card, onOpen }: { card: ManagerReportCard; onOpen: (c: ManagerReportCard) => void }) {
  const color = gradeColor(card.overall_grade)
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: card.overall_rank * 0.03 }}
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
      <span style={{ width: 22, textAlign: 'right', color: C.dim, fontFamily: mono, fontSize: 13 }}>
        {card.overall_rank}
      </span>
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
          {card.titles > 0 && (
            <span style={{ fontSize: 11, color: C.amber }}>{'★'.repeat(card.titles)}</span>
          )}
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

// ── Drawer ────────────────────────────────────────────────────────────────────

function DimensionRow({ dim }: { dim: ReportCardDimension }) {
  const color = gradeColor(dim.grade)
  const fillPct = ((dim.of - dim.rank + 1) / dim.of) * 100
  return (
    <div style={{ padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: barlow, fontWeight: 700, fontSize: 15, color: C.text, letterSpacing: '0.03em' }}>
            {dim.label.toUpperCase()}
          </span>
          <span style={{ color: C.dim, fontSize: 11, fontFamily: mono }}>
            #{dim.rank} of {dim.of}
          </span>
        </div>
        <GradeBadge grade={dim.grade} size={30} />
      </div>
      <div style={{ height: 5, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
        <motion.div
          style={{ height: '100%', background: color, borderRadius: 3 }}
          initial={{ width: 0 }}
          animate={{ width: `${fillPct}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
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
      <div className="tracking-[0.15em] uppercase" style={{ color: C.dim, fontSize: 8, marginTop: 3 }}>
        {label}
      </div>
    </div>
  )
}

function SeasonTrend({ history }: { history: ManagerReportCard['season_history'] }) {
  if (history.length < 2) return null
  const maxWins = Math.max(...history.map((s) => s.wins + s.losses + s.ties), 1)
  return (
    <div>
      <div className="tracking-[0.18em] uppercase" style={{ color: C.dim, fontSize: 8, marginBottom: 8 }}>
        WINS BY SEASON
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 90 }}>
        {history.map((s) => {
          const games = s.wins + s.losses + s.ties || 1
          const h = Math.max(4, Math.round((s.wins / maxWins) * 66))
          const col = s.champion ? C.amber : s.made_playoffs ? C.green : C.dim
          return (
            <div key={s.season} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <span style={{ color: s.champion ? C.amber : C.text, fontSize: 11, fontFamily: mono, fontWeight: 700 }}>
                {s.champion ? '★' : s.wins}
              </span>
              <div style={{ width: '100%', maxWidth: 34, height: h, background: col, borderRadius: '2px 2px 0 0' }} title={`${s.wins}-${s.losses} of ${games}`} />
              <span style={{ color: C.muted, fontSize: 9, fontFamily: mono }}>{`'${s.season.slice(2)}`}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function GradeDrawerBody({ card }: { card: ManagerReportCard }) {
  const color = gradeColor(card.overall_grade)
  return (
    <>
      <div style={{ padding: '18px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <GradeBadge grade={card.overall_grade} size={62} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar avatar={card.avatar} name={card.display_name} size={22} />
              <span style={{ color: C.dim, fontFamily: mono, fontSize: 11 }}>
                #{card.overall_rank} in league · score {card.overall_score.toFixed(0)}
              </span>
            </div>
            <h2
              className="uppercase leading-none"
              style={{ color: C.text, fontFamily: barlow, fontSize: 32, fontWeight: 800, marginTop: 5 }}
            >
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
              <div
                key={s.season}
                style={{ display: 'grid', gridTemplateColumns: '52px 1fr 1fr 1.4fr', gap: 6, padding: '7px 10px', background: C.card, fontSize: 12, fontFamily: mono, alignItems: 'center' }}
              >
                <span style={{ color: C.text, fontWeight: 700 }}>{s.season}</span>
                <span style={{ textAlign: 'right', color: C.muted }}>
                  {s.wins}-{s.losses}
                  {s.ties ? `-${s.ties}` : ''}
                </span>
                <span style={{ textAlign: 'right', color: C.muted }}>
                  #{s.reg_finish}/{s.of_teams}
                </span>
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

function GradeDrawer({ card, onClose }: { card: ManagerReportCard | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {card && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 40 }}
          />
          <motion.aside
            initial={{ x: 540 }}
            animate={{ x: 0 }}
            exit={{ x: 540 }}
            transition={{ type: 'spring', damping: 30, stiffness: 260 }}
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 'min(540px, 100vw)',
              background: C.bg,
              borderLeft: `1px solid ${C.border}`,
              zIndex: 50,
              overflowY: 'auto',
              boxShadow: '-24px 0 60px rgba(0,0,0,0.45)',
            }}
          >
            <button
              onClick={onClose}
              aria-label="Close report card"
              style={{ position: 'absolute', top: 12, right: 12, border: '1px solid #24344f', background: C.card, color: C.muted, width: 28, height: 28, borderRadius: 2, cursor: 'pointer', zIndex: 2 }}
            >
              X
            </button>
            <GradeDrawerBody card={card} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ReportCard() {
  const [selected, setSelected] = useState<ManagerReportCard | null>(null)
  const { data, isLoading, error } = useQuery({
    queryKey: ['report-card'],
    queryFn: () => api.reportCard(),
    staleTime: 5 * 60 * 1000,
  })

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="flex items-baseline gap-4">
          <h1
            className="leading-none uppercase tracking-wide"
            style={{ fontFamily: barlow, fontSize: 40, fontWeight: 800, color: C.text }}
          >
            LEAGUE REPORT CARD
          </h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: C.muted }}>
            FRANCHISE GRADES · RANKED · GRADED ON THE CURVE
          </span>
        </div>
      </div>

      {isLoading && (
        <div className="p-8 text-center tracking-widest uppercase" style={{ color: C.dim, fontSize: 12 }}>
          GRADING THE LEAGUE…
        </div>
      )}
      {error && (
        <div className="mx-5 mt-4 p-3" style={{ background: 'rgba(201,51,40,0.06)', border: '1px solid rgba(201,51,40,0.2)', borderLeft: `3px solid ${C.red}`, borderRadius: 2, color: '#e07060', fontSize: 13 }}>
          {String(error)}
        </div>
      )}

      {data && (
        <>
          <div
            className="flex items-center gap-2 px-5 py-2 tracking-wide uppercase"
            style={{ borderBottom: `1px solid ${C.border}`, background: C.card, color: C.dim, fontSize: 9 }}
          >
            <span style={{ width: 22 }} />
            <span style={{ width: 44 }}>GRADE</span>
            <span style={{ flex: 1, marginLeft: 48 }}>MANAGER · CAREER</span>
            <span>VAL · SKL · TRK · BLD · CAP · ACT</span>
          </div>
          {data.map((card) => (
            <CardRow key={card.roster_id} card={card} onOpen={setSelected} />
          ))}
          <div className="px-5 py-3 tracking-wider uppercase" style={{ borderTop: `1px solid ${C.border}`, fontSize: 10, color: C.dim }}>
            VALUE · SKILL · TRACK RECORD · ROSTER BUILD · DRAFT CAPITAL · ACTIVITY — each graded #1–last within your league
          </div>
        </>
      )}

      <GradeDrawer card={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
