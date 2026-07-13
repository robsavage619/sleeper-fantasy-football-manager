import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api, type MyRosterPlayer } from '@/lib/api'

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const
type Position = (typeof POSITIONS)[number]

function PlayerRow({ player, index }: { player: MyRosterPlayer; index: number }) {
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
      }}
    >
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
      <span
        style={{
          fontSize: 13,
          color: '#d4860c',
          fontFamily: "'DM Mono', monospace",
          width: 52,
          textAlign: 'right',
          flexShrink: 0,
        }}
      >
        {player.dynasty_value.toFixed(1)}
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

function PositionGroup({ position, players }: { position: Position; players: MyRosterPlayer[] }) {
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
        <PlayerRow key={player.player_id} player={player} index={i} />
      ))}
    </div>
  )
}

export function Roster() {
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
              </span>
            </div>
          )}
        </div>
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
            <PositionGroup key={pos} position={pos} players={byPosition.get(pos) ?? []} />
          ))}
        </div>
      )}
    </div>
  )
}
