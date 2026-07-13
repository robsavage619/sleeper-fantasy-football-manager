const BASE = '/api'

async function errorMessage(res: Response, path: string): Promise<string> {
  try {
    const payload = await res.json()
    const detail = payload?.detail
    if (typeof detail === 'string') return `${res.status} ${res.statusText}: ${detail}`
    if (detail?.message) return `${res.status} ${res.statusText}: ${detail.message}`
    if (detail) return `${res.status} ${res.statusText}: ${JSON.stringify(detail)}`
  } catch {
    // Fall through to generic message.
  }
  return `${res.status} ${res.statusText}: ${path}`
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(await errorMessage(res, path))
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorMessage(res, path))
  return res.json() as Promise<T>
}

export type Roster = {
  roster_id: number
  owner_id: string | null
  players: string[]
  starters: string[]
  reserve: string[] | null
  taxi: string[] | null
  settings: Record<string, unknown>
}

export type User = {
  user_id: string
  display_name: string | null
  avatar: string | null
  metadata: Record<string, unknown>
}

export type TradedPick = {
  season: string
  round: number
  roster_id: number
  owner_id: number
  previous_owner_id: number | null
}

export type TrendingPlayer = {
  player_id: string
  count: number
  name: string
  position: string
  team: string
}

export type NFLState = {
  week: number | null
  season: string | null
  season_type: string | null
  display_week: number | null
}

export type Finding = {
  finding_id: string
  kind: string
  body: Record<string, unknown>
  created_at: number
  prompt_hash: string | null
}

export type DraftPlayer = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  age: number
  team: string
  fpar: number
  dynasty_value: number
  is_rookie: boolean
}

export type DraftBoard = {
  status: 'active' | 'complete'
  current_pick: number
  total_picks: number
  current_round: number
  my_slot: number
  picks_until_my_turn: number
  next_my_pick: number | null
  data_quality: 'FULL' | 'DEGRADED'
  warnings: string[]
  recommendation: DraftRecommendation | null
  players: DraftPlayer[]
}

export type DraftRecommendation = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  dynasty_value: number
  urgency: 'ON_CLOCK' | 'MONITOR' | 'BOARD'
  reason: string
  action: string
  alternatives: Array<{
    player_id: string
    name: string
    position: 'QB' | 'RB' | 'WR' | 'TE'
    dynasty_value: number
  }>
}

export type MyRosterPlayer = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  age: number
  team: string
  fpar: number
  dynasty_value: number
  is_starter: boolean
  is_taxi: boolean
  is_reserve: boolean
}

export type MyRoster = {
  roster_id: number
  total_players: number
  total_dynasty_value: number
  players: MyRosterPlayer[]
}

export type WaiverCandidate = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  age: number
  team: string
  trending_adds: number
  trending_drops: number
  add_priority: number
  faab_estimate: number
  bid_min: number
  bid_max: number
  drop_candidate: string | null
  downside: string
  urgency: 'LOW' | 'MED' | 'HIGH'
  decision: string
  rationale: string
}

export type PlayerProfile = {
  player_id: string
  identity: {
    player_id: string
    name: string
    position: string
    team: string
    age: number
    years_exp: number | null
    status: string
    injury_status: string
    search_rank: number | null
    gsis_id: string
  }
  value: {
    current_fpar: number
    dynasty_value: number
    pick_equivalent: string
    age_curve: string
    valuation_season: number
  }
  fantasy_summary: {
    games: number
    seasons?: number
    fantasy_points: number
    points_per_game: number
    best_week: PlayerWeek | null
    worst_week: PlayerWeek | null
    boom_weeks: number
    bust_weeks: number
  }
  season_summaries: PlayerSeasonSummary[]
  weekly: PlayerWeek[]
  usage: {
    recent_targets_per_game: number
    recent_carries_per_game: number
    recent_touches_per_game: number
    recent_points_per_game: number
    avg_snap_pct: number | null
    recent_snap_pct: number | null
  }
  injuries: Array<{
    season: number
    week: number
    team: string
    injury: string
    status: string
  }>
  depth: {
    season: number
    week: number
    team: string
    depth_team: string
    depth_position: string
    formation: string
  } | null
  data_quality: 'FULL' | 'DEGRADED'
  warnings: string[]
}

export type PlayerSeasonSummary = {
  season: number
  games: number
  fantasy_points: number
  points_per_game: number
  targets: number
  carries: number
  receptions: number
  passing_yards: number
  rushing_yards: number
  receiving_yards: number
  target_share: number
  air_yards_share: number
}

export type PlayerWeek = {
  season: number
  week: number
  team: string
  opponent: string
  fantasy_points: number
  targets: number
  carries: number
  receptions: number
  passing_yards: number
  rushing_yards: number
  receiving_yards: number
  touchdowns: number
}

export type OwnerProfile = {
  user_id: string
  display_name: string | null
  roster_id: number
  avatar: string | null
  player_count: number
  starter_count: number
  taxi_count: number
  reserve_count: number
  positions: Record<string, number>
  picks_owned: number
  picks_given: number
  archetype: 'REBUILDER' | 'CONTENDER' | 'BALANCED' | 'UNKNOWN'
  archetype_rationale: string
}

export type PickMarketSignal = {
  season: string
  round: number
  model_value: number
  market_value: number
  discount_pct: number
  signal: 'BUY' | 'SELL' | 'HOLD'
  rationale: string
  trade_count: number
}

export type OwnerSkillIndex = {
  roster_id: number
  user_id: string
  display_name: string | null
  allplay_wins: number
  allplay_games: number
  allplay_pct: number
  actual_wins: number
  actual_losses: number
  actual_ties: number
  actual_games: number
  expected_wins: number
  schedule_luck: number
  skill_season: string
  lineup_efficiency: number
  roster_value: number
  roster_value_pct: number
  skill_score: number
  skill_tier: 'ELITE' | 'STRONG' | 'AVERAGE' | 'WEAK'
  summary: string
}

export type DossierPlayer = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  age: number
  team: string
  dynasty_value: number
  is_starter: boolean
  is_taxi: boolean
  is_reserve: boolean
}

export type AgeBucket = {
  label: string
  min_age: number
  max_age: number
  count: number
  value: number
}

export type PositionValue = {
  position: 'QB' | 'RB' | 'WR' | 'TE'
  value: number
  count: number
  pct: number
}

export type ContentionWindow = {
  score: number // 0-100, higher = younger/ascending
  label: 'ASCENDING' | 'OPENING' | 'OPEN' | 'CLOSING' | 'RETOOLING'
  window: string // e.g. "2-3 year window"
  rationale: string
}

export type DossierPick = { season: string; round: number; source?: 'own' | 'acquired' }

export type PositionRank = {
  position: 'QB' | 'RB' | 'WR' | 'TE'
  value: number
  rank: number // 1 = best in league
  of: number // league size
  league_avg: number
  tier: 'DEEP' | 'SOLID' | 'AVERAGE' | 'THIN'
}

export type OwnerDossier = {
  roster_id: number
  user_id: string
  display_name: string | null
  avatar: string | null
  archetype: OwnerProfile['archetype']
  archetype_rationale: string
  total_dynasty_value: number
  value_rank: number // 1 = most valuable roster in league
  league_size: number
  top_heavy_pct: number // share of total value in top 3 assets, 0-100
  player_count: number
  avg_age: number
  avg_starter_age: number
  players: DossierPlayer[]
  age_buckets: AgeBucket[]
  value_by_position: PositionValue[]
  position_ranks: PositionRank[]
  contention: ContentionWindow
  picks_owned: DossierPick[]
  picks_traded_away: DossierPick[]
}

export type TradeEvent = {
  season: string
  week: number
  partner_roster_id: number | null
  partner_name: string | null
  received: string[]
  sent: string[]
}

export type OwnerHistory = {
  roster_id: number
  user_id: string
  trade_count: number
  trades: TradeEvent[]
  trade_partners: Array<{ roster_id: number; name: string | null; count: number }>
  waiver_adds: number
  free_agent_adds: number
  drops: number
  faab_spent: number
  seasons_covered: string[]
  // behavioral fingerprint
  seasons_active: number
  trades_per_season: number
  picks_acquired: number
  picks_sent: number
  net_picks: number // acquired − sent; >0 = hoards picks
  avg_trade_size: number // avg assets per trade
  top_partner_share: number // 0-1; share of trades with their #1 partner
  adds_per_season: number
  faab_per_season: number
  last_activity: { season: string; week: number } | null
  trades_by_season: Array<{ season: string; count: number }> // chronological
  behavioral_type: string // headline nickname, e.g. "THE PICK HOARDER"
  behavioral_summary: string // one-line objective read
  behavioral_tags: string[] // e.g. ["ACTIVE","PICK-HOARDER","FAAB-AGGRESSIVE"]
  pick_lean: 'HOARDS' | 'SPENDS' | 'NEUTRAL'
  approachability: 'OPEN' | 'SELECTIVE' | 'INSULAR' | 'DORMANT'
}

export type LeagueHistory = {
  seasons_covered: string[]
  owners: OwnerHistory[]
}

export type ProspectProfile = {
  player_id: string | null
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  college: string
  year: number
  age: number | null
  target_share: number
  yards_per_reception: number
  breakout_age: number | null
  recruiting_rank: number | null
  stars: number | null
  dynasty_prospect_score: number
  rationale: string
}

export type TradeAnalysis = {
  give_value: number
  get_value: number
  delta: number
  verdict: 'ACCEPT' | 'DECLINE' | 'CLOSE'
  data_quality: 'FULL' | 'DEGRADED'
  warnings: string[]
  prompt: string
}

export type NarrativeContext = {
  week: number
  season: string
  season_type: string
  prompt: string
  sections: {
    starters: string[]
    bench: string[]
    taxi: string[]
    matchup: string
    waiver_adds: string[]
    trade_angles: string[]
  }
  assembled_at: string
}

export type PlayerProjection = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  projected_pts: number
  confidence: 'HIGH' | 'MED' | 'LOW'
  source: string
  notes: string
}

export type StartSitRec = {
  week: number
  season: number
  projected_starters: PlayerProjection[]
  current_starters: PlayerProjection[]
  changes: Array<{ start: string; sit: string; gain: number }>
  total_projected_pts: number
  current_projected_pts: number
  prompt: string
  data_quality: 'FULL' | 'DEGRADED'
  warnings: string[]
}

export type WarRoomAction = {
  action_id: string
  kind: 'TRADE' | 'WAIVER' | 'PICK' | 'LINEUP' | 'SYSTEM'
  priority: number
  urgency: 'LOW' | 'MED' | 'HIGH'
  title: string
  detail: string
  target: string | null
  confidence: 'LOW' | 'MED' | 'HIGH'
  command: string
  source: string
  acceptance_score?: number | null
}

export type TradeAsset = {
  asset_id: string
  kind: 'player' | 'pick'
  label: string
  position: 'QB' | 'RB' | 'WR' | 'TE' | null
  value: number
}

export type TradeOfferRecommendation = {
  partner_roster_id: number
  partner_name: string
  acceptance_score: number
  confidence: 'LOW' | 'MED' | 'HIGH'
  priority: number
  give: TradeAsset[]
  receive: TradeAsset[]
  give_value: number
  receive_value: number
  value_delta: number
  target_need: string
  partner_need: string
  rationale: string
  command: string
  evidence_count: number
  calibration: 'OWNER-HISTORY' | 'LIMITED-HISTORY' | 'LOW-SAMPLE' | 'UNCALIBRATED'
  calibration_notes: string
}

export type RecommendationEval = {
  overall_status: 'PASS' | 'DEGRADED'
  findings: Array<{
    area: string
    status: string
    severity: string
    detail: string
    next_action: string
  }>
  metrics: Record<string, number | string>
}

export type TransactionPlan = {
  action_id: string
  kind: string
  command: string
  status: string
  confirm_phrase: string
  steps: string[]
  warnings: string[]
}

export const api = {
  draftBoard: (top = 50, season?: number) =>
    get<DraftBoard>(`/draft/board?top=${top}${season ? `&season=${season}` : ''}`),
  draftPrompt: (top = 25, season?: number) =>
    get<{ prompt: string; pick_number: number }>(`/draft/prompt?top=${top}${season ? `&season=${season}` : ''}`),
  league: () => get('/league/'),
  rosters: () => get<Roster[]>('/league/rosters'),
  users: () => get<User[]>('/league/users'),
  tradedPicks: () => get<TradedPick[]>('/league/traded-picks'),
  matchups: (week: number) => get(`/league/matchups/${week}`),
  nflState: () => get<NFLState>('/league/state'),
  trending: (kind: 'add' | 'drop') => get<TrendingPlayer[]>(`/league/trending/${kind}`),
  findings: (kind?: string) =>
    get<Finding[]>(`/findings/${kind ? `?kind=${kind}` : ''}`),
  latestFinding: (kind: string) => get<Finding>(`/findings/latest/${kind}`),
  postFinding: (kind: string, body: Record<string, unknown>) =>
    post<Finding>('/findings/', { kind, body }),
  myRoster: (season?: number) => get<MyRoster>(`/roster/my${season ? `?season=${season}` : ''}`),
  waiverCandidates: (top = 25) => get<WaiverCandidate[]>(`/season/waivers?top=${top}`),
  playerProfile: (playerId: string) =>
    get<PlayerProfile>(`/players/${encodeURIComponent(playerId)}/profile`),
  startSit: (week = 0, season?: number) =>
    get<StartSitRec>(`/season/startsit?week=${week}${season ? `&season=${season}` : ''}`),
  ownerProfiles: () => get<OwnerProfile[]>('/owners/profiles'),
  ownerSkill: () => get<OwnerSkillIndex[]>('/owners/skill'),
  prospects: (year = 2025, top = 50) =>
    get<ProspectProfile[]>(`/draft/prospects?year=${year}&top=${top}`),
  pickMarket: () => get<PickMarketSignal[]>('/picks/market'),
  ownerDossier: (rosterId: number, season?: number) =>
    get<OwnerDossier>(`/owners/dossier/${rosterId}${season ? `?season=${season}` : ''}`),
  leagueHistory: () => get<LeagueHistory>('/owners/history'),
  analyzeTrade: (body: {
    give_player_ids: string[]
    get_player_ids: string[]
    give_pick_ids: string[]
    get_pick_ids: string[]
  }) => post<TradeAnalysis>('/trades/analyze', body),
  tradeOffers: (top = 8) => get<TradeOfferRecommendation[]>(`/trades/offers?top=${top}`),
  recommendationEvals: (top = 8) => get<RecommendationEval>(`/evals/recommendations?top=${top}`),
  transactionPlan: (body: { action_id: string; kind: string; command: string }) =>
    post<TransactionPlan>('/war-room/transaction-plan', body),
  narrative: () => get<NarrativeContext>('/season/narrative'),
  warRoomActions: (top = 12) => get<WarRoomAction[]>(`/war-room/actions?top=${top}`),
}
