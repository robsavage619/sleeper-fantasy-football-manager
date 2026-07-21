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

async function patch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'PATCH' })
  if (!res.ok) throw new Error(await errorMessage(res, path))
  return res.json() as Promise<T>
}

export type Me = {
  roster_id: number
  user_id: string
  display_name: string
  avatar: string | null
  faab_budget: number
  faab_used: number
  faab_remaining: number
}

export type FaabEntry = {
  roster_id: number
  faab_budget: number
  faab_used: number
  faab_remaining: number
}

export type LeagueMeta = {
  league_id: string
  name: string
  season: string
  status: string
  total_rosters: number
  roster_positions: string[]
  settings: Record<string, number>
  scoring_settings: Record<string, number>
  season_type: string
}

export function leagueTypeLabel(league?: LeagueMeta): string {
  const t = league?.settings?.type
  return t === 2 ? 'DYNASTY' : t === 1 ? 'KEEPER' : t === 0 ? 'REDRAFT' : '—'
}

export function leagueFormatLabel(league?: LeagueMeta): string {
  if (!league) return '—'
  const qb = league.roster_positions.filter((p) => p === 'QB').length
  const sf = league.roster_positions.includes('SUPER_FLEX')
  const rec = league.scoring_settings?.rec ?? 0
  const ppr = rec >= 1 ? 'full PPR' : rec >= 0.5 ? 'half PPR' : rec > 0 ? `${rec} PPR` : 'standard'
  return `${leagueTypeLabel(league).toLowerCase()} · ${sf ? 'SF' : `${qb}QB`} · ${ppr}`
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

export type SleeperMatchup = {
  roster_id: number
  matchup_id: number | null
  points: number
  players: string[]
  starters: string[]
  players_points: Record<string, number>
  starters_points?: number[]
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
  market_fpar: number | null
  divergence_pct: number | null
  signal: 'STEAL' | 'REACH' | 'HOLD'
}

export type OfferLogEntry = {
  offer_id: string
  logged_at: string
  sent: boolean
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
  evidence_count?: number
  calibration?: 'OWNER-HISTORY' | 'LIMITED-HISTORY' | 'LOW-SAMPLE' | 'UNCALIBRATED'
  calibration_notes?: string
}

export type DraftBoard = {
  status: 'pre_draft' | 'active' | 'complete'
  // True when my_slot below is our own standings-based projection (this league's
  // verified reverse-final-standings convention), not yet a Sleeper-confirmed order.
  order_projected: boolean
  projection_source_season: string | null
  current_pick: number
  total_picks: number
  current_round: number
  // null only when neither Sleeper nor the standings projection has an answer
  my_slot: number | null
  picks_until_my_turn: number | null
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
  model_value?: number
  market_value?: number | null
  market_valued?: boolean
  is_starter: boolean
  is_taxi: boolean
  is_reserve: boolean
  age_curve_adjustment?: number
  career_phase?: 'ascending' | 'at-peak' | 'declining'
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
    age_curve_adjustment?: number
    career_phase?: 'ascending' | 'at-peak' | 'declining'
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
  is_me: boolean
}

export type DraftClassStrength = {
  season: string
  strength: number // index centered on ~1.0
  pct: number // (strength - 1) * 100, signed
  label: 'STACKED' | 'STRONG' | 'AVERAGE' | 'SOFT' | 'WEAK' | 'UNRATED'
  note: string
  rated: boolean
  source: 'fantasycalc' | 'unavailable'
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
  market_source: string
}

export type PlayerSabermetrics = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  seasons: number[]
  consistency: {
    games: number
    floor: number
    median: number
    ceiling: number
    volatility: number
    boom_pct: number
    bust_pct: number
    startable_line: number
    replacement_line: number
    season: number
  }
  td_dependence: {
    td_points: number
    total_fp: number
    td_share: number
    positional_median: number
    vs_median: number
  }
  opportunity_trend: {
    snap_share_delta: number | null
    target_share_delta: number | null
    carries_delta: number | null
    window_weeks: number
  }
  age_curve: {
    residual: number
    expected_fpar: number
    actual_fpar: number
    prior_season: number | null
    current_season: number | null
    prior_age: number | null
    note: string
  }
  market_momentum: {
    trend_30day: number | null
    value: number | null
    overall_rank: number | null
    position_rank: number | null
  }
  usage_quality: {
    wopr: number | null
    target_share: number | null
    air_yards_share: number | null
    racr: number | null
    epa_per_play: number | null
    cpoe: number | null
    explosive_play_rate: number | null
    snap_share: number | null
  }
  xfp: {
    xfp: number
    actual_fp: number
    residual: number
    coeffs: Record<string, number>
    evidence_count: number
    label: string
  }
  data_quality: 'ok' | string
  warnings: string[]
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

export type DossierPick = { season: string; round: number; source?: 'own' | 'acquired'; value?: number }

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
  /** CFBD play-involvement share (usage.overall) — not literal target share; CFBD doesn't track targets. */
  usage_rate: number
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
  impact_score?: number
  impact_label?: 'LOW' | 'MED' | 'HIGH'
  acceptance_breakdown?: AcceptanceBreakdown | null
}

export type AcceptanceBreakdown = {
  base: number
  position_fit: number
  margin_score: number
  history_score: number
  window_score: number
  sample_penalty: number
  total: number
  confidence: 'LOW' | 'MED' | 'HIGH'
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

export type ProspectCollegeSeason = {
  season: number
  receiving?: {
    games: number
    receptions: number
    yards: number
    touchdowns: number
    ypr: number
  }
  rushing?: {
    games: number
    carries: number
    yards: number
    touchdowns: number
    ypc: number
  }
  passing?: {
    games: number
    completions: number
    attempts: number
    comp_pct: number
    yards: number
    touchdowns: number
    interceptions: number
    ypa: number
  }
}

export type ProspectSignal = {
  label: string
  detail: string
  tone: 'positive' | 'caution' | 'neutral'
}

export type ProspectMarket = {
  value: number | null
  overall_rank: number | null
  position_rank: number | null
  tier: number | null
  trend_30day: number | null
  adp: number | null
  roster_pct: number | null
  trade_frequency: number | null
  volatility: number | null
  volatility_pct: number | null
  redraft_value: number | null
  redraft_dynasty_diff: number | null
  draft_year: number | null
  draft_round: number | null
  draft_pick: number | null
  height: number | null
  weight: number | null
  college: string | null
  team: string | null
  age: number | null
  years_exp: number | null
  player_timeline: 'ASCENDING' | 'DEVELOPING' | 'READY-NOW' | 'WIN-NOW' | null
  dynasty_premium_pct: number | null
}

export type ProspectDraftCapital = {
  year: number | null
  round: number | null
  pick: number | null
  team: string | null
  capital_tier: 'PREMIUM' | 'DAY 2' | 'DAY 3' | null
}

export type ProspectAthleticism = {
  height_in: number | null
  weight: number | null
  forty: number | null
  vertical: number | null
  bench: number | null
  broad_jump: number | null
  cone: number | null
  shuttle: number | null
  draft_round: number | null
  draft_ovr: number | null
  draft_team: string | null
  school: string | null
  position: string | null
  speed_score: number | null
  athletic_grade: 'ELITE' | 'GOOD' | 'AVERAGE' | 'BELOW' | null
}

export type ProspectCollege = {
  source: string | null
  has_data: boolean
  seasons: ProspectCollegeSeason[]
  recruiting_rank: number | null
  stars: number | null
}

export type ProspectRosterFit = {
  position_rank: number | null
  position_of: number | null
  position_tier: string | null
  position_league_avg: number | null
  contention_label: string
  contention_window: string
  contention_rationale: string
  timeline_verdict: string | null
}

export type ProspectScoutingReport = {
  identity: {
    name: string
    position: 'QB' | 'RB' | 'WR' | 'TE'
    college: string
    class_year: number
    age: number | null
    nfl_team: string | null
    height_in: number | null
    weight: number | null
  }
  dynasty_prospect_score: number
  market: ProspectMarket | null
  draft_capital: ProspectDraftCapital | null
  athleticism: ProspectAthleticism | null
  college: ProspectCollege
  roster_fit: ProspectRosterFit | null
  signals: ProspectSignal[]
  data_quality: 'FULL' | 'PARTIAL' | 'DEGRADED'
  warnings: string[]
  sources_used: string[]
}

export type ProspectScoutFinding = {
  player_id: string | null
  name: string
  college: string
  // The model posts comps as plain strings ("Saquon Barkley — three-down back…"), but
  // older/structured payloads may use {name, rationale}. Accept both.
  comps: Array<string | { name: string; rationale?: string }>
  verdict: string
  case: string
  team_fit: string
  // risk_notes arrives as either a single string or a list of strings.
  risk_notes: string | string[]
  consensus_check?: string
  sources?: string[]
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

export type ReportCardDimension = {
  key: string
  label: string
  grade: string
  rank: number
  of: number
  value: number
  detail: string
}

export type ReportSeasonRecord = {
  season: string
  wins: number
  losses: number
  ties: number
  fpts: number
  reg_finish: number
  of_teams: number
  made_playoffs: boolean
  champion: boolean
}

export type ManagerReportCard = {
  roster_id: number
  display_name: string
  avatar: string | null
  is_me: boolean
  overall_grade: string
  overall_rank: number
  overall_score: number
  dimensions: ReportCardDimension[]
  record: string
  win_pct: number
  titles: number
  playoff_appearances: number
  seasons_played: number
  best_finish: number | null
  season_history: ReportSeasonRecord[]
  headline: string
}

export type OwnerGMMetrics = {
  roster_id: number
  user_id: string
  display_name: string | null
  skill_season: string
  luck: {
    skill_season: string
    actual_wins: number
    allplay_pct: number
    expected_wins: number
    luck_index: number
    close_wins: number
    close_losses: number
    one_score_games: number
  }
  lineup_efficiency: { efficiency: number | null; weeks: number; missing: boolean }
  faab: { budget: number; used: number | null; remaining: number | null }
  trade_ledger: {
    value_in: number
    value_out: number
    net: number
    trade_count: number
    resolved: number
    unresolved: number
    label: string // UNCALIBRATED
    evidence_count: number
  }
  data_quality: string
  warnings: string[]
}

export type TxPickup = {
  player_id: string
  name: string
  points: number
  started_points: number
}

export type TxTradeAsset = { player_id: string; name: string; points: number }

export type TxTradeDeal = {
  week: number
  partner: string
  received: TxTradeAsset[]
  given: TxTradeAsset[]
  picks_received: number
  picks_given: number
  received_points: number
  given_points: number
  net_points: number
}

export type DraftedPlayer = {
  player_id: string
  name: string
  position: string
  season: string
  round: number
  pick_no: number
  value: number
  rostered: boolean
}

export type DraftProfile = {
  roster_id: number
  display_name: string
  total_picks: number
  seasons_drafted: number
  position_mix: Record<string, number>
  position_lean: string
  hits: number
  hit_rate: number
  avg_pick_value: number
  best_picks: DraftedPlayer[]
  best_steal: DraftedPlayer | null
}

export type TransactionValue = {
  roster_id: number
  display_name: string
  season: string
  waiver_points: number
  waiver_started_points: number
  waiver_adds: number
  trade_in_points: number
  trade_out_points: number
  trade_net_points: number
  trade_count: number
  draft_started_points: number
  trade_started_points: number
  top_pickups: TxPickup[]
  trade_deals: TxTradeDeal[]
}

export interface RefreshStart {
  status: string
  started_at?: string
}

export interface RefreshSourceState {
  ok: boolean
  detail?: string
  error?: string
  refreshed_at?: string
}

export interface RefreshFreshness {
  exists: boolean
  mtime?: string
  cached_seasons?: number[]
}

export interface RefreshStatus {
  job: {
    status: 'idle' | 'running' | 'done' | 'error'
    started_at?: string
    finished_at?: string
    sources: Record<string, RefreshSourceState>
  }
  freshness: Record<string, RefreshFreshness>
}

// --- Edge & matchup surfaces (scoring-leverage, sim, regression, environment) ---

export type MispricingEntry = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  games_played: number
  our_fp: number
  generic_fp: number
  leverage: number
  pos_median_leverage: number
  edge_pct: number
  verdict: 'BUY' | 'SELL' | 'FAIR'
  age: number | null
  rosterable: boolean
  market_value: number | null
  value_gap: number | null
  note: string
}

export type MispricingBoard = {
  season: number
  calibration: string
  min_games: number
  market_source: string
  entries: MispricingEntry[]
  buys: MispricingEntry[]
  sells: MispricingEntry[]
  warnings: string[]
}

export type TeamOdds = {
  roster_id: number
  strength: number
  playoff_odds: number
  title_odds: number
  bye_odds: number
  avg_wins: number
  avg_seed: number
  is_me: boolean
}

export type SeasonSim = {
  season: number
  n_sims: number
  regular_weeks: number
  playoff_teams: number
  schedule_source: string
  teams: TeamOdds[]
  warnings: string[]
}

export type ContentionRow = {
  roster_id: number
  label: 'WIN-NOW' | 'SUSTAIN' | 'RETOOL' | 'REBUILD' | 'HOLD'
  playoff_odds: number
  title_odds: number
  core_age: number
  young_share: number
  strength: number
  seeking: string
  shedding: string
  rationale: string
  is_me: boolean
}

export type ContentionBoard = { season: number; windows: ContentionRow[]; warnings: string[] }

export type RegressionFlag = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  total_yards: number
  total_tds: number
  expected_tds: number
  td_oe: number
  verdict: 'SELL-HIGH' | 'BUY-LOW' | 'AGE-DECLINE' | 'NEUTRAL'
  age: number | null
  rosterable: boolean
  note: string
}

export type RegressionBoard = {
  season: number
  baselines: Record<string, number | Record<string, number>>
  sell_high: RegressionFlag[]
  buy_low: RegressionFlag[]
  basis: 'redzone-opportunity' | 'yardage'
  warnings: string[]
}

export type SoSWeek = { week: number; opponent: string; index: number }

export type TeamPositionSoS = {
  team: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  full_season_index: number
  playoff_index: number
  weeks_counted: number
  playoff_weeks_counted: number
  softest_week: SoSWeek | null
  toughest_week: SoSWeek | null
}

export type ScheduleStrength = {
  dvp_season: number
  schedule_season: number
  dvp: Record<string, number>
  sos: TeamPositionSoS[]
  warnings: string[]
}

export type EnvSplit = { bucket: string; games: number; avg_fp: number; delta: number }
export type StadiumSplit = { stadium: string; games: number; avg_fp: number; delta: number }

export type PlayerEnvironmentProfile = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  total_games: number
  overall_avg_fp: number
  splits: Record<string, EnvSplit>
  stadiums: StadiumSplit[]
  flags: string[]
}

export type EnvironmentFlags = { count: number; flagged: PlayerEnvironmentProfile[] }

export type HandcuffLink = {
  starter_id: string
  starter_name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  backup_id: string | null
  backup_name: string | null
  backup_owner: string
  status: 'SECURED' | 'EXPOSED' | 'NO_BACKUP'
}

export type LeverageStash = {
  backup_id: string
  backup_name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  starter_name: string
  starter_owner: string
}

export type HandcuffMap = {
  season: number
  my_links: HandcuffLink[]
  exposed: HandcuffLink[]
  leverage_stashes: LeverageStash[]
  warnings: string[]
}

export type WireAlert = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  recent_pct: number
  prior_pct: number
  delta: number
  available: boolean
  note: string
}

export type WireWatchBoard = { season: number; recent_n: number; alerts: WireAlert[]; warnings: string[] }

export type GamedayBrief = {
  week: number
  season: number
  has_matchup: boolean
  my_roster_id: number
  opponent_roster_id: number | null
  my_projected: number
  opponent_projected: number
  win_probability: number
  lineup_upside: number
  recommended_swaps: Array<{ start: string; sit: string; gain: number }>
  note: string
  warnings: string[]
}

export type VegasGame = {
  season: number
  week: number
  team: string
  opponent: string
  is_home: boolean
  implied_total: number | null
  opponent_implied_total: number | null
  team_spread: number | null
  game_total: number | null
  blowout_risk: number | null
}

export type VegasEnvironment = {
  season: number
  league_avg_implied_total: number | null
  games: VegasGame[]
  warnings: string[]
}

export type PlayoffTeamEnvironment = {
  team: string
  season: number
  weeks_counted: number
  avg_implied_total: number | null
  avg_blowout_risk: number | null
}

export type VegasPlayoffs = { season: number; teams: PlayoffTeamEnvironment[] }

export type PricePoint = { as_of: string; value: number }
export type PlayerMeta = { name: string; position: string; team: string }

export type PlayerPriceHistory = {
  sleeper_id: string
  meta: PlayerMeta | null
  points: PricePoint[]
  momentum_pct: number | null
  zscore: number | null
  note: string
}

export type PriceMovers = {
  snapshot_dates: string[]
  direction: 'up' | 'down'
  movers: PlayerPriceHistory[]
}

export type PriceTrendResponse = PlayerPriceHistory & { snapshot_dates: string[] }

export type PositionBidStats = {
  position: string
  n: number
  p25: number | null
  p50: number | null
  p75: number | null
  p90: number | null
}

export type OwnerBidProfile = {
  roster_id: number
  n_bids: number
  median_bid: number | null
  aggressiveness: 'AGGRESSIVE' | 'TYPICAL' | 'CONSERVATIVE' | 'UNKNOWN'
}

export type FaabMarket = {
  seasons_covered: string[]
  n_bids: number
  by_position: Record<string, PositionBidStats>
  by_owner: Record<string, OwnerBidProfile>
  warnings: string[]
}

export type OpponentAdjustedEntry = {
  player_id: string
  name: string
  position: 'QB' | 'RB' | 'WR' | 'TE'
  team: string
  games_played: number
  raw_fp: number
  adjusted_fp: number
  schedule_luck: number
  note: string
}

export type OpponentAdjustedBoard = {
  season: number
  softest_schedule: OpponentAdjustedEntry[]
  toughest_schedule: OpponentAdjustedEntry[]
  warnings: string[]
}

export type ScoreboardKind = {
  kind: string
  total: number
  graded: number
  correct: number
  hit_rate: number | null
}

export type Scoreboard = {
  recs: Array<{ finding_id: string; made_at: string; kind: string; subject: string; status: string; detail: string }>
  by_kind: ScoreboardKind[]
  overall_hit_rate: number | null
  graded_count: number
  pending_count: number
  warnings: string[]
}

export type PlayerAlert = {
  player_id: string
  name: string
  position: string
  team: string
  kind: 'INJURY' | 'DEPTH' | 'OPPORTUNITY'
  severity: 'WARN' | 'WATCH' | 'INFO'
  detail: string
}

export type LeagueMove = {
  week: number
  type: string | null
  roster_ids: number[]
  adds: string[]
  drops: string[]
  involves_me: boolean
}

export type IntelFeed = {
  roster_alerts: PlayerAlert[]
  opportunities: PlayerAlert[]
  league_moves: LeagueMove[]
  generated_note: string
}

export type NegotiationBrief = {
  target_player: string
  target_position: string
  target_value: number
  owner_name: string
  owner_archetype: string
  owner_window: string
  owner_needs: string[]
  owner_surplus: string[]
  opening_value: number
  fair_value: number
  walkaway_value: number
  talking_points: string[]
  prompt: string
  warnings: string[]
}

export const api = {
  draftBoard: (top = 50, season?: number) =>
    get<DraftBoard>(`/draft/board?top=${top}${season ? `&season=${season}` : ''}`),
  draftPrompt: (top = 25, season?: number) =>
    get<{ prompt: string; pick_number: number }>(`/draft/prompt?top=${top}${season ? `&season=${season}` : ''}`),
  league: () => get<LeagueMeta>('/league/'),
  me: () => get<Me>('/league/me'),
  refresh: () => post<RefreshStart>('/admin/refresh', {}),
  refreshStatus: () => get<RefreshStatus>('/admin/refresh/status'),
  faab: () => get<FaabEntry[]>('/league/faab'),
  rosters: () => get<Roster[]>('/league/rosters'),
  users: () => get<User[]>('/league/users'),
  tradedPicks: () => get<TradedPick[]>('/league/traded-picks'),
  matchups: (week: number) => get<SleeperMatchup[]>(`/league/matchups/${week}`),
  nflState: () => get<NFLState>('/league/state'),
  trending: (kind: 'add' | 'drop') => get<TrendingPlayer[]>(`/league/trending/${kind}`),
  // Request a generous limit: the backend defaults to 50, which silently truncates the
  // per-prospect scout set (60+) and drops the oldest findings — exactly the top-of-board
  // players scouted first. Callers here want the full set for matching/badging.
  findings: (kind?: string, limit = 500) =>
    get<Finding[]>(`/findings/?limit=${limit}${kind ? `&kind=${kind}` : ''}`),
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
  ownersSabermetrics: () => get<OwnerGMMetrics[]>('/owners/sabermetrics'),
  reportCard: () => get<ManagerReportCard[]>('/owners/report-card'),
  transactionValue: () => get<TransactionValue[]>('/owners/transaction-value'),
  draftProfile: () => get<DraftProfile[]>('/owners/draft-profile'),
  prospects: (year = 2025, top = 50) =>
    get<ProspectProfile[]>(`/draft/prospects?year=${year}&top=${top}`),
  prospectScouting: (params: {
    name: string
    position: string
    college?: string
    year?: number
    age?: number | null
    player_id?: string | null
    recruiting_rank?: number | null
    stars?: number | null
    dynasty_prospect_score?: number
  }) => {
    const qs = new URLSearchParams()
    qs.set('name', params.name)
    qs.set('position', params.position)
    if (params.college) qs.set('college', params.college)
    if (params.year != null) qs.set('year', String(params.year))
    if (params.age != null) qs.set('age', String(params.age))
    if (params.player_id) qs.set('player_id', params.player_id)
    if (params.recruiting_rank != null) qs.set('recruiting_rank', String(params.recruiting_rank))
    if (params.stars != null) qs.set('stars', String(params.stars))
    if (params.dynasty_prospect_score != null)
      qs.set('dynasty_prospect_score', String(params.dynasty_prospect_score))
    return get<ProspectScoutingReport>(`/draft/prospects/scouting?${qs.toString()}`)
  },
  prospectScoutingPrompt: (params: {
    name: string
    position: string
    college?: string
    year?: number
    age?: number | null
    player_id?: string | null
    recruiting_rank?: number | null
    stars?: number | null
    dynasty_prospect_score?: number
  }) => {
    const qs = new URLSearchParams()
    qs.set('name', params.name)
    qs.set('position', params.position)
    if (params.college) qs.set('college', params.college)
    if (params.year != null) qs.set('year', String(params.year))
    if (params.age != null) qs.set('age', String(params.age))
    if (params.player_id) qs.set('player_id', params.player_id)
    if (params.recruiting_rank != null) qs.set('recruiting_rank', String(params.recruiting_rank))
    if (params.stars != null) qs.set('stars', String(params.stars))
    if (params.dynasty_prospect_score != null)
      qs.set('dynasty_prospect_score', String(params.dynasty_prospect_score))
    return get<{ prompt: string }>(`/draft/prospects/scouting-prompt?${qs.toString()}`)
  },
  pickMarket: () => get<PickMarketSignal[]>('/picks/market'),
  draftClassStrength: () => get<DraftClassStrength[]>('/picks/class-strength'),
  playerSabermetrics: (playerId: string) =>
    get<PlayerSabermetrics>(`/players/${encodeURIComponent(playerId)}/sabermetrics`),
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
  offerLog: (sent?: boolean) =>
    get<OfferLogEntry[]>(`/offers${sent !== undefined ? `?sent=${sent}` : ''}`),
  logOffers: (offers: TradeOfferRecommendation[]) =>
    post<{ logged: number }>('/offers/log', offers),
  markOfferSent: (offerId: string) =>
    patch<{ offer_id: string; sent: boolean }>(`/offers/${offerId}/sent`),
  recommendationEvals: (top = 8) => get<RecommendationEval>(`/evals/recommendations?top=${top}`),
  transactionPlan: (body: { action_id: string; kind: string; command: string }) =>
    post<TransactionPlan>('/war-room/transaction-plan', body),
  narrative: () => get<NarrativeContext>('/season/narrative'),
  warRoomActions: (top = 12) => get<WarRoomAction[]>(`/war-room/actions?top=${top}`),
  // Edge & matchup surfaces
  mispricing: (top = 15) => get<MispricingBoard>(`/mispricing?top=${top}`),
  seasonSim: (nSims = 4000) => get<SeasonSim>(`/season-sim?n_sims=${nSims}`),
  contention: () => get<ContentionBoard>('/contention'),
  regression: (top = 15) => get<RegressionBoard>(`/regression?top=${top}`),
  scheduleStrength: (position?: string) =>
    get<ScheduleStrength>(`/schedule-strength${position ? `?position=${position}` : ''}`),
  environmentFlags: () => get<EnvironmentFlags>('/environment'),
  playerEnvironment: (playerId: string) =>
    get<PlayerEnvironmentProfile>(`/environment/${encodeURIComponent(playerId)}`),
  handcuffs: () => get<HandcuffMap>('/handcuffs'),
  wireWatch: (availableOnly = true) => get<WireWatchBoard>(`/wire-watch?available_only=${availableOnly}`),
  gameday: (week = 1) => get<GamedayBrief>(`/gameday?week=${week}`),
  vegasEnvironment: (week?: number) => get<VegasEnvironment>(`/vegas${week ? `?week=${week}` : ''}`),
  vegasPlayoffs: () => get<VegasPlayoffs>('/vegas/playoffs'),
  priceMovers: (direction: 'up' | 'down' = 'up', limit = 15) =>
    get<PriceMovers>(`/market/price-history/movers?direction=${direction}&limit=${limit}`),
  playerPriceTrend: (sleeperId: string) =>
    get<PriceTrendResponse>(`/market/price-history/${encodeURIComponent(sleeperId)}`),
  faabMarket: () => get<FaabMarket>('/faab-market'),
  opponentAdjusted: (season?: number, top = 12) =>
    get<OpponentAdjustedBoard>(
      `/opponent-adjusted?top=${top}${season ? `&season=${season}` : ''}`,
    ),
  scoreboard: () => get<Scoreboard>('/scoreboard'),
  gmAddressPrompt: () => get<{ prompt: string; generated_at: string }>('/gm-address'),
  // Real-world intelligence + negotiation copilot (previously computed, never wired to the UI)
  intelFeed: (rosterId?: number) => get<IntelFeed>(`/intel/feed${rosterId ? `?roster_id=${rosterId}` : ''}`),
  negotiation: (playerId: string, ownerRosterId: number) =>
    get<NegotiationBrief>(
      `/negotiation?player_id=${encodeURIComponent(playerId)}&owner_roster_id=${ownerRosterId}`,
    ),
}
