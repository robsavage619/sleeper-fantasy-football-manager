import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'

const POS_COLOR: Record<string, string> = { QB: '#e05030', RB: '#24a870', WR: '#3a8cd4', TE: '#c8820a' }

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline gap-3 px-5 pt-6 pb-2">
      <h2 className="uppercase tracking-wide leading-none" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 22, fontWeight: 800, color: '#e8eef6' }}>{children}</h2>
      {sub && <span className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>{sub}</span>}
    </div>
  )
}

function PosTag({ position }: { position: string }) {
  const c = POS_COLOR[position] ?? '#6a8098'
  return <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', padding: '1px 5px', color: c, background: `${c}18`, borderRadius: 1 }}>{position}</span>
}

function sosColor(idx: number): string {
  if (idx >= 1.06) return '#24a870' // soft = good
  if (idx <= 0.94) return '#c93328' // tough
  return '#6a8098'
}

export function Matchups() {
  const gameday = useQuery({ queryKey: ['gameday'], queryFn: () => api.gameday(1) })
  const myRoster = useQuery({ queryKey: ['my-roster'], queryFn: () => api.myRoster() })
  const env = useQuery({ queryKey: ['environment-flags'], queryFn: api.environmentFlags })
  const sched = useQuery({ queryKey: ['schedule-strength'], queryFn: () => api.scheduleStrength() })
  const wire = useQuery({ queryKey: ['wire-watch'], queryFn: () => api.wireWatch(true) })
  const handcuffs = useQuery({ queryKey: ['handcuffs'], queryFn: api.handcuffs })

  const myIds = new Set((myRoster.data?.players ?? []).map((p) => p.player_id))
  const myFlagged = (env.data?.flagged ?? []).filter((p) => myIds.has(p.player_id))

  // SoS for my rostered players, keyed by team|pos.
  const sosMap = new Map<string, number>()
  for (const s of sched.data?.sos ?? []) sosMap.set(`${s.team}|${s.position}`, s.playoff_index)
  const mySos = (myRoster.data?.players ?? [])
    .map((p) => ({ p, idx: sosMap.get(`${p.team}|${p.position}`) }))
    .filter((r): r is { p: (typeof r)['p']; idx: number } => typeof r.idx === 'number')
    .sort((a, b) => b.idx - a.idx)

  const g = gameday.data
  const wp = g?.win_probability ?? 0.5

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 40, fontWeight: 800, color: '#e8eef6' }}>MATCHUP LAB</h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: '#6a8098' }}>WIN PROBABILITY · WEATHER · SCHEDULE · WIRE</span>
        </div>
      </div>

      {/* Gameday */}
      <SectionTitle sub={g?.has_matchup ? `week ${g.week}` : 'off-season'}>Gameday</SectionTitle>
      <div className="px-5 pb-2">
        {g?.has_matchup ? (
          <div className="flex flex-wrap items-center gap-8">
            <div>
              <div className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>WIN PROBABILITY</div>
              <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 48, fontWeight: 800, lineHeight: 1, color: wp >= 0.5 ? '#24a870' : '#c93328' }}>{pct(wp)}</div>
            </div>
            <div style={{ flex: 1, minWidth: 260, maxWidth: 460 }}>
              <div style={{ height: 10, background: '#0e1526', borderRadius: 2, overflow: 'hidden' }}>
                <motion.div style={{ height: '100%', background: wp >= 0.5 ? '#24a870' : '#c93328' }} initial={{ width: 0 }} animate={{ width: `${wp * 100}%` }} transition={{ duration: 0.5 }} />
              </div>
              <div className="flex justify-between mt-1" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>
                <span>ME {g.my_projected.toFixed(0)}</span>
                <span>{g.opponent_projected.toFixed(0)} OPP (R{g.opponent_roster_id})</span>
              </div>
            </div>
            {g.lineup_upside > 0 && (
              <div>
                <div className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#d4860c' }}>LINEUP UPSIDE</div>
                <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 32, fontWeight: 800, color: '#d4860c', lineHeight: 1 }}>+{g.lineup_upside.toFixed(1)}</div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ color: '#6a8098', fontSize: 13 }}>{g?.note ?? 'No live matchup.'}</div>
        )}
        {gameday.isLoading && <Loading label="COMPUTING WIN PROBABILITY…" />}
      </div>

      {/* Weather / stadium leans */}
      <SectionTitle sub="my roster · historical splits">Stadium &amp; Weather Leans</SectionTitle>
      <div className="px-5 pb-2">
        {myFlagged.length === 0 && !env.isLoading && <Empty>No material venue/weather leans on the roster.</Empty>}
        {myFlagged.map((p, i) => (
          <motion.div key={p.player_id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }} className="flex items-center gap-3 py-1.5" style={{ borderBottom: '1px solid #0e1526' }}>
            <PosTag position={p.position} />
            <span style={{ fontSize: 13, color: '#e8eef6', width: 150 }}>{p.name}</span>
            <span style={{ fontSize: 12, color: '#8a9ab0' }}>{p.flags.join(' · ')}</span>
          </motion.div>
        ))}
        {env.isLoading && <Loading label="LOADING SPLITS…" />}
      </div>

      {/* Playoff SoS */}
      <SectionTitle sub={sched.data ? `DvP ${sched.data.dvp_season} → ${sched.data.schedule_season} sched` : 'weeks 15-17'}>Playoff Schedule Outlook</SectionTitle>
      <div className="px-5 pb-2">
        {mySos.length === 0 && !sched.isLoading && (
          <Empty>{sched.data?.warnings?.[0] ?? 'Schedule not yet published for the upcoming season.'}</Empty>
        )}
        {mySos.map(({ p, idx }, i) => (
          <motion.div key={p.player_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.015 }} className="flex items-center gap-3 py-1">
            <PosTag position={p.position} />
            <span style={{ fontSize: 13, color: '#e8eef6', width: 150 }}>{p.name}</span>
            <span style={{ fontSize: 11, color: '#6a8098', width: 40 }}>{p.team}</span>
            <div style={{ flex: 1, height: 5, background: '#0e1526', borderRadius: 1, overflow: 'hidden', maxWidth: 260 }}>
              <motion.div style={{ height: '100%', background: sosColor(idx) }} initial={{ width: 0 }} animate={{ width: `${Math.min(100, idx * 55)}%` }} transition={{ duration: 0.4 }} />
            </div>
            <span className="tabular-nums" style={{ fontSize: 12, color: sosColor(idx), fontFamily: "'DM Mono', monospace", width: 44, textAlign: 'right' }}>{idx.toFixed(2)}</span>
          </motion.div>
        ))}
        {sched.isLoading && <Loading label="GRADING DEFENSES…" />}
      </div>

      {/* Wire early-warning + Handcuffs */}
      <div className="grid gap-px" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
        <div style={{ background: '#060a12' }}>
          <SectionTitle sub="snap-share risers, available">Wire Early-Warning</SectionTitle>
          <div className="px-5 pb-4">
            {(wire.data?.alerts ?? []).length === 0 && !wire.isLoading && <Empty>No available risers cleared the bar.</Empty>}
            {(wire.data?.alerts ?? []).slice(0, 12).map((a, i) => (
              <motion.div key={a.player_id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }} className="flex items-center gap-2 py-1.5" style={{ borderBottom: '1px solid #0e1526' }}>
                <PosTag position={a.position} />
                <span style={{ fontSize: 13, color: '#e8eef6', width: 140 }}>{a.name}</span>
                <span style={{ fontSize: 11, color: '#24a870', fontFamily: "'DM Mono', monospace" }}>{a.note}</span>
              </motion.div>
            ))}
            {wire.isLoading && <Loading label="SCANNING SNAPS…" />}
          </div>
        </div>
        <div style={{ background: '#060a12' }}>
          <SectionTitle sub="contingent value">Handcuffs &amp; Leverage</SectionTitle>
          <div className="px-5 pb-4">
            <div className="tracking-[0.15em] uppercase" style={{ fontSize: 10, color: '#c93328', paddingBottom: 4 }}>EXPOSED STARTERS</div>
            {(handcuffs.data?.exposed ?? []).length === 0 && !handcuffs.isLoading && <Empty>Contingent value secured.</Empty>}
            {(handcuffs.data?.exposed ?? []).slice(0, 6).map((h) => (
              <div key={h.starter_id} className="flex items-center gap-2 py-1" style={{ fontSize: 12 }}>
                <PosTag position={h.position} />
                <span style={{ color: '#e8eef6', width: 130 }}>{h.starter_name}</span>
                <span style={{ color: '#6a8098' }}>→ {h.backup_name ?? 'no backup'} [{h.backup_owner}]</span>
              </div>
            ))}
            <div className="tracking-[0.15em] uppercase" style={{ fontSize: 10, color: '#00b8cc', padding: '10px 0 4px' }}>LEVERAGE STASHES</div>
            {(handcuffs.data?.leverage_stashes ?? []).slice(0, 6).map((s) => (
              <div key={s.backup_id} className="flex items-center gap-2 py-1" style={{ fontSize: 12 }}>
                <PosTag position={s.position} />
                <span style={{ color: '#e8eef6', width: 130 }}>{s.backup_name}</span>
                <span style={{ color: '#6a8098' }}>behind {s.starter_name}</span>
              </div>
            ))}
            {handcuffs.isLoading && <Loading label="MAPPING DEPTH CHARTS…" />}
          </div>
        </div>
      </div>
      <div style={{ height: 24 }} />
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div style={{ color: '#3d5070', fontSize: 12, padding: '6px 0' }}>{children}</div>
}

function Loading({ label }: { label: string }) {
  return <div className="py-4 text-center tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>{label}</div>
}
