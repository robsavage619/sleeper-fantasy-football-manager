import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import { api, type PlayerProfile } from '@/lib/api'

function AnalyticsSection({ playerId }: { playerId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-sabermetrics', playerId],
    queryFn: () => api.playerSabermetrics(playerId),
    enabled: !!playerId,
  })

  if (isLoading) {
    return (
      <Section title="Analytics">
        <div style={{ color: '#3d5070', fontSize: 12 }}>Loading advanced metrics…</div>
      </Section>
    )
  }
  if (error || !data) {
    return (
      <Section title="Analytics">
        <div style={{ color: '#3d5070', fontSize: 12 }}>No advanced metrics available.</div>
      </Section>
    )
  }

  const c = data.consistency
  const xfp = data.xfp
  const mom = data.market_momentum?.trend_30day
  const degraded = data.data_quality !== 'ok'

  return (
    <Section title="Analytics">
      {(degraded || data.warnings.length > 0) && (
        <div
          style={{
            color: '#d4860c',
            background: 'rgba(212, 134, 12, 0.08)',
            border: '1px solid rgba(212, 134, 12, 0.25)',
            borderRadius: 2,
            padding: '8px 10px',
            fontSize: 11,
            lineHeight: 1.4,
            marginBottom: 10,
          }}
        >
          {degraded ? `Data quality: ${data.data_quality}` : ''}
          {degraded && data.warnings.length > 0 ? ' · ' : ''}
          {data.warnings.join(' · ')}
        </div>
      )}

      {c && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Metric label="Floor" value={c.floor.toFixed(1)} sub="10th pct week" />
            <Metric label="Median" value={c.median.toFixed(1)} sub="typical week" />
            <Metric label="Ceiling" value={c.ceiling.toFixed(1)} sub="90th pct week" />
          </div>
          <div className="grid grid-cols-2 gap-2" style={{ marginTop: 8 }}>
            <Metric label="Boom %" value={`${(c.boom_pct * 100).toFixed(0)}%`} />
            <Metric label="Bust %" value={`${(c.bust_pct * 100).toFixed(0)}%`} />
          </div>
        </>
      )}

      {xfp && (
        <div style={{ marginTop: 12, borderTop: '1px solid #162035', paddingTop: 12 }}>
          <div className="grid grid-cols-2 gap-2">
            <Metric
              label="xFP Residual"
              value={`${xfp.residual >= 0 ? '+' : ''}${xfp.residual.toFixed(1)}`}
              sub={`${xfp.actual_fp.toFixed(0)} actual vs ${xfp.xfp.toFixed(0)} expected`}
            />
            <Metric
              label="30-Day Market"
              value={mom == null ? '—' : `${mom >= 0 ? '+' : ''}${mom}`}
              sub="value trend"
            />
          </div>
          {xfp.label && (
            <div style={{ color: '#6a8098', fontSize: 11, marginTop: 8, lineHeight: 1.4, fontStyle: 'italic' }}>
              {xfp.label}
            </div>
          )}
        </div>
      )}
    </Section>
  )
}

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ border: '1px solid #162035', background: '#09111f', padding: '10px 12px' }}>
      <div className="tracking-[0.24em] uppercase" style={{ color: '#3d5070', fontSize: 9 }}>
        {label}
      </div>
      <div
        style={{
          color: '#e8eef6',
          fontFamily: "'Barlow Condensed', sans-serif",
          fontSize: 26,
          fontWeight: 800,
          lineHeight: 1,
          marginTop: 4,
        }}
      >
        {value}
      </div>
      {sub && <div style={{ color: '#6a8098', fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ borderTop: '1px solid #162035', padding: '14px 18px' }}>
      <div
        className="tracking-[0.28em] uppercase"
        style={{ color: '#6a8098', fontSize: 10, marginBottom: 10 }}
      >
        {title}
      </div>
      {children}
    </section>
  )
}

function ProfileBody({ profile }: { profile: PlayerProfile }) {
  const color = POS_COLOR[profile.identity.position] ?? '#6a8098'
  const latestWeeks = [...profile.weekly].reverse().slice(0, 8)
  const injuries = profile.injuries.filter((row) => row.injury !== 'summary').slice(-8).reverse()
  const injurySummary = profile.injuries.find((row) => row.injury === 'summary')

  return (
    <>
      <div style={{ padding: '18px', borderBottom: '1px solid #162035' }}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="tracking-[0.3em] uppercase" style={{ color, fontSize: 10 }}>
              {profile.identity.position} · {profile.identity.team || 'FA'} · AGE{' '}
              {profile.identity.age ? profile.identity.age.toFixed(0) : '—'}
            </div>
            <h2
              className="uppercase leading-none"
              style={{
                color: '#e8eef6',
                fontFamily: "'Barlow Condensed', sans-serif",
                fontSize: 38,
                fontWeight: 800,
                marginTop: 5,
              }}
            >
              {profile.identity.name}
            </h2>
          </div>
          <span
            className="tracking-[0.18em] uppercase"
            style={{
              border: `1px solid ${profile.data_quality === 'FULL' ? '#1a9b5e' : '#d4860c'}`,
              color: profile.data_quality === 'FULL' ? '#1a9b5e' : '#d4860c',
              fontSize: 10,
              padding: '4px 7px',
              flexShrink: 0,
            }}
          >
            {profile.data_quality}
          </span>
        </div>
      </div>

      {profile.warnings.length > 0 && (
        <div
          style={{
            color: '#d4860c',
            background: 'rgba(212, 134, 12, 0.08)',
            borderBottom: '1px solid rgba(212, 134, 12, 0.25)',
            padding: '10px 18px',
            fontSize: 12,
            lineHeight: 1.45,
          }}
        >
          {profile.warnings.join(' · ')}
        </div>
      )}

      <Section title="Value Under Our Rules">
        <div className="grid grid-cols-3 gap-2">
          <Metric
            label="Dynasty"
            value={profile.value.dynasty_value.toFixed(1)}
            sub={`${profile.value.pick_equivalent} equivalent`}
          />
          <Metric
            label="FPAR"
            value={profile.value.current_fpar.toFixed(1)}
            sub={`season ${profile.value.valuation_season}`}
          />
          <Metric
            label="PPG"
            value={profile.fantasy_summary.points_per_game.toFixed(1)}
            sub={`${profile.fantasy_summary.games} games`}
          />
        </div>
        <div style={{ color: '#8aa0b8', fontSize: 12, marginTop: 10 }}>
          {profile.value.age_curve}
        </div>
      </Section>

      <Section title="Trajectory">
        {profile.season_summaries.length === 0 ? (
          <div style={{ color: '#3d5070', fontSize: 12 }}>No scored season history.</div>
        ) : (
          <div style={{ display: 'grid', gap: 1, background: '#162035' }}>
            {profile.season_summaries.map((season) => (
              <div
                key={season.season}
                className="grid grid-cols-5 gap-2"
                style={{ background: '#0c1625', padding: '8px 10px', fontSize: 12 }}
              >
                <span style={{ color: '#e8eef6', fontFamily: "'DM Mono', monospace" }}>
                  {season.season}
                </span>
                <span style={{ color: '#6a8098' }}>{season.games} G</span>
                <span style={{ color: '#d4860c' }}>{season.points_per_game.toFixed(1)} PPG</span>
                <span style={{ color: '#3a8cd4' }}>{season.targets} TGT</span>
                <span style={{ color: '#24a870' }}>{season.carries} CAR</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Usage">
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Recent Tgt/G" value={profile.usage.recent_targets_per_game.toFixed(1)} />
          <Metric label="Recent Car/G" value={profile.usage.recent_carries_per_game.toFixed(1)} />
          <Metric
            label="Snap %"
            value={
              profile.usage.recent_snap_pct == null
                ? '—'
                : `${profile.usage.recent_snap_pct.toFixed(0)}%`
            }
          />
        </div>
        {profile.depth && (
          <div style={{ color: '#8aa0b8', fontSize: 12, marginTop: 10 }}>
            Depth: {profile.depth.team} {profile.depth.depth_position} · team{' '}
            {profile.depth.depth_team} · week {profile.depth.week}
          </div>
        )}
      </Section>

      <AnalyticsSection playerId={profile.player_id} />

      <Section title="Recent Weeks">
        {latestWeeks.length === 0 ? (
          <div style={{ color: '#3d5070', fontSize: 12 }}>No weekly game log.</div>
        ) : (
          <div style={{ display: 'grid', gap: 1, background: '#162035' }}>
            {latestWeeks.map((week) => (
              <div
                key={`${week.season}-${week.week}`}
                className="grid grid-cols-6 gap-2"
                style={{ background: '#0c1625', padding: '8px 10px', fontSize: 12 }}
              >
                <span style={{ color: '#6a8098' }}>
                  {week.season} W{week.week}
                </span>
                <span style={{ color: '#e8eef6' }}>{week.team}</span>
                <span style={{ color: '#d4860c' }}>{week.fantasy_points.toFixed(1)}</span>
                <span style={{ color: '#3a8cd4' }}>{week.targets} tgt</span>
                <span style={{ color: '#24a870' }}>{week.carries} car</span>
                <span style={{ color: '#6a8098' }}>{week.touchdowns} TD</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Injuries">
        {injurySummary && (
          <div style={{ color: '#d4860c', fontSize: 12, marginBottom: 8 }}>
            {injurySummary.status}
          </div>
        )}
        {injuries.length === 0 ? (
          <div style={{ color: '#3d5070', fontSize: 12 }}>No injury reports found.</div>
        ) : (
          <div style={{ display: 'grid', gap: 1, background: '#162035' }}>
            {injuries.map((item, index) => (
              <div
                key={`${item.season}-${item.week}-${index}`}
                className="grid grid-cols-4 gap-2"
                style={{ background: '#0c1625', padding: '8px 10px', fontSize: 12 }}
              >
                <span style={{ color: '#6a8098' }}>
                  {item.season} W{item.week}
                </span>
                <span style={{ color: '#e8eef6' }}>{item.team}</span>
                <span style={{ color: '#d4860c' }}>{item.injury || '—'}</span>
                <span style={{ color: '#8aa0b8' }}>{item.status || '—'}</span>
              </div>
            ))}
          </div>
        )}
      </Section>
    </>
  )
}

export function PlayerProfileDrawer({
  playerId,
  onClose,
}: {
  playerId: string | null
  onClose: () => void
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-profile', playerId],
    queryFn: () => api.playerProfile(playerId ?? ''),
    enabled: playerId !== null,
  })

  return (
    <AnimatePresence>
      {playerId && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0, 0, 0, 0.45)',
              zIndex: 40,
            }}
          />
          <motion.aside
            initial={{ x: 520 }}
            animate={{ x: 0 }}
            exit={{ x: 520 }}
            transition={{ type: 'spring', damping: 30, stiffness: 260 }}
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 'min(520px, 100vw)',
              background: '#060a12',
              borderLeft: '1px solid #162035',
              zIndex: 50,
              overflowY: 'auto',
              boxShadow: '-24px 0 60px rgba(0,0,0,0.45)',
            }}
          >
            <button
              onClick={onClose}
              aria-label="Close player profile"
              style={{
                position: 'absolute',
                top: 12,
                right: 12,
                border: '1px solid #24344f',
                background: '#09111f',
                color: '#6a8098',
                width: 28,
                height: 28,
                borderRadius: 2,
                cursor: 'pointer',
                zIndex: 2,
              }}
            >
              X
            </button>
            {isLoading && (
              <div className="p-8 tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>
                Loading player intelligence...
              </div>
            )}
            {error && (
              <div className="p-8" style={{ color: '#c93328', fontSize: 13 }}>
                {String(error)}
              </div>
            )}
            {data && <ProfileBody profile={data} />}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
