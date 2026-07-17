import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { MispricingEntry, RegressionFlag } from '@/lib/api'
import { InfoTip } from '@/components/viz'
import { GLOSSARY } from '@/lib/glossary'

const EDGE_COL_INFO: Record<string, string> = {
  EDGE: GLOSSARY.edgePct,
  'MKT VAL': GLOSSARY.leverage,
  'VALUE GAP': GLOSSARY.valueGap,
}
const REG_COL_INFO: Record<string, string> = {
  'TD±': GLOSSARY.tdOverExpected,
}
const CONTENTION_COL_INFO: Record<string, string> = {
  PLAYOFF: GLOSSARY.titleOdds,
}

const POS_COLOR: Record<string, string> = { QB: '#e05030', RB: '#24a870', WR: '#3a8cd4', TE: '#c8820a' }
const LABEL_COLOR: Record<string, string> = {
  'WIN-NOW': '#e0a030',
  SUSTAIN: '#24a870',
  RETOOL: '#3a8cd4',
  REBUILD: '#8a94a6',
  HOLD: '#6a8098',
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline gap-3 px-5 pt-6 pb-2">
      <h2
        className="uppercase tracking-wide leading-none"
        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 22, fontWeight: 800, color: '#e8eef6' }}
      >
        {children}
      </h2>
      {sub && <span className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>{sub}</span>}
    </div>
  )
}

function PosTag({ position }: { position: string }) {
  const c = POS_COLOR[position] ?? '#6a8098'
  return (
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', padding: '1px 5px', color: c, background: `${c}18`, borderRadius: 1 }}>
      {position}
    </span>
  )
}

function EdgeTable({ rows, tone }: { rows: MispricingEntry[]; tone: 'buy' | 'sell' }) {
  const color = tone === 'buy' ? '#24a870' : '#c93328'
  if (rows.length === 0)
    return <div className="px-5 py-4" style={{ color: '#3d5070', fontSize: 12 }}>No {tone === 'buy' ? 'buy' : 'sell'} edges this cycle.</div>
  return (
    <table className="w-full text-left war-table">
      <thead>
        <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
          {['PLAYER', 'POS', 'TEAM', 'EDGE', 'MKT VAL', 'VALUE GAP'].map((h) => (
            <th key={h} className="py-2 px-3" style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
              {h}
              {EDGE_COL_INFO[h] && <InfoTip text={EDGE_COL_INFO[h]} label={h} />}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((e, i) => (
          <motion.tr key={e.player_id + i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
            <td className="py-2 px-3" style={{ borderLeft: `2px solid ${color}`, fontSize: 13, color: '#e8eef6' }}>{e.name}</td>
            <td className="py-2 px-3"><PosTag position={e.position} /></td>
            <td className="py-2 px-3" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{e.team}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>
              {e.edge_pct > 0 ? '+' : ''}{e.edge_pct.toFixed(1)}%
            </td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{e.market_value != null ? e.market_value.toFixed(0) : '—'}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: e.value_gap != null ? color : '#3d5070', fontFamily: "'DM Mono', monospace" }}>
              {e.value_gap != null ? `${e.value_gap > 0 ? '+' : ''}${e.value_gap.toFixed(0)}` : '—'}
            </td>
          </motion.tr>
        ))}
      </tbody>
    </table>
  )
}

function RegTable({ rows, tone }: { rows: RegressionFlag[]; tone: 'buy' | 'sell' }) {
  const color = tone === 'buy' ? '#24a870' : '#c93328'
  if (rows.length === 0)
    return <div className="px-5 py-4" style={{ color: '#3d5070', fontSize: 12 }}>Nothing flagged.</div>
  return (
    <table className="w-full text-left war-table">
      <thead>
        <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
          {['PLAYER', 'POS', 'TDs', 'xTD', 'TD±'].map((h) => (
            <th key={h} className="py-2 px-3" style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.2em' }}>
              {h}
              {REG_COL_INFO[h] && <InfoTip text={REG_COL_INFO[h]} label={h} />}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((f, i) => (
          <motion.tr key={f.player_id + i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
            <td className="py-2 px-3" style={{ borderLeft: `2px solid ${color}`, fontSize: 13, color: '#e8eef6' }}>{f.name}</td>
            <td className="py-2 px-3"><PosTag position={f.position} /></td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{f.total_tds.toFixed(0)}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{f.expected_tds.toFixed(1)}</td>
            <td className="py-2 px-3 tabular-nums" style={{ fontSize: 13, color, fontFamily: "'DM Mono', monospace", fontWeight: 600 }}>{f.td_oe > 0 ? '+' : ''}{f.td_oe.toFixed(1)}</td>
          </motion.tr>
        ))}
      </tbody>
    </table>
  )
}

export function Edges() {
  const mispricing = useQuery({ queryKey: ['mispricing'], queryFn: () => api.mispricing(12) })
  const sim = useQuery({ queryKey: ['season-sim'], queryFn: () => api.seasonSim(3000) })
  const contention = useQuery({ queryKey: ['contention'], queryFn: api.contention })
  const regression = useQuery({ queryKey: ['regression'], queryFn: () => api.regression(10) })
  const owners = useQuery({ queryKey: ['owner-profiles'], queryFn: api.ownerProfiles, staleTime: 5 * 60 * 1000 })

  const nameByRoster = new Map<number, string>()
  for (const o of owners.data ?? []) nameByRoster.set(o.roster_id, o.display_name || `Roster ${o.roster_id}`)
  const rosterName = (id: number) => nameByRoster.get(id) ?? `Roster ${id}`

  const me = sim.data?.teams.find((t) => t.is_me)
  const maxTitle = Math.max(0.01, ...(sim.data?.teams ?? []).map((t) => t.title_odds))

  return (
    <div>
      <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid #162035' }}>
        <div className="flex items-baseline gap-4">
          <h1 className="leading-none uppercase tracking-wide" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 40, fontWeight: 800, color: '#e8eef6' }}>
            MARKET EDGES
          </h1>
          <span className="tracking-[0.3em] uppercase" style={{ fontSize: 11, color: '#6a8098' }}>
            SCORING-LEVERAGE · TITLE EQUITY · REGRESSION
          </span>
        </div>
      </div>

      {/* Title equity */}
      <SectionTitle sub={sim.data ? `${sim.data.schedule_source} · ${sim.data.n_sims} sims` : ''}>Title Equity</SectionTitle>
      {me && (
        <div className="px-5 pb-2 flex flex-wrap gap-6">
          <Stat label="MY TITLE ODDS" value={pct(me.title_odds)} accent="#00b8cc" info={GLOSSARY.titleOdds} />
          <Stat label="MY PLAYOFF ODDS" value={pct(me.playoff_odds)} accent="#24a870" info={GLOSSARY.titleOdds} />
          <Stat label="PROJ WINS" value={me.avg_wins.toFixed(1)} accent="#6a8098" />
          <Stat label="STRENGTH/WK" value={me.strength.toFixed(0)} accent="#6a8098" info={GLOSSARY.leverage} />
        </div>
      )}
      <div className="px-5 pb-3">
        {(sim.data?.teams ?? []).map((t, i) => (
          <div key={t.roster_id} className="flex items-center gap-3 py-1">
            <span style={{ width: 150, fontSize: 12, color: t.is_me ? '#00b8cc' : '#b8c6d8', fontWeight: t.is_me ? 600 : 400, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {i + 1}. {rosterName(t.roster_id)}{t.is_me ? ' ◆' : ''}
            </span>
            <div style={{ flex: 1, height: 6, background: '#0e1526', borderRadius: 1, overflow: 'hidden', maxWidth: 360 }}>
              <motion.div style={{ height: '100%', background: t.is_me ? '#00b8cc' : '#2d4a6a', borderRadius: 1 }} initial={{ width: 0 }} animate={{ width: `${(t.title_odds / maxTitle) * 100}%` }} transition={{ duration: 0.5 }} />
            </div>
            <span className="tabular-nums" style={{ width: 48, fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace", textAlign: 'right' }}>{pct(t.title_odds)}</span>
          </div>
        ))}
        {sim.isLoading && <Loading label="SIMULATING SEASON…" />}
      </div>

      {/* Contention windows */}
      <SectionTitle sub="buyer / seller classifier">Contention Windows</SectionTitle>
      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-left war-table">
          <thead>
            <tr style={{ background: '#09111f', borderBottom: '1px solid #162035' }}>
              {['TEAM', 'WINDOW', 'PLAYOFF', 'CORE AGE', 'YOUTH', 'WANTS', 'SHOULD MOVE'].map((h) => (
                <th key={h} className="py-2 px-3" style={{ color: '#3d5070', fontSize: 10, fontWeight: 600, letterSpacing: '0.2em', whiteSpace: 'nowrap' }}>
                  {h}
                  {CONTENTION_COL_INFO[h] && <InfoTip text={CONTENTION_COL_INFO[h]} label={h} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(contention.data?.windows ?? []).map((w, i) => (
              <motion.tr key={w.roster_id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}>
                <td className="py-2 px-3" style={{ fontSize: 13, color: w.is_me ? '#00b8cc' : '#e8eef6', fontWeight: w.is_me ? 600 : 400, whiteSpace: 'nowrap' }}>{rosterName(w.roster_id)}{w.is_me ? ' ◆' : ''}</td>
                <td className="py-2 px-3">
                  <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 7px', color: LABEL_COLOR[w.label], background: `${LABEL_COLOR[w.label]}18`, borderRadius: 1, whiteSpace: 'nowrap' }}>{w.label}</span>
                </td>
                <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{pct(w.playoff_odds)}</td>
                <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{w.core_age.toFixed(1)}</td>
                <td className="py-2 px-3 tabular-nums" style={{ fontSize: 12, color: '#6a8098', fontFamily: "'DM Mono', monospace" }}>{pct(w.young_share)}</td>
                <td className="py-2 px-3" style={{ fontSize: 11, color: '#8a9ab0', maxWidth: 200 }}>{w.seeking}</td>
                <td className="py-2 px-3" style={{ fontSize: 11, color: '#8a9ab0', maxWidth: 200 }}>{w.shedding}</td>
              </motion.tr>
            ))}
          </tbody>
        </table>
        {contention.isLoading && <Loading label="CLASSIFYING WINDOWS…" />}
      </div>

      {/* Mispricing */}
      <SectionTitle sub={mispricing.data ? mispricing.data.calibration : 'our scoring vs generic PPR'}>League-Specific Mispricing</SectionTitle>
      <div className="grid gap-px" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#24a870">BUY — market cheap for us</ColHead>
          <EdgeTable rows={mispricing.data?.buys ?? []} tone="buy" />
        </div>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#c93328">SELL — market overpays</ColHead>
          <EdgeTable rows={mispricing.data?.sells ?? []} tone="sell" />
        </div>
      </div>
      {mispricing.isLoading && <Loading label="RE-SCORING UNDER LEAGUE RULES…" />}
      {mispricing.data?.market_source === 'none' && (
        <div className="px-5 py-2" style={{ color: '#d4860c', fontSize: 11 }}>Market feed down — edges shown without market value.</div>
      )}

      {/* Regression */}
      <SectionTitle sub="TD-over-expected">Regression Watch</SectionTitle>
      <div className="grid gap-px pb-8" style={{ gridTemplateColumns: '1fr 1fr', background: '#162035' }}>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#c93328">SELL-HIGH — rode TD variance up</ColHead>
          <RegTable rows={regression.data?.sell_high ?? []} tone="sell" />
        </div>
        <div style={{ background: '#060a12' }}>
          <ColHead color="#24a870">BUY-LOW — unlucky on real usage</ColHead>
          <RegTable rows={regression.data?.buy_low ?? []} tone="buy" />
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, accent, info }: { label: string; value: string; accent: string; info?: string }) {
  return (
    <div>
      <div className="tracking-[0.2em] uppercase" style={{ fontSize: 10, color: '#3d5070' }}>
        {label}
        {info && <InfoTip text={info} label={label} />}
      </div>
      <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 34, fontWeight: 800, color: accent, lineHeight: 1 }}>{value}</div>
    </div>
  )
}

function ColHead({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <div className="px-3 py-2 tracking-[0.15em] uppercase" style={{ fontSize: 10, fontWeight: 700, color, borderBottom: `1px solid ${color}30` }}>{children}</div>
  )
}

function Loading({ label }: { label: string }) {
  return <div className="py-6 text-center tracking-widest uppercase" style={{ color: '#3d5070', fontSize: 12 }}>{label}</div>
}
