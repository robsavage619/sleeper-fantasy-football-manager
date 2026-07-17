import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { PlayerProfileDrawer } from '@/components/PlayerProfileDrawer'
import { InfoTip, PlayerHeadshot, POS_COLOR, StackBar } from '@/components/viz'
import { api, type MyRosterPlayer } from '@/lib/api'
import { GLOSSARY } from '@/lib/glossary'

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const
type Position = (typeof POSITIONS)[number]

function PlayerRow({
  player,
  index,
  maxValue,
  onOpen,
}: {
  player: MyRosterPlayer
  index: number
  maxValue: number
  onOpen: (playerId: string) => void
}) {
  const barPct = maxValue > 0 ? Math.max(0.02, player.dynasty_value / maxValue) : 0
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.02 }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 16px',
        borderBottom: '1px solid #162035',
        cursor: 'pointer',
      }}
      onClick={() => onOpen(player.player_id)}
    >
      <PlayerHeadshot
        playerId={player.player_id}
        name={player.name}
        position={player.position}
        size={30}
      />
      <span style={{ flex: 1, fontSize: 14, fontWeight: 500, color: '#e8eef6', minWidth: 0 }}>
        {player.name}
      </span>
      <span
        style={{
          fontSize: 12,
          color: '#6a8098',
          fontFamily: "'DM Mono', monospace",
          width: 28,
          textAlign: 'center',
          flexShrink: 0,
        }}
      >
        {Math.round(player.age)}
      </span>
      <span style={{ fontSize: 12, color: '#3d5070', width: 36, textAlign: 'center', flexShrink: 0 }}>
        {player.team || 'FA'}
      </span>
      <div style={{ width: 80, flexShrink: 0 }}>
        <div style={{ height: 5, background: '#162035', borderRadius: 3, overflow: 'hidden' }}>
          <div
            style={{
              width: `${barPct * 100}%`,
              height: '100%',
              background: POS_COLOR[player.position] ?? '#6a8098',
              borderRadius: 3,
            }}
          />
        </div>
      </div>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, width: 62, justifyContent: 'flex-end', flexShrink: 0 }}>
        <span
          style={{
            fontSize: 13,
            color: '#d4860c',
            fontFamily: "'DM Mono', monospace",
            textAlign: 'right',
          }}
        >
          {player.dynasty_value.toFixed(1)}
        </span>
        <InfoTip
          text={`${GLOSSARY.dynastyValue} Model side: ${player.fpar.toFixed(0)} current FPAR ${
            player.age_curve_adjustment != null
              ? `${player.age_curve_adjustment >= 0 ? '+' : ''}${player.age_curve_adjustment.toFixed(0)} age-curve (${player.career_phase ?? 'n/a'})`
              : ''
          } = ${player.model_value != null ? player.model_value.toFixed(0) : player.dynasty_value.toFixed(0)} model value.${
            player.market_valued
              ? ` Market anchored the displayed ${player.dynasty_value.toFixed(0)}${player.position === 'QB' ? ' — QB is priced market-only, the model side above is not used for QBs.' : '.'}`
              : ''
          }`}
          label="dynasty value"
          align="right"
        />
      </span>
      <div style={{ display: 'flex', gap: 4, width: 120, justifyContent: 'flex-end', flexShrink: 0 }}>
        {player.is_starter && !player.is_taxi && !player.is_reserve && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.25em',
              padding: '2px 5px',
              color: '#00b8cc',
              background: 'rgba(0, 184, 204, 0.1)',
              border: '1px solid rgba(0, 184, 204, 0.25)',
              borderRadius: 1,
              textTransform: 'uppercase',
            }}
          >
            STARTER
          </span>
        )}
        {player.is_taxi && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.25em',
              padding: '2px 5px',
              color: '#d4860c',
              background: 'rgba(212, 134, 12, 0.1)',
              border: '1px solid rgba(212, 134, 12, 0.25)',
              borderRadius: 1,
              textTransform: 'uppercase',
            }}
          >
            TAXI
          </span>
        )}
        {player.is_reserve && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.25em',
              padding: '2px 5px',
              color: '#c93328',
              background: 'rgba(201, 51, 40, 0.1)',
              border: '1px solid rgba(201, 51, 40, 0.25)',
              borderRadius: 1,
              textTransform: 'uppercase',
            }}
          >
            IR
          </span>
        )}
      </div>
    </motion.div>
  )
}

function PositionGroup({
  position,
  players,
  maxValue,
  onOpen,
}: {
  position: Position
  players: MyRosterPlayer[]
  maxValue: number
  onOpen: (playerId: string) => void
}) {
  const color = POS_COLOR[position]

  const sorted = [
    ...players
      .filter((p) => p.is_starter && !p.is_taxi && !p.is_reserve)
      .sort((a, b) => b.dynasty_value - a.dynasty_value),
    ...players
      .filter((p) => !p.is_starter && !p.is_taxi && !p.is_reserve)
      .sort((a, b) => b.dynasty_value - a.dynasty_value),
    ...players.filter((p) => p.is_taxi).sort((a, b) => b.dynasty_value - a.dynasty_value),
    ...players.filter((p) => p.is_reserve).sort((a, b) => b.dynasty_value - a.dynasty_value),
  ]

  if (sorted.length === 0) return null

  return (
    <div
      style={{
        background: '#0c1625',
        border: '1px solid #162035',
        borderLeft: `3px solid ${color}`,
        borderRadius: 2,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          borderBottom: '1px solid #162035',
        }}
      >
        <span
          style={{
            fontSize: 10,
            color,
            letterSpacing: '0.3em',
            textTransform: 'uppercase',
            fontWeight: 700,
            fontFamily: "'Barlow Condensed', sans-serif",
          }}
        >
          {position}
        </span>
        <span style={{ fontSize: 11, color: '#3d5070', fontFamily: "'DM Mono', monospace" }}>
          {sorted.length}
        </span>
      </div>
      {sorted.map((player, i) => (
        <PlayerRow
          key={player.player_id}
          player={player}
          index={i}
          maxValue={maxValue}
          onOpen={onOpen}
        />
      ))}
    </div>
  )
}

export function Roster() {
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({
    queryKey: ['my-roster'],
    queryFn: () => api.myRoster(),
  })

  const byPosition = new Map<Position, MyRosterPlayer[]>()
  for (const pos of POSITIONS) byPosition.set(pos, [])
  for (const player of data?.players ?? []) {
    const group = byPosition.get(player.position as Position)
    if (group) group.push(player)
  }
  const maxValue = Math.max(1, ...(data?.players ?? []).map((p) => p.dynasty_value))
  const posValue = POSITIONS.map((pos) => ({
    label: pos,
    value: (byPosition.get(pos) ?? []).reduce((s, p) => s + p.dynasty_value, 0),
    color: POS_COLOR[pos],
  }))

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1
            className="leading-none uppercase tracking-wide"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontSize: 40,
              fontWeight: 800,
              color: '#e8eef6',
            }}
          >
            MY ROSTER
          </h1>
          {data && (
            <div className="flex items-baseline gap-3">
              <span
                style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: 32,
                  fontWeight: 700,
                  color: '#d4860c',
                  fontVariantNumeric: 'tabular-nums',
                  lineHeight: 1,
                }}
              >
                {data.total_dynasty_value.toFixed(0)}
              </span>
              <span
                className="tracking-[0.2em] uppercase"
                style={{ fontSize: 11, color: '#6a8098' }}
              >
                DYNASTY · {data.total_players} PLAYERS
                <InfoTip text={GLOSSARY.dynastyValue} label="dynasty value" />
              </span>
            </div>
          )}
        </div>
        {data && (
          <div style={{ marginTop: 12, maxWidth: 520 }}>
            <div
              className="tracking-[0.18em] uppercase"
              style={{ color: '#3d5070', fontSize: 9, marginBottom: 5 }}
            >
              Value by position
            </div>
            <StackBar segments={posValue} height={9} />
            <div className="flex gap-4" style={{ marginTop: 6 }}>
              {posValue.map((s) => (
                <span key={s.label} className="flex items-center gap-1.5" style={{ fontSize: 10 }}>
                  <span
                    style={{ width: 8, height: 8, background: s.color, borderRadius: 2, display: 'inline-block' }}
                  />
                  <span style={{ color: '#8aa0b8' }}>{s.label}</span>
                  <span style={{ color: '#3d5070', fontFamily: "'DM Mono', monospace" }}>
                    {s.value.toFixed(0)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {isLoading && (
        <div
          className="p-8 text-center tracking-widest uppercase"
          style={{ color: '#3d5070', fontSize: 12 }}
        >
          LOADING ROSTER…
        </div>
      )}

      {error && (
        <div
          className="mx-5 mt-4 p-3"
          style={{
            background: 'rgba(201, 51, 40, 0.06)',
            border: '1px solid rgba(201, 51, 40, 0.2)',
            borderLeft: '3px solid #c93328',
            borderRadius: 2,
            color: '#e07060',
            fontSize: 13,
          }}
        >
          {String(error)}
        </div>
      )}

      {data && (
        <div className="p-5 grid gap-4">
          {POSITIONS.map((pos) => (
            <PositionGroup
              key={pos}
              position={pos}
              players={byPosition.get(pos) ?? []}
              maxValue={maxValue}
              onOpen={setSelectedPlayerId}
            />
          ))}
        </div>
      )}
      <PlayerProfileDrawer
        playerId={selectedPlayerId}
        onClose={() => setSelectedPlayerId(null)}
      />
    </div>
  )
}
