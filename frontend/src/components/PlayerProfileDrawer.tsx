import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import { api, type PlayerProfile } from '@/lib/api'
import {
  Donut,
  INK,
  InfoTip,
  MiniBars,
  PercentileBar,
  PlayerHeadshot,
  POS_COLOR,
  RangeBar,
  Sparkline,
  STATUS,
} from '@/components/viz'
import { GLOSSARY } from '@/lib/glossary'

const USAGE_INFO: Record<string, string> = {
  WOPR: GLOSSARY.wopr,
  'Target Share': GLOSSARY.targetShare,
  'Air-Yds Share': GLOSSARY.airYardsShare,
}

/** Price-history sparkline — the endpoint was wrapped in the client but never rendered anywhere. */
function PriceTrendSection({ playerId }: { playerId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['price-trend', playerId],
    queryFn: () => api.playerPriceTrend(playerId),
    enabled: !!playerId,
  })

  if (isLoading) {
    return (
      <Section title="Market Price Trend">
        <div style={{ color: '#3d5070', fontSize: 12 }}>Loading price history…</div>
      </Section>
    )
  }
  if (!data || data.points.length < 2) {
    return (
      <Section title="Market Price Trend">
        <div style={{ color: '#3d5070', fontSize: 12 }}>{data?.note ?? 'Not enough snapshots yet for a trend.'}</div>
      </Section>
    )
  }

  const momentum = data.momentum_pct
  return (
    <Section title="Market Price Trend">
      <div className="flex items-center gap-4">
        <Sparkline values={data.points.map((p) => p.value)} width={140} height={36} />
        <div>
          <div
            style={{
              fontFamily: "'DM Mono', monospace",
              fontSize: 16,
              fontWeight: 600,
              color: momentum == null ? INK.muted : momentum >= 0 ? STATUS.good : STATUS.bad,
            }}
          >
            {momentum != null ? `${momentum > 0 ? '+' : ''}${momentum.toFixed(1)}%` : '—'}
          </div>
          <div style={{ color: INK.dim, fontSize: 10 }}>{data.snapshot_dates.length} snapshots</div>
        </div>
      </div>
    </Section>
  )
}

/** Stadium/weather environment splits — distinct from the league-wide flag list on Matchups. */
function EnvironmentSection({ playerId }: { playerId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-environment', playerId],
    queryFn: () => api.playerEnvironment(playerId),
    enabled: !!playerId,
  })

  if (isLoading) {
    return (
      <Section title="Environment Splits">
        <div style={{ color: '#3d5070', fontSize: 12 }}>Loading environment splits…</div>
      </Section>
    )
  }
  if (error || !data) {
    return (
      <Section title="Environment Splits">
        <div style={{ color: '#3d5070', fontSize: 12 }}>No environment splits available.</div>
      </Section>
    )
  }

  const splitRows = Object.entries(data.splits)
  if (splitRows.length === 0 && data.stadiums.length === 0) {
    return (
      <Section title="Environment Splits">
        <div style={{ color: '#3d5070', fontSize: 12 }}>Not enough games ({data.total_games}) for a reliable split.</div>
      </Section>
    )
  }

  return (
    <Section title="Environment Splits">
      {data.flags.length > 0 && (
        <div style={{ color: '#d4860c', fontSize: 11, marginBottom: 10 }}>{data.flags.join(' · ')}</div>
      )}
      {splitRows.length > 0 && (
        <div style={{ display: 'grid', gap: 1, background: '#162035', marginBottom: 10 }}>
          {splitRows.map(([bucket, s]) => (
            <div key={bucket} className="grid grid-cols-4 gap-2" style={{ background: '#0c1625', padding: '8px 10px', fontSize: 12 }}>
              <span style={{ color: '#e8eef6', textTransform: 'capitalize' }}>{bucket.replace(/_/g, ' ')}</span>
              <span style={{ color: '#6a8098' }}>{s.games} G</span>
              <span style={{ color: '#d4860c' }}>{s.avg_fp.toFixed(1)} FP</span>
              <span style={{ color: s.delta >= 0 ? STATUS.good : STATUS.bad, fontFamily: "'DM Mono', monospace" }}>
                {s.delta >= 0 ? '+' : ''}{s.delta.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      )}
      {data.stadiums.length > 0 && (
        <div style={{ display: 'grid', gap: 1, background: '#162035' }}>
          {data.stadiums.slice(0, 6).map((s) => (
            <div key={s.stadium} className="grid grid-cols-4 gap-2" style={{ background: '#0c1625', padding: '8px 10px', fontSize: 12 }}>
              <span style={{ color: '#e8eef6' }}>{s.stadium}</span>
              <span style={{ color: '#6a8098' }}>{s.games} G</span>
              <span style={{ color: '#d4860c' }}>{s.avg_fp.toFixed(1)} FP</span>
              <span style={{ color: s.delta >= 0 ? STATUS.good : STATUS.bad, fontFamily: "'DM Mono', monospace" }}>
                {s.delta >= 0 ? '+' : ''}{s.delta.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

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
  const uq = data.usage_quality
  const degraded = data.data_quality !== 'ok'

  // Usage-quality metrics that live naturally on a 0..1 scale → percentile bars.
  const pct = (n: number): string => `${(n * 100).toFixed(0)}%`
  const usageBars: { label: string; v: number | null; fmt: (n: number) => string }[] = [
    { label: 'WOPR', v: uq?.wopr ?? null, fmt: (n: number) => n.toFixed(2) },
    { label: 'Target Share', v: uq?.target_share ?? null, fmt: pct },
    { label: 'Air-Yds Share', v: uq?.air_yards_share ?? null, fmt: pct },
    { label: 'Snap Share', v: uq?.snap_share ?? null, fmt: pct },
  ].filter((b) => b.v != null)

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
            marginBottom: 12,
          }}
        >
          {degraded ? `Data quality: ${data.data_quality}` : ''}
          {degraded && data.warnings.length > 0 ? ' · ' : ''}
          {data.warnings.join(' · ')}
        </div>
      )}

      {c && (
        <div className="flex items-center gap-4" style={{ marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <div
              className="tracking-[0.14em] uppercase"
              style={{ color: INK.muted, fontSize: 9.5, marginBottom: 6 }}
            >
              Weekly outcome range
            </div>
            <RangeBar
              floor={c.floor}
              median={c.median}
              ceiling={c.ceiling}
              max={c.ceiling * 1.1}
            />
            <div style={{ color: INK.muted, fontSize: 10.5, marginTop: 6, lineHeight: 1.4 }}>
              Volatility {c.volatility.toFixed(2)} · startable line {c.startable_line.toFixed(1)}
            </div>
          </div>
          <Donut pct01={c.boom_pct} color={STATUS.good} label="Boom" />
          <Donut pct01={c.bust_pct} color={STATUS.bad} label="Bust" />
        </div>
      )}

      {usageBars.length > 0 && (
        <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
          {usageBars.map((b) => (
            <PercentileBar
              key={b.label}
              label={b.label}
              pct01={b.v as number}
              value={b.fmt(b.v as number)}
              info={USAGE_INFO[b.label]}
            />
          ))}
        </div>
      )}

      {xfp && (
        <div style={{ borderTop: '1px solid #162035', paddingTop: 12 }}>
          <div className="grid grid-cols-2 gap-2">
            <Metric
              label="xFP Residual"
              value={`${xfp.residual >= 0 ? '+' : ''}${xfp.residual.toFixed(1)}`}
              sub={`${xfp.actual_fp.toFixed(0)} actual vs ${xfp.xfp.toFixed(0)} expected`}
              info={GLOSSARY.xfpResidual}
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

function Metric({ label, value, sub, info }: { label: string; value: string; sub?: string; info?: string }) {
  return (
    <div style={{ border: '1px solid #162035', background: '#09111f', padding: '10px 12px' }}>
      <div className="tracking-[0.24em] uppercase" style={{ color: '#3d5070', fontSize: 9 }}>
        {label}
        {info && <InfoTip text={info} label={label} />}
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
          <div className="flex items-center gap-3">
            <PlayerHeadshot
              playerId={profile.player_id}
              name={profile.identity.name}
              position={profile.identity.position}
              size={58}
            />
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
                  fontSize: 34,
                  fontWeight: 800,
                  marginTop: 5,
                }}
              >
                {profile.identity.name}
              </h2>
            </div>
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
            info={GLOSSARY.dynastyValue}
          />
          <Metric
            label="FPAR"
            value={profile.value.current_fpar.toFixed(1)}
            sub={`season ${profile.value.valuation_season}`}
            info={GLOSSARY.currentFpar}
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
        {profile.value.age_curve_adjustment != null && (
          <div className="flex items-center gap-1" style={{ color: '#6a8098', fontSize: 11, marginTop: 4 }}>
            {profile.value.career_phase ?? 'n/a'}: {profile.value.age_curve_adjustment >= 0 ? '+' : ''}
            {profile.value.age_curve_adjustment.toFixed(0)} age-curve adjustment on top of {profile.value.current_fpar.toFixed(0)} current FPAR
            <InfoTip text={GLOSSARY.ageCurveAdjustment} label="age-curve adjustment" />
          </div>
        )}
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

      <PriceTrendSection playerId={profile.player_id} />
      <EnvironmentSection playerId={profile.player_id} />

      <Section title="Recent Weeks">
        {latestWeeks.length === 0 ? (
          <div style={{ color: '#3d5070', fontSize: 12 }}>No weekly game log.</div>
        ) : (
          <>
            {(() => {
              const chrono = profile.weekly.slice(-12)
              const pts = chrono.map((w) => w.fantasy_points)
              const sorted = [...pts].sort((a, b) => a - b)
              const median = sorted[Math.floor(sorted.length / 2)] ?? 0
              return (
                <div style={{ marginBottom: 10 }}>
                  <MiniBars
                    values={pts}
                    labels={chrono.map((w) => `${w.season} W${w.week}`)}
                    boomLine={median * 1.35}
                    bustLine={median * 0.6}
                    height={44}
                  />
                  <div className="flex justify-between" style={{ marginTop: 4 }}>
                    <span style={{ color: INK.dim, fontSize: 9 }}>
                      {chrono[0] ? `${chrono[0].season} W${chrono[0].week}` : ''}
                    </span>
                    <span style={{ color: STATUS.good, fontSize: 9 }}>■ boom</span>
                    <span style={{ color: STATUS.bad, fontSize: 9 }}>■ bust</span>
                    <span style={{ color: INK.dim, fontSize: 9 }}>latest</span>
                  </div>
                </div>
              )
            })()}
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
          </>
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
