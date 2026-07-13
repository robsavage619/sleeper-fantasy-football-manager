import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { DossierPick, OwnerProfile, TradeAnalysis } from '@/lib/api'

const MY_ROSTER_ID = 2
const CURRENT_YEAR = new Date().getFullYear()

const C = {
  bg: '#060a12',
  card: '#0c1625',
  border: '#162035',
  text: '#e8eef6',
  muted: '#6a8098',
  cyan: '#00b8cc',
  amber: '#d4860c',
  green: '#1a9b5e',
  red: '#c93328',
}

const POS_COLORS: Record<string, string> = {
  QB: '#e05030', RB: '#24a870', WR: '#3a8cd4', TE: '#c8820a',
}

const ARCHETYPE_COLORS: Record<string, string> = {
  REBUILDER: '#c93328', CONTENDER: '#1a9b5e', BALANCED: '#00b8cc', UNKNOWN: '#6a8098',
}

const POS_ORDER = ['QB', 'RB', 'WR', 'TE']
const ROUNDS = [1, 2, 3, 4]
const FUTURE_SEASONS = [String(CURRENT_YEAR), String(CURRENT_YEAR + 1)]
const ORDINALS = ['1st', '2nd', '3rd', '4th']
const ordinal = (n: number) => ORDINALS[n - 1] ?? `${n}th`

const ROUND_BASE: Record<number, number> = { 1: 80, 2: 50, 3: 25, 4: 10 }
function pickValue(season: string | number, round: number): number {
  const yearsAhead = Math.max(0, Number(season) - CURRENT_YEAR)
  return Math.round((ROUND_BASE[round] ?? 5) * Math.pow(0.88, yearsAhead) * 10) / 10
}

function makePickId(season: string | number, round: number): string {
  return `${season}_${round}_1`
}

type PlayerSlot = {
  player_id: string
  name: string
  position: string
  age: number
  dynasty_value: number
}

type PickSlot = {
  id: string
  season: string
  round: number
  value: number
  source?: 'own' | 'acquired'
}

// ── helpers ──────────────────────────────────────────────────────────────────

function computeFitScore(profile: OwnerProfile, myProfile: OwnerProfile): number {
  let score = 50
  if (profile.archetype === 'REBUILDER') score += 15
  if (profile.picks_owned > myProfile.picks_owned) score += 10
  const complementaryPositions = POS_ORDER.filter((pos) => {
    const mine = (myProfile.positions[pos] ?? 0) as number
    const theirs = (profile.positions[pos] ?? 0) as number
    return Math.abs(mine - theirs) >= 2
  })
  if (complementaryPositions.length >= 1) score += 10
  if (complementaryPositions.length >= 2) score += 5
  return Math.min(score, 99)
}

function buildRationale(profile: OwnerProfile, myProfile: OwnerProfile): string {
  if (profile.picks_owned > myProfile.picks_owned) {
    return 'Has excess picks — might deal for proven talent'
  }
  if (profile.archetype === 'REBUILDER') {
    return 'Rebuilding — sell veterans while your window is open'
  }
  if (profile.archetype === 'CONTENDER') {
    return 'Window-open — may overpay for depth you can spare'
  }
  for (const pos of POS_ORDER) {
    const mine = (myProfile.positions[pos] ?? 0) as number
    const theirs = (profile.positions[pos] ?? 0) as number
    if (theirs === 0 && mine >= 2) {
      return `${pos}-needy — your depth at ${pos} could unlock a deal`
    }
    if (mine === 0 && theirs >= 2) {
      return `They stack ${pos} — potential swap for your positional gaps`
    }
  }
  return 'Positional overlap suggests room to negotiate'
}

// ── micro-components ─────────────────────────────────────────────────────────

function XBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: C.muted, fontSize: 16, padding: '0 2px', lineHeight: 1, flexShrink: 0,
      }}
    >
      ×
    </button>
  )
}

function OwnerAvatar({ avatar, name, size = 28 }: { avatar: string | null; name: string; size?: number }) {
  if (avatar) {
    return (
      <img
        src={`https://sleepercdn.com/avatars/thumbs/${avatar}`}
        alt={name}
        style={{ width: size, height: size, borderRadius: 2, objectFit: 'cover', border: `1px solid ${C.border}` }}
      />
    )
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: 2, background: C.card, border: `1px solid ${C.border}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: "'DM Mono', monospace", fontSize: size * 0.34, color: C.muted, flexShrink: 0,
    }}>
      {name.slice(0, 2).toUpperCase()}
    </div>
  )
}

// ── PlayerModal ───────────────────────────────────────────────────────────────

function PlayerModal({
  title,
  players,
  loading,
  onAdd,
  onClose,
}: {
  title: string
  players: PlayerSlot[]
  loading?: boolean
  onAdd: (p: PlayerSlot) => void
  onClose: () => void
}) {
  const [search, setSearch] = useState('')
  const filtered = players.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.position.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        style={{
          background: C.card, border: `1px solid ${C.border}`, borderRadius: 4,
          width: '100%', maxWidth: 460, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          padding: '14px 16px 10px', borderBottom: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
            fontSize: 18, color: C.cyan, letterSpacing: '0.06em',
          }}>
            {title}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: C.muted, cursor: 'pointer', fontSize: 20, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
          <input
            autoFocus
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by name or position…"
            style={{
              width: '100%', background: C.bg, border: `1px solid ${C.border}`,
              borderRadius: 2, padding: '7px 10px', color: C.text, fontSize: 13,
              fontFamily: "'DM Mono', monospace", outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: C.muted, fontSize: 12, padding: 24 }}>Loading roster…</div>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', color: C.muted, fontSize: 12, padding: 24 }}>No players found</div>
          ) : filtered.map(p => (
            <button
              key={p.player_id}
              onClick={() => { onAdd(p); onClose() }}
              style={{
                width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 10px', borderRadius: 2, textAlign: 'left',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = C.bg }}
              onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{
                  fontSize: 10, padding: '1px 4px', borderRadius: 1, minWidth: 24, textAlign: 'center',
                  background: (POS_COLORS[p.position] ?? C.muted) + '33',
                  color: POS_COLORS[p.position] ?? C.muted,
                  fontFamily: "'DM Mono', monospace",
                }}>
                  {p.position}
                </span>
                <span style={{ color: C.text, fontSize: 13 }}>{p.name}</span>
                <span style={{ color: C.muted, fontSize: 11 }}>age {Math.floor(p.age)}</span>
              </div>
              <span style={{ fontFamily: "'DM Mono', monospace", color: C.amber, fontSize: 12, flexShrink: 0 }}>
                {p.dynasty_value.toFixed(1)}
              </span>
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  )
}

// ── PickModal ─────────────────────────────────────────────────────────────────

function PickModal({
  mode,
  ownedPicks,
  onAdd,
  onClose,
}: {
  mode: 'give' | 'get'
  ownedPicks: DossierPick[]
  onAdd: (id: string, season: string, round: number) => void
  onClose: () => void
}) {
  const PICK_COLORS: Record<number, string> = { 1: C.amber, 2: C.cyan, 3: C.muted, 4: C.muted }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        style={{
          background: C.card, border: `1px solid ${C.border}`, borderRadius: 4,
          width: '100%', maxWidth: 360,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          padding: '14px 16px 10px', borderBottom: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{
            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
            fontSize: 18, color: C.amber, letterSpacing: '0.06em',
          }}>
            {mode === 'give' ? 'PICKS YOU OWN' : 'PICKS TO RECEIVE'}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: C.muted, cursor: 'pointer', fontSize: 20, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: 16 }}>
          {mode === 'give' ? (
            ownedPicks.length === 0 ? (
              <div style={{ color: C.muted, fontSize: 12, fontStyle: 'italic' }}>No picks available</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {ownedPicks.map(p => {
                  const id = makePickId(p.season, p.round)
                  const val = pickValue(p.season, p.round)
                  return (
                    <button
                      key={id}
                      onClick={() => { onAdd(id, p.season, p.round); onClose() }}
                      style={{
                        background: 'none', border: `1px solid ${C.border}`, borderRadius: 2,
                        cursor: 'pointer', padding: '8px 12px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', textAlign: 'left',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = C.bg }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                    >
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ color: C.text, fontFamily: "'DM Mono', monospace", fontSize: 13 }}>
                          {p.season} {ordinal(p.round)}
                        </span>
                        <span style={{
                          fontSize: 9, padding: '1px 4px', borderRadius: 1,
                          background: p.source !== 'acquired' ? C.amber + '22' : C.cyan + '22',
                          color: p.source !== 'acquired' ? C.amber : C.cyan,
                          fontFamily: "'DM Mono', monospace", letterSpacing: '0.04em',
                        }}>
                          {p.source !== 'acquired' ? 'OWN' : 'ACQ'}
                        </span>
                      </div>
                      <span style={{ fontFamily: "'DM Mono', monospace", color: C.amber, fontSize: 12 }}>
                        {val.toFixed(1)}
                      </span>
                    </button>
                  )
                })}
              </div>
            )
          ) : (
            <div>
              {FUTURE_SEASONS.map(season => (
                <div key={season} style={{ marginBottom: 14 }}>
                  <div style={{
                    color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginBottom: 8,
                    fontFamily: "'DM Mono', monospace",
                  }}>
                    {season}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                    {ROUNDS.map(round => {
                      const val = pickValue(season, round)
                      const id = makePickId(season, round)
                      const col = PICK_COLORS[round]
                      return (
                        <button
                          key={id}
                          onClick={() => { onAdd(id, season, round); onClose() }}
                          style={{
                            background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2,
                            cursor: 'pointer', padding: '8px 4px',
                            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                          }}
                          onMouseEnter={e => { e.currentTarget.style.borderColor = col }}
                          onMouseLeave={e => { e.currentTarget.style.borderColor = C.border }}
                        >
                          <span style={{ color: col, fontSize: 11, fontFamily: "'DM Mono', monospace" }}>
                            {ordinal(round)}
                          </span>
                          <span style={{ color: C.muted, fontSize: 9, fontFamily: "'DM Mono', monospace" }}>
                            {val.toFixed(0)}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}

// ── TradePanel ────────────────────────────────────────────────────────────────

function TradePanel({
  side,
  players,
  picks,
  onRemovePlayer,
  onRemovePick,
  onAddPlayer,
  onAddPick,
}: {
  side: 'GIVE' | 'GET'
  players: PlayerSlot[]
  picks: PickSlot[]
  onRemovePlayer: (id: string) => void
  onRemovePick: (id: string) => void
  onAddPlayer: () => void
  onAddPick: () => void
}) {
  const accent = side === 'GIVE' ? C.cyan : C.amber
  const totalValue = players.reduce((s, p) => s + p.dynasty_value, 0)
    + picks.reduce((s, p) => s + p.value, 0)
  const empty = players.length === 0 && picks.length === 0

  return (
    <div style={{
      background: C.card, borderRadius: 2, border: `1px solid ${C.border}`,
      boxShadow: `inset 3px 0 0 ${accent}`,
      padding: '14px 16px', flex: 1, minWidth: 0,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <span style={{
          fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
          fontSize: 22, color: accent, letterSpacing: '0.06em',
        }}>
          {side}
        </span>
        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 14, color: totalValue === 0 ? C.muted : accent }}>
          {totalValue.toFixed(1)}
        </span>
      </div>

      {empty ? (
        <div style={{
          border: `1px dashed ${C.border}`, borderRadius: 2,
          padding: '14px 10px', textAlign: 'center', color: C.muted, fontSize: 12, marginBottom: 10,
        }}>
          No assets added
        </div>
      ) : (
        <div style={{ marginBottom: 10 }}>
          {players.map(p => (
            <div key={p.player_id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '5px 0', borderBottom: `1px solid ${C.border}`,
            }}>
              <div style={{ display: 'flex', gap: 7, alignItems: 'center', flex: 1, minWidth: 0 }}>
                <span style={{
                  fontSize: 10, padding: '1px 4px', borderRadius: 1, flexShrink: 0,
                  background: (POS_COLORS[p.position] ?? C.muted) + '33',
                  color: POS_COLORS[p.position] ?? C.muted,
                  fontFamily: "'DM Mono', monospace",
                }}>
                  {p.position}
                </span>
                <span style={{ color: C.text, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.name}
                </span>
                <span style={{ color: C.muted, fontSize: 10, flexShrink: 0 }}>
                  {Math.floor(p.age)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                <span style={{ fontFamily: "'DM Mono', monospace", color: accent, fontSize: 11 }}>
                  {p.dynasty_value.toFixed(1)}
                </span>
                <XBtn onClick={() => onRemovePlayer(p.player_id)} />
              </div>
            </div>
          ))}
          {picks.map(pk => (
            <div key={pk.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '5px 0', borderBottom: `1px solid ${C.border}`,
            }}>
              <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
                <span style={{
                  fontSize: 10, padding: '1px 4px', borderRadius: 1,
                  background: C.border, color: C.muted, fontFamily: "'DM Mono', monospace",
                }}>
                  PICK
                </span>
                <span style={{ color: C.text, fontSize: 12 }}>
                  {pk.season} {ordinal(pk.round)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontFamily: "'DM Mono', monospace", color: accent, fontSize: 11 }}>
                  {pk.value.toFixed(1)}
                </span>
                <XBtn onClick={() => onRemovePick(pk.id)} />
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: empty ? 0 : 8 }}>
        <button
          onClick={onAddPlayer}
          style={{
            flex: 1, background: 'none', border: `1px solid ${accent}44`, borderRadius: 2,
            padding: '6px 0', color: accent, fontSize: 10, letterSpacing: '0.06em',
            cursor: 'pointer', fontFamily: "'DM Mono', monospace",
          }}
        >
          + PLAYER
        </button>
        <button
          onClick={onAddPick}
          style={{
            flex: 1, background: 'none', border: `1px solid ${C.border}`, borderRadius: 2,
            padding: '6px 0', color: C.muted, fontSize: 10, letterSpacing: '0.06em',
            cursor: 'pointer', fontFamily: "'DM Mono', monospace",
          }}
        >
          + PICK
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function Trades() {
  const [givePlayers, setGivePlayers] = useState<PlayerSlot[]>([])
  const [getPlayers, setGetPlayers] = useState<PlayerSlot[]>([])
  const [givePicks, setGivePicks] = useState<PickSlot[]>([])
  const [getPicks, setGetPicks] = useState<PickSlot[]>([])
  const [partnerId, setPartnerId] = useState<number | null>(null)
  const [playerModal, setPlayerModal] = useState<'give' | 'get' | null>(null)
  const [pickModal, setPickModal] = useState<'give' | 'get' | null>(null)
  const [analysis, setAnalysis] = useState<TradeAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [showPrompt, setShowPrompt] = useState(false)
  const [promptCopied, setPromptCopied] = useState(false)

  const { data: myRoster } = useQuery({ queryKey: ['my-roster'], queryFn: () => api.myRoster() })
  const { data: myDossier } = useQuery({
    queryKey: ['dossier', MY_ROSTER_ID],
    queryFn: () => api.ownerDossier(MY_ROSTER_ID),
    staleTime: 5 * 60 * 1000,
  })
  const { data: ownerProfiles } = useQuery({ queryKey: ['owner-profiles'], queryFn: api.ownerProfiles })
  const { data: partnerDossier, isLoading: partnerLoading } = useQuery({
    queryKey: ['dossier', partnerId],
    queryFn: () => api.ownerDossier(partnerId!),
    enabled: partnerId !== null,
    staleTime: 5 * 60 * 1000,
  })

  const myPlayers: PlayerSlot[] = useMemo(
    () => (myRoster?.players ?? []).map(p => ({
      player_id: p.player_id, name: p.name, position: p.position, age: p.age, dynasty_value: p.dynasty_value,
    })),
    [myRoster],
  )

  const partnerPlayers: PlayerSlot[] = useMemo(
    () => (partnerDossier?.players ?? []).map(p => ({
      player_id: p.player_id, name: p.name, position: p.position, age: p.age, dynasty_value: p.dynasty_value,
    })),
    [partnerDossier],
  )

  const myPicksOwned: DossierPick[] = myDossier?.picks_owned ?? []

  const hasGiveAssets = givePlayers.length > 0 || givePicks.length > 0
  const hasGetAssets = getPlayers.length > 0 || getPicks.length > 0
  const hasAssets = hasGiveAssets || hasGetAssets
  const canAnalyze = partnerId !== null && hasGiveAssets && hasGetAssets

  function addGivePlayer(p: PlayerSlot) {
    if (!givePlayers.find(x => x.player_id === p.player_id)) {
      setGivePlayers(prev => [...prev, p])
      setAnalysis(null)
    }
  }

  function addGetPlayer(p: PlayerSlot) {
    if (!getPlayers.find(x => x.player_id === p.player_id)) {
      setGetPlayers(prev => [...prev, p])
      setAnalysis(null)
    }
  }

  function addGivePick(id: string, season: string, round: number) {
    if (!givePicks.find(x => x.id === id)) {
      setGivePicks(prev => [...prev, { id, season, round, value: pickValue(season, round) }])
      setAnalysis(null)
    }
  }

  function addGetPick(id: string, season: string, round: number) {
    if (!getPicks.find(x => x.id === id)) {
      setGetPicks(prev => [...prev, { id, season, round, value: pickValue(season, round) }])
      setAnalysis(null)
    }
  }

  async function runAnalysis() {
    if (!canAnalyze) {
      setAnalyzeError('Select a trade partner and at least one asset on both sides.')
      return
    }
    setAnalyzing(true)
    setAnalyzeError(null)
    try {
      const result = await api.analyzeTrade({
        give_player_ids: givePlayers.map(p => p.player_id),
        get_player_ids: getPlayers.map(p => p.player_id),
        give_pick_ids: givePicks.map(p => p.id),
        get_pick_ids: getPicks.map(p => p.id),
      })
      setAnalysis(result)
      setShowPrompt(false)
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  function copyPrompt() {
    if (analysis?.prompt) {
      navigator.clipboard.writeText(analysis.prompt)
      setPromptCopied(true)
      setTimeout(() => setPromptCopied(false), 2000)
    }
  }

  const myProfile = ownerProfiles?.find(p => p.display_name === 'robsavage')
  const otherProfiles = ownerProfiles?.filter(p => p.roster_id !== myProfile?.roster_id) ?? []
  const partnerProfile = ownerProfiles?.find(p => p.roster_id === partnerId)

  type FitCandidate = { profile: OwnerProfile; score: number; rationale: string }
  const fitCandidates: FitCandidate[] = useMemo(() => {
    if (!ownerProfiles || !myProfile) return []
    return ownerProfiles
      .filter(p => p.roster_id !== myProfile.roster_id)
      .map(p => ({ profile: p, score: computeFitScore(p, myProfile), rationale: buildRationale(p, myProfile) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 5)
  }, [ownerProfiles, myProfile])

  const verdictColor = analysis
    ? analysis.verdict === 'ACCEPT' ? C.green
      : analysis.verdict === 'DECLINE' ? C.red
      : C.muted
    : C.muted

  // Player modal pool: GIVE = my roster, GET = selected partner's roster.
  const getModalPlayers = partnerId !== null ? partnerPlayers : []

  return (
    <div style={{ padding: '20px 24px' }}>
      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
        fontSize: 30, color: C.cyan, margin: 0, letterSpacing: '0.04em', lineHeight: 1,
      }}>
        TRADE ANALYZER
      </h1>
      <p style={{ color: C.muted, fontSize: 11, margin: '4px 0 20px', letterSpacing: '0.1em' }}>
        DYNASTY-AWARE · PLAYERS + PICKS · PICK-ACCUMULATION ARBITRAGE
      </p>

      {/* Trade partner selector */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14,
        padding: '10px 14px', background: C.card, border: `1px solid ${C.border}`, borderRadius: 2,
      }}>
        <span style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', whiteSpace: 'nowrap', fontFamily: "'DM Mono', monospace" }}>
          TRADE PARTNER
        </span>
        <select
          value={partnerId ?? ''}
          onChange={e => {
            const v = e.target.value
            setPartnerId(v ? Number(v) : null)
            setGetPlayers([])
          }}
          style={{
            flex: 1, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2,
            padding: '5px 8px', color: C.text, fontSize: 12,
            fontFamily: "'DM Mono', monospace", cursor: 'pointer', outline: 'none',
          }}
        >
          <option value="">Select partner to browse their roster…</option>
          {otherProfiles.map(p => (
            <option key={p.roster_id} value={p.roster_id}>
              {(p.display_name ?? `Roster ${p.roster_id}`).toUpperCase()} · {p.archetype}
            </option>
          ))}
        </select>
        {partnerProfile && (
          <span style={{
            fontSize: 9, padding: '2px 6px', borderRadius: 1, flexShrink: 0,
            background: (ARCHETYPE_COLORS[partnerProfile.archetype] ?? C.muted) + '22',
            color: ARCHETYPE_COLORS[partnerProfile.archetype] ?? C.muted,
            fontFamily: "'DM Mono', monospace", letterSpacing: '0.06em',
          }}>
            {partnerProfile.archetype}
          </span>
        )}
        {partnerLoading && (
          <span style={{ color: C.muted, fontSize: 10, fontFamily: "'DM Mono', monospace", flexShrink: 0 }}>
            loading…
          </span>
        )}
      </div>

      {/* GIVE / GET panels */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <TradePanel
          side="GIVE"
          players={givePlayers}
          picks={givePicks}
          onRemovePlayer={id => { setGivePlayers(p => p.filter(x => x.player_id !== id)); setAnalysis(null) }}
          onRemovePick={id => { setGivePicks(p => p.filter(x => x.id !== id)); setAnalysis(null) }}
          onAddPlayer={() => setPlayerModal('give')}
          onAddPick={() => setPickModal('give')}
        />
        <TradePanel
          side="GET"
          players={getPlayers}
          picks={getPicks}
          onRemovePlayer={id => { setGetPlayers(p => p.filter(x => x.player_id !== id)); setAnalysis(null) }}
          onRemovePick={id => { setGetPicks(p => p.filter(x => x.id !== id)); setAnalysis(null) }}
          onAddPlayer={() => {
            if (partnerId === null) {
              setAnalyzeError('Select a trade partner before adding GET players.')
              return
            }
            setPlayerModal('get')
          }}
          onAddPick={() => setPickModal('get')}
        />
      </div>

      {/* Action bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={runAnalysis}
          disabled={!canAnalyze || analyzing}
          style={{
            flex: 1, padding: '11px 0',
            background: canAnalyze && !analyzing ? C.cyan : C.border,
            border: 'none', borderRadius: 2,
            cursor: canAnalyze && !analyzing ? 'pointer' : 'default',
            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
            fontSize: 17, letterSpacing: '0.08em',
            color: canAnalyze && !analyzing ? C.bg : C.muted,
            transition: 'background 0.12s',
          }}
        >
          {analyzing ? 'ANALYZING…' : 'ANALYZE TRADE'}
        </button>
        {hasAssets && (
          <button
            onClick={() => {
              setGivePlayers([]); setGetPlayers([]); setGivePicks([]); setGetPicks([])
              setAnalysis(null); setAnalyzeError(null)
            }}
            style={{
              padding: '11px 16px', background: 'none', border: `1px solid ${C.border}`,
              borderRadius: 2, cursor: 'pointer', color: C.muted,
              fontSize: 10, letterSpacing: '0.06em', fontFamily: "'DM Mono', monospace",
            }}
          >
            CLEAR
          </button>
        )}
      </div>

      {/* Analysis result */}
      {(analysis || analyzeError) && (
        <div style={{
          background: C.card, border: `1px solid ${C.border}`,
          boxShadow: analysis ? `inset 3px 0 0 ${verdictColor}` : 'none',
          borderRadius: 2, padding: '14px 16px', marginBottom: 16,
        }}>
          {analyzeError ? (
            <div style={{ color: C.red, fontSize: 12, fontFamily: "'DM Mono', monospace" }}>{analyzeError}</div>
          ) : analysis && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 14, flexWrap: 'wrap' }}>
                <div style={{
                  fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
                  fontSize: 32, color: verdictColor, letterSpacing: '0.06em', lineHeight: 1,
                }}>
                  {analysis.verdict}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div>
                    <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginBottom: 2 }}>GIVE</div>
                    <div style={{ fontFamily: "'DM Mono', monospace", color: C.cyan, fontSize: 22, lineHeight: 1 }}>
                      {analysis.give_value.toFixed(1)}
                    </div>
                  </div>
                  <div style={{ color: C.border, fontSize: 18, lineHeight: 1 }}>→</div>
                  <div>
                    <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginBottom: 2 }}>GET</div>
                    <div style={{ fontFamily: "'DM Mono', monospace", color: C.amber, fontSize: 22, lineHeight: 1 }}>
                      {analysis.get_value.toFixed(1)}
                    </div>
                  </div>
                  <div style={{ paddingLeft: 14, borderLeft: `1px solid ${C.border}` }}>
                    <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginBottom: 2 }}>NET</div>
                    <div style={{
                      fontFamily: "'DM Mono', monospace", fontSize: 22, lineHeight: 1,
                      color: analysis.delta >= 0 ? C.green : C.red,
                    }}>
                      {analysis.delta >= 0 ? '+' : ''}{analysis.delta.toFixed(1)}
                    </div>
                  </div>
                </div>
              </div>
              {analysis.data_quality === 'DEGRADED' && analysis.warnings.length > 0 && (
                <div style={{
                  background: C.bg, border: `1px solid ${C.amber}55`,
                  borderLeft: `3px solid ${C.amber}`, borderRadius: 2,
                  color: C.amber, fontSize: 11, fontFamily: "'DM Mono', monospace",
                  padding: '8px 10px', marginBottom: 12,
                }}>
                  {analysis.warnings.join(' · ')}
                </div>
              )}

              <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 10, color: C.muted, letterSpacing: '0.08em', fontFamily: "'DM Mono', monospace" }}>
                    CLAUDE CODE PROMPT
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={copyPrompt}
                      style={{
                        background: 'none', border: `1px solid ${C.border}`, borderRadius: 2,
                        padding: '3px 10px', cursor: 'pointer',
                        color: promptCopied ? C.green : C.muted,
                        fontSize: 10, letterSpacing: '0.06em', fontFamily: "'DM Mono', monospace",
                      }}
                    >
                      {promptCopied ? 'COPIED' : 'COPY'}
                    </button>
                    <button
                      onClick={() => setShowPrompt(v => !v)}
                      style={{
                        background: 'none', border: `1px solid ${C.border}`, borderRadius: 2,
                        padding: '3px 10px', cursor: 'pointer', color: C.muted,
                        fontSize: 10, letterSpacing: '0.06em', fontFamily: "'DM Mono', monospace",
                      }}
                    >
                      {showPrompt ? 'HIDE' : 'SHOW'}
                    </button>
                  </div>
                </div>
                {showPrompt && (
                  <pre style={{
                    background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2,
                    padding: 12, margin: 0, fontSize: 10, color: C.muted,
                    overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    fontFamily: "'DM Mono', monospace", lineHeight: 1.6,
                    maxHeight: 320, overflowY: 'auto',
                  }}>
                    {analysis.prompt}
                  </pre>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Mutual Fit Scanner */}
      <div style={{
        background: C.card, border: `1px solid ${C.border}`,
        boxShadow: `inset 3px 0 0 ${C.amber}`,
        borderRadius: 2, padding: '14px 16px', marginBottom: 14,
      }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{
            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
            fontSize: 22, color: C.amber, letterSpacing: '0.04em',
          }}>
            MUTUAL FIT SCANNER
          </div>
          <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginTop: 2, fontFamily: "'DM Mono', monospace" }}>
            ROSTER COMPLEMENTARITY · ARCHETYPE ALIGNMENT · PICK SURPLUS
          </div>
        </div>

        {!ownerProfiles ? (
          <p style={{ color: C.muted, fontSize: 12, margin: 0, fontStyle: 'italic' }}>Loading owner profiles…</p>
        ) : !myProfile ? (
          <p style={{ color: C.muted, fontSize: 12, margin: 0, fontStyle: 'italic' }}>Could not locate your profile.</p>
        ) : fitCandidates.length === 0 ? (
          <p style={{ color: C.muted, fontSize: 12, margin: 0, fontStyle: 'italic' }}>No trade candidates found.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {fitCandidates.map((candidate, index) => {
              const p = candidate.profile
              const archetypeColor = ARCHETYPE_COLORS[p.archetype] ?? C.muted
              const sortedPositions = Object.entries(p.positions)
                .filter(([, count]) => (count as number) > 0)
                .sort(([a], [b]) => POS_ORDER.indexOf(a) - POS_ORDER.indexOf(b))

              return (
                <motion.div
                  key={p.roster_id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.18, delay: index * 0.06 }}
                  style={{
                    background: C.bg, border: `1px solid ${C.border}`,
                    boxShadow: `inset 3px 0 0 ${archetypeColor}`,
                    borderRadius: 2, padding: '10px 14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <OwnerAvatar avatar={p.avatar} name={p.display_name ?? 'Unknown'} size={30} />
                      <div>
                        <div style={{
                          fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700,
                          fontSize: 15, color: C.text, letterSpacing: '0.04em', lineHeight: 1.1,
                        }}>
                          {(p.display_name ?? 'Unknown').toUpperCase()}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 2 }}>
                          <span style={{
                            fontSize: 9, padding: '1px 5px', borderRadius: 1,
                            background: archetypeColor + '22', color: archetypeColor,
                            fontFamily: "'DM Mono', monospace", letterSpacing: '0.06em',
                          }}>
                            {p.archetype}
                          </span>
                          <span style={{ color: C.muted, fontSize: 10, fontFamily: "'DM Mono', monospace" }}>
                            {p.picks_owned}pk
                          </span>
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ color: C.muted, fontSize: 9, letterSpacing: '0.08em', fontFamily: "'DM Mono', monospace" }}>
                        MUTUAL FIT
                      </div>
                      <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 22, color: C.amber, lineHeight: 1 }}>
                        {candidate.score}
                      </div>
                    </div>
                  </div>

                  <div style={{ color: C.muted, fontSize: 11, fontStyle: 'italic', marginBottom: 8, paddingLeft: 40 }}>
                    {candidate.rationale}
                  </div>

                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', paddingLeft: 40 }}>
                    {sortedPositions.map(([pos, count]) => (
                      <span key={pos} style={{
                        fontSize: 10, padding: '1px 6px', borderRadius: 1,
                        background: (POS_COLORS[pos] ?? C.muted) + '22',
                        color: POS_COLORS[pos] ?? C.muted,
                        fontFamily: "'DM Mono', monospace", letterSpacing: '0.03em',
                      }}>
                        {pos} {count as number}
                      </span>
                    ))}
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>

      {/* Pick Inventory */}
      <div style={{
        background: C.card, border: `1px solid ${C.border}`,
        borderRadius: 2, padding: '14px 16px',
      }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{
            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
            fontSize: 22, color: C.amber, letterSpacing: '0.04em',
          }}>
            MY PICK INVENTORY
          </div>
          <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginTop: 2, fontFamily: "'DM Mono', monospace" }}>
            {myPicksOwned.length} TOTAL — OWN + ACQUIRED
          </div>
        </div>

        {myPicksOwned.length === 0 ? (
          <p style={{ color: C.muted, fontSize: 12, margin: 0 }}>
            {myDossier ? 'No picks in inventory.' : 'Loading…'}
          </p>
        ) : (
          <div>
            {['own', 'acquired'].map(group => {
              const picks = myPicksOwned.filter(p => group === 'own' ? p.source !== 'acquired' : p.source === 'acquired')
              if (picks.length === 0) return null
              return (
                <div key={group} style={{ marginBottom: 12 }}>
                  <div style={{
                    color: group === 'own' ? C.amber : C.cyan,
                    fontSize: 9, letterSpacing: '0.1em', marginBottom: 6,
                    fontFamily: "'DM Mono', monospace",
                  }}>
                    {group === 'own' ? 'OWN PICKS' : 'ACQUIRED'}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {picks.map((p, i) => (
                      <span key={i} style={{
                        fontSize: 11, padding: '3px 8px', borderRadius: 2,
                        border: `1px solid ${group === 'own' ? C.amber + '44' : C.cyan + '44'}`,
                        color: group === 'own' ? C.amber : C.cyan,
                        fontFamily: "'DM Mono', monospace",
                      }}>
                        {p.season} {ordinal(p.round)}
                      </span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      {playerModal === 'give' && (
        <PlayerModal
          title="ADD TO GIVE — YOUR ROSTER"
          players={myPlayers}
          onAdd={addGivePlayer}
          onClose={() => setPlayerModal(null)}
        />
      )}
      {playerModal === 'get' && (
        <PlayerModal
          title={partnerId ? `ADD TO GET — ${(partnerProfile?.display_name ?? 'PARTNER').toUpperCase()}` : 'ADD TO GET — YOUR ROSTER'}
          players={getModalPlayers}
          loading={partnerLoading}
          onAdd={addGetPlayer}
          onClose={() => setPlayerModal(null)}
        />
      )}
      {pickModal === 'give' && (
        <PickModal
          mode="give"
          ownedPicks={myPicksOwned}
          onAdd={addGivePick}
          onClose={() => setPickModal(null)}
        />
      )}
      {pickModal === 'get' && (
        <PickModal
          mode="get"
          ownedPicks={[]}
          onAdd={addGetPick}
          onClose={() => setPickModal(null)}
        />
      )}
    </div>
  )
}
