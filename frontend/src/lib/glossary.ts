/**
 * Shared plain-English metric definitions — single source for every InfoTip
 * and glossary panel in the app. Originally lived only on the Report Card;
 * promoted here so every page can explain its own numbers instead of
 * shipping bare scores.
 */

export const GLOSSARY: Record<string, string> = {
  // --- Report Card dimensions --------------------------------------------
  value:
    'Roster Value — the combined dynasty value of every player on the roster. Higher means more long-term talent on hand.',
  skill:
    'Manager Skill — how well this GM plays regardless of luck: all-play win rate, lineup efficiency, and luck-adjusted results.',
  track: 'Track Record — historical results: career win % plus championships won.',
  build:
    'Roster Build — positional balance and depth across QB / RB / WR / TE. Rewards depth, penalizes holes at a position.',
  capital: 'Draft Capital — future draft picks currently stockpiled. More picks = more ammo to build or trade.',
  activity: 'Activity — how engaged the GM is: trades, waiver adds, and FAAB spent per season.',

  // --- Report Card metrics -------------------------------------------------
  dynastyValue:
    "Dynasty Value (DV) — the model's estimate of a player's long-term worth in a keeper/dynasty league, blending current production with age. A roster's value is the sum across all its players.",
  allPlay:
    'All-Play % — your win rate if you played EVERY team every week, not just your scheduled opponent. It strips out schedule luck; 50% is exactly average.',
  luck: "Luck (wins) — actual wins minus what all-play says you should have won. Positive = you've won more than your scores earned. Directional only — not a calibrated estimate.",
  lineupEfficiency:
    'Lineup Efficiency — points your starters scored vs the best legal lineup you could have set that week. 100% = perfect start/sit calls.',
  tradeLedger:
    'Trade Ledger P&L — retrospective value gained vs given up across all trades. UNCALIBRATED: a rough production-based estimate, and some historical assets can’t be matched by name.',
  draftHitRate: 'Draft Hit Rate — the share of a GM’s draft picks that returned real, startable fantasy value.',
  waiverValueAdded:
    'Waiver Value Added — fantasy points from waiver/free-agent pickups that actually reached the starting lineup.',
  faab: 'FAAB — Free-Agent Acquisition Budget, the fake money each team bids to claim players off waivers.',
  gradedOnCurve:
    'Graded on the curve — every grade is ranked WITHIN your league (#1 = A+, last = D). It answers “who’s best here,” not an absolute score.',
  draftClassStrength:
    'Draft Class Strength — how loaded an upcoming rookie class is, read live from the pick market (FantasyCalc): what the market pays for that class’s picks vs a neutral, time-discounted baseline. A premium = the crowd treats the class as stacked. This is already baked into every pick’s value and Draft Capital grade — shown here so it’s visible, not applied twice.',

  // --- Trade acceptance / FIT score ---------------------------------------
  acceptanceScore:
    "FIT score (0-100) — a heuristic estimate of how likely this partner is to accept the offer, built from roster-fit, value margin, their trade history, and their contention window. It is NOT a calibrated probability — it has never been checked against real accepted or rejected trades. Read it as a rough ranking of offers, not a percentage.",
  acceptanceConfidence:
    "Confidence — a label on the FIT score's magnitude (HIGH ≥ 74, MED ≥ 54, LOW below). This is a score band, not a statistical confidence interval — a HIGH-confidence score from one trade of history and one from eight trades of history look identical here.",
  acceptanceBreakdown:
    'FIT breakdown — the components summed into the score: a base of 42, plus points for roster fit (how well the positions solve both sides’ needs), value margin (how much you’re paying above fair value), this owner’s trade history/approachability, their contention-window fit, and a small-sample penalty when they have under 3 logged trades.',
  impactScore:
    'Impact — how much this trade actually improves YOUR roster, separate from whether the partner would accept it. Rewards landing a real need at a fair price; penalizes overpaying, trivial depth swaps, and trading for aging production while your own window says sell.',
  calibration:
    'Evidence quality — how much real trade history this partner’s acceptance estimate is based on. OWNER-HISTORY (8+ trades) is the most trustworthy; LOW-SAMPLE or UNCALIBRATED means the score is mostly generic heuristics.',

  // --- Dynasty value breakdown ---------------------------------------------
  currentFpar: 'Current FPAR — fantasy points above a replacement-level player at the same position, from last season’s actual production.',
  ageCurveAdjustment:
    'Age-curve adjustment — how much the dynasty value moves away from current production based on career stage: positive for a player still ascending toward their positional peak, negative for a player past it and declining.',
  careerPhase:
    'Career phase — ascending (still growing toward positional peak), at-peak, or declining (past peak, discounted forward).',

  // --- Waivers --------------------------------------------------------------
  waiverPriority:
    'Priority (0-100) — how urgently to add this player, blending trending-add momentum, positional need, and age. Above 80 is a same-day claim; below 60 is a speculative stash.',
  faabBidRange:
    'Suggested bid range — a low/high FAAB percentage based on this league’s historical winning bids at similar priority, not a guaranteed clearing price.',

  // --- Market Edges -----------------------------------------------------------
  edgePct:
    'Edge % — how much a player’s value under YOUR league’s exact scoring rules differs from their value under generic PPR. Positive = your league’s settings make them more valuable than the national market prices; that gap is the edge.',
  valueGap: 'Value gap — the raw point difference behind Edge %: league-scoring value minus generic-PPR value.',
  leverage: 'Leverage — a player’s scoring output relative to a positional baseline; the raw number the edge percentage is computed from.',
  titleOdds: 'Title odds — the share of Monte-Carlo simulated seasons (using current roster strength and remaining schedule) where this team wins the championship. A point estimate, not a confidence interval.',
  tdOverExpected:
    'TD over/under expected — actual touchdowns scored minus what red-zone opportunity + yardage predicts. Positive means touchdown-lucky and due for regression; negative means touchdown-unlucky and due for positive regression.',

  // --- Matchups ---------------------------------------------------------------
  sosIndex:
    'Strength of Schedule index — remaining-opponent difficulty relative to 1.0 (league average). Above 1.0 is a harder-than-average schedule; below 1.0 is easier.',
  winProbability: 'Win probability — this week’s modeled chance of winning your matchup, from projected scoring and matchup context.',
  lineupUpside: 'Lineup upside — projected points gained by starting the optimal lineup vs your current start/sit choices.',

  // --- Market Signals -----------------------------------------------------------
  blowoutRisk: 'Blowout risk — modeled chance this game’s spread produces a lopsided result, which tends to suppress the losing team’s garbage-time volume.',
  momentum: 'Momentum — recent trend in a player’s market value or usage, as a percent change over the recent window.',
  faabPercentile:
    'FAAB percentile (p25/p50/p75/p90) — the historical winning-bid distribution for similarly-valued waiver claims in this league. p50 is the median winning bid.',
  scheduleLuck: 'Schedule luck — how much easier or harder your opponents’ schedules have been than average, expressed as a win-equivalent.',

  // --- Prospects ------------------------------------------------------------
  prospectScore:
    'Dynasty prospect score (0-100) — a blended college-production and athletic-testing grade. Not a guarantee of NFL translation; treat it as a starting-point rank, not a probability of success.',
  usageRate: 'Usage rate — the share of their college offense’s touches/targets this player commanded. NOT the same measurement as NFL target share; the two aren’t directly comparable.',

  // --- Player profile drawer -------------------------------------------------
  wopr: 'WOPR (Weighted Opportunity Rating) — combines target share and air-yards share into one usage number; the strongest single predictor of receiver fantasy output.',
  targetShare: 'Target share — the percentage of the team’s pass targets this player received.',
  airYardsShare: 'Air yards share — the percentage of the team’s total downfield passing distance thrown this player’s way; a signal of role beyond raw targets.',
  xfpResidual:
    'xFP residual — actual fantasy points minus expected fantasy points from opportunity (targets/carries by depth and location). Positive means outperforming their usage — often a signal for regression.',
  pickEquivalent: 'Pick equivalent — the rookie-pick round this player’s dynasty value roughly matches, for comparing a player offer to a pick offer.',
}

/** Convenience: pick an ordered [term-label, definition][] list for a Glossary panel. */
export function glossaryEntries(keys: Array<[label: string, key: keyof typeof GLOSSARY]>): [string, string][] {
  return keys.map(([label, key]) => [label, GLOSSARY[key]])
}
