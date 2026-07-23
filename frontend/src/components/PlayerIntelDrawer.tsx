import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import { api, type IntelFlag, type PlayerIntel } from '@/lib/api'
import { INK, POS_COLOR, STATUS, SURFACE } from '@/components/viz'

/**
 * Situation intel from the engine's own research (studies S2-S6): when a player's
 * track record has stopped applying, and why.
 *
 * The panel deliberately shows the evidence next to every claim rather than a
 * single confidence score. The findings behind these flags differ in strength —
 * the quarterback effect replicated out of sample, the running-back attrition
 * split rests on a definition the study itself flags as shaky — and collapsing
 * them into one number would hide exactly the distinctions worth acting on.
 */

const SEVERITY_COLOR: Record<IntelFlag['severity'], string> = {
  ALERT: STATUS.bad,
  WATCH: STATUS.warn,
  INFO: STATUS.ok,
}

const SEVERITY_HINT: Record<IntelFlag['severity'], string> = {
  ALERT: 'Should move a roster decision',
  WATCH: 'Worth weighing, not decisive',
  INFO: 'Context — often a reason NOT to act',
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ borderTop: `1px solid ${SURFACE.border}`, padding: '14px 18px' }}>
      <div
        className="tracking-[0.28em] uppercase"
        style={{ color: INK.muted, fontSize: 10, marginBottom: 10 }}
      >
        {title}
      </div>
      {children}
    </section>
  )
}

function FlagCard({ flag }: { flag: IntelFlag }) {
  const color = SEVERITY_COLOR[flag.severity]
  return (
    <div
      style={{
        borderLeft: `2px solid ${color}`,
        background: SURFACE.card,
        padding: '10px 12px',
        marginBottom: 8,
      }}
    >
      <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
        <span
          className="tracking-[0.18em] uppercase"
          style={{ color, fontSize: 9, fontWeight: 600 }}
          title={SEVERITY_HINT[flag.severity]}
        >
          {flag.severity}
        </span>
        <span
          style={{
            color: INK.dim,
            fontSize: 9,
            fontFamily: "'DM Mono', monospace",
            border: `1px solid ${SURFACE.border2}`,
            padding: '1px 5px',
          }}
          title="Which study established this"
        >
          {flag.study}
        </span>
      </div>
      <div style={{ color: INK.primary, fontSize: 13, lineHeight: 1.45 }}>{flag.headline}</div>
      <div style={{ color: INK.muted, fontSize: 11, lineHeight: 1.5, marginTop: 6 }}>
        {flag.evidence}
      </div>
    </div>
  )
}

function PlayerCard({ player }: { player: PlayerIntel }) {
  const color = POS_COLOR[player.position] ?? INK.muted
  const alerts = player.flags.filter((f) => f.severity === 'ALERT').length

  return (
    <div style={{ marginBottom: 18 }}>
      <div className="flex items-baseline gap-2" style={{ marginBottom: 8 }}>
        <span style={{ color, fontSize: 10, fontWeight: 700 }}>{player.position}</span>
        <span style={{ color: INK.primary, fontSize: 14, fontWeight: 600 }}>{player.name}</span>
        <span style={{ color: INK.dim, fontSize: 11 }}>
          {player.team}
          {player.age != null ? ` · ${player.age.toFixed(0)}` : ''}
          {player.archetype ? ` · ${player.archetype.replace(/_/g, ' ')}` : ''}
        </span>
        {alerts > 0 && (
          <span style={{ color: STATUS.bad, fontSize: 10, marginLeft: 'auto' }}>
            {alerts} alert{alerts > 1 ? 's' : ''}
          </span>
        )}
      </div>
      {player.flags.map((flag, i) => (
        <FlagCard key={`${flag.kind}-${i}`} flag={flag} />
      ))}
    </div>
  )
}

export function PlayerIntelDrawer({
  open,
  rosterId,
  onClose,
}: {
  open: boolean
  /** Omit to sweep the whole league — what a waiver or trade-target scan wants. */
  rosterId?: number
  onClose: () => void
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-intel', rosterId ?? 'league'],
    queryFn: () => api.playerIntel(rosterId),
    enabled: open,
  })

  const flagged = data?.players.filter((p) => p.flags.length > 0) ?? []

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 40 }}
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
              background: '#060a12',
              borderLeft: `1px solid ${SURFACE.border}`,
              zIndex: 50,
              overflowY: 'auto',
              boxShadow: '-24px 0 60px rgba(0,0,0,0.45)',
            }}
          >
            <header
              className="flex items-start justify-between"
              style={{ padding: '18px 18px 14px' }}
            >
              <div>
                <div
                  className="tracking-[0.28em] uppercase"
                  style={{ color: INK.muted, fontSize: 10 }}
                >
                  Player Intel
                </div>
                <div style={{ color: INK.primary, fontSize: 18, fontWeight: 600, marginTop: 4 }}>
                  When a track record stops applying
                </div>
                <div style={{ color: INK.dim, fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
                  {data?.scope === 'league' ? 'League-wide sweep' : 'Your roster'} · flags from this
                  engine's own studies, each shown with the effect size behind it
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  color: INK.muted,
                  fontSize: 18,
                  lineHeight: 1,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
                aria-label="Close player intel"
              >
                ×
              </button>
            </header>

            {isLoading && (
              <Section title="Loading">
                <div style={{ color: INK.dim, fontSize: 12 }}>Reading situation research…</div>
              </Section>
            )}

            {error != null && (
              <Section title="Unavailable">
                <div style={{ color: STATUS.bad, fontSize: 12 }}>
                  Could not load intel. The context table may not be built yet — run{' '}
                  <code style={{ fontFamily: "'DM Mono', monospace" }}>sffm ingest</code>.
                </div>
              </Section>
            )}

            {!isLoading && error == null && flagged.length === 0 && (
              <Section title="No flags">
                <div style={{ color: INK.muted, fontSize: 12, lineHeight: 1.6 }}>
                  Nobody's situation changed enough to undermine their track record — no team,
                  coach or quarterback moves worth flagging. That is a clean result, not a missing
                  one.
                </div>
              </Section>
            )}

            {flagged.length > 0 && (
              <Section title={`${flagged.length} flagged`}>
                {flagged.map((player) => (
                  <PlayerCard key={player.player_id} player={player} />
                ))}
              </Section>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
