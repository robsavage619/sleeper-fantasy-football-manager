import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { api, type DraftPlayer } from '@/lib/api'

const POS_COLOR: Record<string, string> = {
  QB: '#e05030',
  RB: '#24a870',
  WR: '#3a8cd4',
  TE: '#c8820a',
}

const TABLE_COLS = [
  { label: '#', className: 'py-2 pl-3 pr-2 w-10' },
  { label: 'PLAYER', className: 'py-2 px-2' },
  { label: 'POS', className: 'py-2 px-2 w-14' },
  { label: 'AGE', className: 'py-2 px-2 w-12' },
  { label: 'TEAM', className: 'py-2 px-2 w-14' },
  { label: 'FPAR', className: 'py-2 px-2 w-16 text-right' },
  { label: 'DYNASTY', className: 'py-2 pl-2 pr-4 w-20 text-right' },
]

const POS_FILTER = ['ALL', 'QB', 'RB', 'WR', 'TE'] as const
type Filter = (typeof POS_FILTER)[number]

function PlayerRow({
  rank,
  player,
  index,
}: {
  rank: number
  player: DraftPlayer
  index: number
}) {
  const color = POS_COLOR[player.position] ?? '#6a8098'

  return (
    <motion.tr
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.014 }}
    >
      <td className="py-2.5 pl-3 pr-2" style={{ color: '#3d5070', fontSize: 12, fontFamily: "'DM Mono', monospace" }}>
        {rank}
      </td>
      <td className="py-2.5 px-2" style={{ borderLeft: `2px solid ${color}` }}>
        <span className="font-medium" style={{ fontSize: 13, color: '#e8eef6' }}>
          {player.name}
        </span>
        {player.is_rookie && (
          <span
            className="ml-2 tracking-wider uppercase"
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: '2px 5px',
              color: '#c8820a',
              background: 'rgba(200, 130, 10, 0.12)',
              border: '1px solid rgba(200, 130, 10, 0.3)',
              borderRadius: 1,
            }}
          >
            ROOK
          </span>
        )}
      </td>
      <td className="py-2.5 px-2">
        <span
          className="tracking-widest font-bold"
          style={{
            fontSize: 11,
            padding: '2px 6px',
            color,
            background: `${color}18`,
            borderRadius: 1,
          }}
        >
          {player.position}
        </span>
      </td>
      <td
        className="py-2.5 px-2 tabular-nums"
        style={{ fontSize: 13, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}
      >
        {player.age.toFixed(0)}
      </td>
      <td className="py-2.5 px-2" style={{ fontSize: 12, color: '#3d5070' }}>
        {player.team || 'FA'}
      </td>
      <td
        className="py-2.5 px-2 text-right tabular-nums"
        style={{ fontSize: 13, color: '#1a9b5e', fontFamily: "'DM Mono', monospace" }}
      >
        {player.fpar.toFixed(1)}
      </td>
      <td
        className="py-2.5 pl-2 pr-4 text-right tabular-nums"
        style={{ fontSize: 13, color: '#d4860c', fontFamily: "'DM Mono', monospace" }}
      >
        {player.dynasty_value.toFixed(1)}
      </td>
    </motion.tr>
  )
}

function PickTimeline({
  current,
  total,
  mySlot,
  picksUntil,
  currentRound,
}: {
  current: number
  total: number
  mySlot: number
  picksUntil: number
  currentRound: number
}) {
  const pct = Math.min(100, ((current - 1) / total) * 100)
  const isMyTurn = picksUntil === 0

  return (
    <div>
      {isMyTurn && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="px-5 py-3 flex items-center justify-between"
          style={{ background: 'rgba(201, 51, 40, 0.06)', borderBottom: '2px solid #c93328' }}
        >
          <div className="flex items-center gap-3">
            <span
              className="war-pulse font-black tracking-widest uppercase"
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontSize: 20,
                color: '#c93328',
              }}
            >
              ◉ ON THE CLOCK
            </span>
            <span
              className="tracking-[0.2em] uppercase"
              style={{ fontSize: 11, color: 'rgba(201, 51, 40, 0.6)' }}
            >
              PICK #{current} · RD {currentRound} · SLOT {mySlot}
            </span>
          </div>
          <span
            className="tracking-widest uppercase"
            style={{ fontSize: 11, color: 'rgba(201, 51, 40, 0.5)' }}
          >
            REVIEW BOARD · DRAFT IN SLEEPER
          </span>
        </motion.div>
      )}

      <div className="px-5 py-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-baseline gap-3">
            <span
              className="leading-none font-bold"
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontSize: 28,
                color: '#e8eef6',
              }}
            >
              PICK {current}
            </span>
            <span style={{ fontSize: 13, color: '#3d5070' }}>
              of {total} · Round {currentRound} · Slot {mySlot}
            </span>
          </div>
          {!isMyTurn && (
            <span style={{ fontSize: 13, color: '#6a8098' }}>
              <span
                style={{ fontFamily: "'DM Mono', monospace", fontWeight: 700, color: '#e8eef6' }}
              >
                {picksUntil}
              </span>{' '}
              {picksUntil === 1 ? 'pick' : 'picks'} until your turn
            </span>
          )}
        </div>
        <div
          className="relative overflow-hidden"
          style={{ height: 3, background: '#162035', borderRadius: 1 }}
        >
          <motion.div
            className="h-full"
            style={{
              background: isMyTurn ? '#c93328' : '#00b8cc',
              borderRadius: 1,
            }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        </div>
      </div>
    </div>
  )
}

export function DraftBoard() {
  const [filter, setFilter] = useState<Filter>('ALL')
  const [sortBy, setSortBy] = useState<'fpar' | 'dynasty_value' | 'age'>('dynasty_value')

  const { data, isLoading, error } = useQuery({
    queryKey: ['draft-board'],
    queryFn: () => api.draftBoard(60),
    refetchInterval: 15_000,
  })

  const players = (data?.players ?? [])
    .filter((p) => filter === 'ALL' || p.position === filter)
    .sort((a: DraftPlayer, b: DraftPlayer) =>
      sortBy === 'age' ? a[sortBy] - b[sortBy] : b[sortBy] - a[sortBy],
    )

  return (
    <div>
      {/* Header */}
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
            DRAFT BOARD
          </h1>
          <span
            className="tracking-[0.3em] uppercase"
            style={{ fontSize: 11, color: '#6a8098' }}
          >
            DYNASTY ROOKIE DRAFT · 4 ROUNDS · SYNCS 15S
          </span>
        </div>
      </div>

      {isLoading && (
        <div className="p-8 text-center tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>
          LOADING BOARD…
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
        <>
          {data.status === 'complete' ? (
            <div className="p-10 text-center">
              <span
                className="tracking-widest uppercase"
                style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontSize: 24,
                  fontWeight: 700,
                  color: '#6a8098',
                }}
              >
                DRAFT COMPLETE
              </span>
            </div>
          ) : (
            <PickTimeline
              current={data.current_pick}
              total={data.total_picks}
              mySlot={data.my_slot}
              picksUntil={data.picks_until_my_turn}
              currentRound={data.current_round}
            />
          )}

          {/* Controls */}
          <div
            className="flex items-center gap-3 px-5 py-3"
            style={{ borderBottom: '1px solid #162035', background: '#09111f' }}
          >
            <div className="flex gap-1">
              {POS_FILTER.map((pos) => (
                <button
                  key={pos}
                  onClick={() => setFilter(pos)}
                  className="tracking-widest uppercase font-bold transition-all"
                  style={{
                    fontSize: 11,
                    padding: '5px 12px',
                    background: filter === pos ? '#00b8cc' : 'transparent',
                    color: filter === pos ? '#060a12' : '#6a8098',
                    border: `1px solid ${filter === pos ? '#00b8cc' : '#162035'}`,
                    borderRadius: 2,
                    cursor: 'pointer',
                  }}
                >
                  {pos}
                </button>
              ))}
            </div>
            <div className="ml-auto flex gap-1">
              {(
                [
                  { key: 'dynasty_value', label: 'DYNASTY' },
                  { key: 'fpar', label: 'FPAR' },
                  { key: 'age', label: 'AGE' },
                ] as const
              ).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setSortBy(key)}
                  className="tracking-widest uppercase font-semibold transition-all"
                  style={{
                    fontSize: 10,
                    padding: '5px 10px',
                    background: sortBy === key ? '#111f30' : 'transparent',
                    color: sortBy === key ? '#e8eef6' : '#3d5070',
                    border: `1px solid ${sortBy === key ? '#3a7cc0' : '#162035'}`,
                    borderRadius: 2,
                    cursor: 'pointer',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Board table */}
          <div style={{ overflowX: 'auto' }}>
            <table className="w-full text-left war-table">
              <thead>
                <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
                  {TABLE_COLS.map(({ label, className }) => (
                    <th
                      key={label}
                      className={className}
                      style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.25em' }}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {players.map((p, i) => (
                    <PlayerRow key={p.player_id} rank={i + 1} player={p} index={i} />
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {players.length === 0 && !isLoading && (
              <div
                className="py-10 text-center tracking-widest uppercase"
                style={{ color: '#3d5070', fontSize: 12 }}
              >
                NO PLAYERS FOUND
              </div>
            )}
          </div>

          <div
            className="px-5 py-3 tracking-wider uppercase"
            style={{ borderTop: '1px solid #162035', fontSize: 10, color: '#2d4060' }}
          >
            FPAR = FANTASY PTS ABOVE REPLACEMENT · DYNASTY = AGE-CURVE ADJUSTED · ROOKIES VIA SLEEPER SEARCH RANK
          </div>
        </>
      )}
    </div>
  )
}
