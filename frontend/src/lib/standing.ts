import type { Finding } from '@/lib/api'

/**
 * Standing-evaluation model.
 *
 * The findings store is append-only, so a raw newest-first feed buries the AI
 * GM's weekly calls the moment a 60-finding prospect-scout batch lands. The
 * app instead treats each decision kind as a *standing document*: the newest
 * finding of a kind is the current call and stays current until the next run
 * of that kind supersedes it. Scout reports are a per-player library, not a
 * feed, so they are deduped by player and kept separate.
 */

/** Decision kinds in reading order — plan documents first, then single calls. */
export const DECISION_KINDS = [
  'narrative',
  'trade_plan',
  'market_edge',
  'waiver_plan',
  'owner_dossier',
  'trade',
  'waiver',
  'draft',
  'lineup',
  'prospect',
] as const

export type DecisionKind = (typeof DECISION_KINDS)[number]

/** Kinds that are single-document-per-run (a newer one fully replaces the old). */
const SINGLETON_KINDS = new Set<string>([
  'narrative',
  'trade_plan',
  'market_edge',
  'waiver_plan',
  'owner_dossier',
])

const KIND_ORDER = new Map<string, number>(DECISION_KINDS.map((k, i) => [k, i]))

export type StandingEvaluation = {
  /** Newest decision finding per kind, in reading order. */
  sections: Finding[]
  /** All findings belonging to the most recent run of each multi-call kind. */
  byKind: Map<string, Finding[]>
  /** created_at (epoch seconds) of the newest standing finding, or null. */
  evaluatedAt: number | null
  /** Newest scout report per prospect, newest-first. */
  scouts: Finding[]
  /** True when nothing has ever been posted. */
  isEmpty: boolean
}

function bodyOf(f: Finding): Record<string, unknown> {
  return (f.body ?? {}) as Record<string, unknown>
}

/**
 * Timestamp a finding was generated. Prefers the model-reported
 * `generated_at` in the body, falling back to the store's `created_at`.
 */
export function findingTime(f: Finding): number {
  const gen = bodyOf(f).generated_at
  if (typeof gen === 'string') {
    const parsed = Date.parse(gen)
    if (!Number.isNaN(parsed)) return parsed / 1000
  }
  return f.created_at
}

/**
 * Collapse the raw findings list into the currently-standing evaluation.
 *
 * Singleton kinds keep only their newest finding. Multi-call kinds (trade,
 * waiver, draft, lineup, prospect) keep every finding from their most recent
 * run — findings of that kind posted within `runWindowSec` of the newest one —
 * so a three-trade week shows all three, but last week's calls drop away.
 */
export function buildStanding(findings: Finding[] | undefined, runWindowSec = 900): StandingEvaluation {
  if (!findings?.length) {
    return { sections: [], byKind: new Map(), evaluatedAt: null, scouts: [], isEmpty: true }
  }

  const scoutsByPlayer = new Map<string, Finding>()
  const grouped = new Map<string, Finding[]>()

  for (const f of findings) {
    if (f.kind === 'prospect_scout') {
      const body = bodyOf(f)
      const key = String(body.player_id ?? body.name ?? f.finding_id)
      const prev = scoutsByPlayer.get(key)
      if (!prev || findingTime(f) > findingTime(prev)) scoutsByPlayer.set(key, f)
      continue
    }
    const list = grouped.get(f.kind)
    if (list) list.push(f)
    else grouped.set(f.kind, [f])
  }

  const byKind = new Map<string, Finding[]>()
  for (const [kind, list] of grouped) {
    const sorted = [...list].sort((a, b) => findingTime(b) - findingTime(a))
    if (SINGLETON_KINDS.has(kind)) {
      byKind.set(kind, [sorted[0]])
    } else {
      const newest = findingTime(sorted[0])
      byKind.set(
        kind,
        sorted.filter((f) => newest - findingTime(f) <= runWindowSec),
      )
    }
  }

  const sections = [...byKind.values()]
    .map((list) => list[0])
    .sort((a, b) => {
      const oa = KIND_ORDER.get(a.kind) ?? 99
      const ob = KIND_ORDER.get(b.kind) ?? 99
      return oa !== ob ? oa - ob : findingTime(b) - findingTime(a)
    })

  const scouts = [...scoutsByPlayer.values()].sort((a, b) => findingTime(b) - findingTime(a))
  const stamps = sections.map(findingTime)
  const evaluatedAt = stamps.length ? Math.max(...stamps) : null

  return {
    sections,
    byKind,
    evaluatedAt,
    scouts,
    isEmpty: sections.length === 0 && scouts.length === 0,
  }
}

/** Absolute short date stamp, e.g. "Jul 18 · 03:55". */
export function stampDate(epochSec: number | null): string {
  if (!epochSec) return '—'
  const d = new Date(epochSec * 1000)
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} · ${d.toLocaleTimeString(
    undefined,
    { hour: '2-digit', minute: '2-digit', hour12: false },
  )}`
}

/** Coarse age of an evaluation, used to flag a stale standing document. */
export function evaluationAge(epochSec: number | null): { label: string; stale: boolean } {
  if (!epochSec) return { label: 'never run', stale: true }
  const days = (Date.now() / 1000 - epochSec) / 86_400
  if (days < 1) return { label: 'today', stale: false }
  if (days < 2) return { label: 'yesterday', stale: false }
  const whole = Math.round(days)
  return { label: `${whole}d ago`, stale: days >= 7 }
}
