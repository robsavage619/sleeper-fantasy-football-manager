import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Finding, NarrativeContext } from '@/lib/api'
import { Empty, Loading, VerdictStamp } from '@/components/viz'
import { buildStanding, evaluationAge, findingTime, stampDate } from '@/lib/standing'

const C = {
  bg: '#060a12',
  card: '#0c1625',
  border: '#162035',
  border2: '#24344f',
  text: '#e8eef6',
  muted: '#6a8098',
  dim: '#3d5070',
  cyan: '#00b8cc',
  amber: '#d4860c',
  green: '#1a9b5e',
  red: '#c93328',
  violet: '#9085e9',
}

const barlow = "'Barlow Condensed', sans-serif"
const mono = "'DM Mono', monospace"

// ── safe accessors over the untyped finding bodies ───────────────────────────
const str = (v: unknown): string => (v == null ? '' : String(v))
const rec = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
/** Assets arrive as either a single string or a list of pieces. */
const assets = (v: unknown): string => (Array.isArray(v) ? v.map(str).join(' + ') : str(v))

// ── memo furniture ───────────────────────────────────────────────────────────

function MemoSection({
  eyebrow,
  title,
  accent,
  stamp,
  children,
}: {
  eyebrow: string
  title: string
  accent: string
  stamp?: string
  children: React.ReactNode
}) {
  // Deliberately not animated: a standing document should be legible the
  // instant it paints. Entrance fades gate readability on rAF completing,
  // which throttling (backgrounded tab, low-power mode) can leave half-done.
  return (
    <section
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        boxShadow: `inset 3px 0 0 ${accent}`,
        borderRadius: 2,
        padding: '16px 20px 18px',
        marginBottom: 14,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.2em', color: accent }}>{eyebrow}</span>
        <h2
          style={{
            fontFamily: barlow,
            fontWeight: 800,
            fontSize: 21,
            color: C.text,
            letterSpacing: '0.04em',
            margin: 0,
            lineHeight: 1,
            textTransform: 'uppercase',
          }}
        >
          {title}
        </h2>
        <span style={{ flex: 1, height: 1, background: C.border, minWidth: 20 }} />
        {stamp && <span style={{ fontFamily: mono, fontSize: 9, color: C.dim }}>{stamp}</span>}
      </div>
      {children}
    </section>
  )
}

/** Body prose set for reading, not scanning. */
function Prose({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <p style={{ fontSize: size, color: '#c2d0e2', lineHeight: 1.72, margin: 0, maxWidth: '78ch' }}>{children}</p>
  )
}

/** Pull quote — lifts the single most load-bearing line out of the prose. */
function PullQuote({ children, accent }: { children: React.ReactNode; accent: string }) {
  return (
    <div
      style={{
        borderLeft: `2px solid ${accent}`,
        padding: '6px 0 6px 16px',
        margin: '14px 0',
        maxWidth: '62ch',
      }}
    >
      <span
        style={{
          fontFamily: barlow,
          fontSize: 19,
          fontWeight: 600,
          color: C.text,
          lineHeight: 1.32,
          letterSpacing: '0.01em',
        }}
      >
        {children}
      </span>
    </div>
  )
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginTop: 10 }}>
      <span style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.16em', color: C.dim, minWidth: 78 }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: C.muted, lineHeight: 1.6, flex: 1 }}>{children}</span>
    </div>
  )
}

/**
 * Split narrative prose into a lead paragraph and the remainder, so the memo
 * opens with a readable lead rather than one undifferentiated block.
 *
 * A sentence only ends where terminal punctuation is followed by whitespace
 * and a new sentence opener — the engine's prose is dense with decimals
 * ("luck index +3.71", "5 TDs vs 10.5 expected") that a naive split on "."
 * would tear mid-number.
 */
function splitLead(text: string): { lead: string; rest: string } {
  const sentences = text.match(/[\s\S]+?[.!?]+(?=\s+["'(“]?[A-Z]|\s*$)/g)
  if (!sentences || sentences.length < 3) return { lead: text, rest: '' }
  return { lead: sentences.slice(0, 2).join(' ').trim(), rest: sentences.slice(2).join(' ').trim() }
}

// ── memo sections ────────────────────────────────────────────────────────────

function StateOfFranchise({ finding }: { finding: Finding }) {
  const body = rec(finding.body)
  const text = str(body.narrative)
  const { lead, rest } = splitLead(text)
  return (
    <MemoSection
      eyebrow="§01"
      title="State of the Franchise"
      accent={C.cyan}
      stamp={stampDate(findingTime(finding))}
    >
      <Prose size={15}>{lead}</Prose>
      {rest && (
        <div style={{ marginTop: 12 }}>
          <Prose>{rest}</Prose>
        </div>
      )}
    </MemoSection>
  )
}

function TradePlan({ finding }: { finding: Finding }) {
  const body = rec(finding.body)
  const posture = str(body.posture)
  const recs = arr(body.trade_recs).map(rec)
  const sequencing = str(body.sequencing)

  return (
    <MemoSection eyebrow="§02" title="Trade Plan" accent={C.green} stamp={stampDate(findingTime(finding))}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        {posture && <VerdictStamp verdict={posture} stamped size="lg" />}
        <span style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.14em', color: C.dim }}>
          POSTURE · {recs.length} DEAL{recs.length === 1 ? '' : 'S'} ON THE TABLE
        </span>
      </div>

      {str(body.plan) && <Prose>{str(body.plan)}</Prose>}

      {/* Sequenced deal timeline — order matters, so it reads as a numbered run of play */}
      {recs.length > 0 && (
        <ol style={{ listStyle: 'none', margin: '18px 0 0', padding: 0 }}>
          {recs.map((r, i) => (
            <li
              key={i}
              style={{
                display: 'flex',
                gap: 14,
                paddingBottom: i === recs.length - 1 ? 0 : 16,
                position: 'relative',
              }}
            >
              {/* Timeline rail */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <span
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: '50%',
                    border: `1px solid ${C.green}66`,
                    background: 'rgba(26,155,94,0.1)',
                    color: C.green,
                    fontFamily: mono,
                    fontSize: 11,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                {i < recs.length - 1 && <span style={{ flex: 1, width: 1, background: C.border, marginTop: 4 }} />}
              </div>

              <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                  <span style={{ fontFamily: barlow, fontSize: 17, fontWeight: 700, color: C.text }}>
                    {str(r.partner)}
                  </span>
                  {str(r.urgency) && <VerdictStamp verdict={str(r.urgency)} />}
                </div>
                {/* The deal itself, as a ledger line */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    flexWrap: 'wrap',
                    fontFamily: mono,
                    fontSize: 12,
                    padding: '8px 12px',
                    background: C.bg,
                    border: `1px solid ${C.border}`,
                    borderRadius: 2,
                  }}
                >
                  <span style={{ color: C.red }}>{assets(r.send)}</span>
                  <span style={{ color: C.dim }}>→</span>
                  <span style={{ color: C.green }}>{assets(r.receive)}</span>
                </div>
                {str(r.rationale) && (
                  <p style={{ fontSize: 12.5, color: C.muted, lineHeight: 1.6, margin: '8px 0 0', maxWidth: '74ch' }}>
                    {str(r.rationale)}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}

      {sequencing && (
        <div
          style={{
            marginTop: 16,
            padding: '10px 14px',
            background: 'rgba(212,134,12,0.06)',
            border: `1px solid ${C.amber}33`,
            borderRadius: 2,
          }}
        >
          <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.16em', color: C.amber, marginBottom: 4 }}>
            SEQUENCING
          </div>
          <p style={{ fontSize: 12.5, color: '#c2d0e2', lineHeight: 1.6, margin: 0 }}>{sequencing}</p>
        </div>
      )}
    </MemoSection>
  )
}

function EdgeColumn({
  title,
  color,
  entries,
}: {
  title: string
  color: string
  entries: Record<string, unknown>[]
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: barlow,
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: '0.16em',
          color,
          paddingBottom: 6,
          marginBottom: 10,
          borderBottom: `1px solid ${color}33`,
        }}
      >
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {entries.map((e, i) => (
          <div key={i}>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 3 }}>{str(e.player)}</div>
            <p style={{ fontSize: 12, color: C.muted, lineHeight: 1.6, margin: 0 }}>{str(e.thesis)}</p>
            {str(e.target_partner) && (
              <div style={{ fontFamily: mono, fontSize: 10, color: C.dim, marginTop: 4 }}>
                TARGET · {str(e.target_partner)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function MarketEdges({ finding }: { finding: Finding }) {
  const body = rec(finding.body)
  const buys = arr(body.buys).map(rec)
  const sells = arr(body.sells).map(rec)
  const reconciliations = str(body.reconciliations)

  return (
    <MemoSection eyebrow="§03" title="Market Edges" accent={C.violet} stamp={stampDate(findingTime(finding))}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}>
        {buys.length > 0 && <EdgeColumn title={`BUY · ${buys.length}`} color={C.green} entries={buys} />}
        {sells.length > 0 && <EdgeColumn title={`SELL · ${sells.length}`} color={C.red} entries={sells} />}
      </div>
      {reconciliations && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
          <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.16em', color: C.dim, marginBottom: 5 }}>
            WHERE THE BOARDS DISAGREE
          </div>
          <Prose size={12.5}>{reconciliations}</Prose>
        </div>
      )}
    </MemoSection>
  )
}

function WaiverPlan({ finding }: { finding: Finding }) {
  const body = rec(finding.body)
  const recs = arr(body.waiver_recs).map(rec)
  const holds = arr(body.holds).map(str)

  return (
    <MemoSection eyebrow="§04" title="Waiver Plan" accent={C.amber} stamp={stampDate(findingTime(finding))}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {recs.map((r, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 14,
              padding: '12px 14px',
              background: C.bg,
              border: `1px solid ${C.border}`,
              borderRadius: 2,
            }}
          >
            {/* Bid chip — the number is the decision, so it leads */}
            <div style={{ textAlign: 'center', flexShrink: 0, minWidth: 56 }}>
              <div style={{ fontFamily: mono, fontSize: 22, fontWeight: 700, color: C.amber, lineHeight: 1 }}>
                ${str(r.faab_bid)}
              </div>
              <div style={{ fontFamily: mono, fontSize: 8.5, letterSpacing: '0.14em', color: C.dim, marginTop: 3 }}>
                FAAB
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{str(r.player)}</span>
                {str(r.tier) && <VerdictStamp verdict={str(r.tier)} />}
                {str(r.drop) && (
                  <span style={{ fontFamily: mono, fontSize: 10.5, color: C.dim }}>DROP {str(r.drop)}</span>
                )}
              </div>
              <p style={{ fontSize: 12.5, color: C.muted, lineHeight: 1.6, margin: 0 }}>{str(r.rationale)}</p>
            </div>
          </div>
        ))}
      </div>

      {holds.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.16em', color: C.dim, marginBottom: 6 }}>
            HOLDING FIRE
          </div>
          <ul style={{ margin: 0, padding: '0 0 0 16px' }}>
            {holds.map((h, i) => (
              <li key={i} style={{ fontSize: 12, color: C.muted, lineHeight: 1.65 }}>
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}
    </MemoSection>
  )
}

function RivalDossier({ finding }: { finding: Finding }) {
  const body = rec(finding.body)
  const angles = arr(body.angles).map(rec)
  const watch = arr(body.watch_items).map(str)

  return (
    <MemoSection eyebrow="§05" title="Rival Dossier" accent={C.red} stamp={stampDate(findingTime(finding))}>
      <div style={{ fontFamily: barlow, fontSize: 18, fontWeight: 700, color: C.text, marginBottom: 8 }}>
        TARGET · {str(body.target).toUpperCase()}
      </div>
      {str(body.exploit_plan) && <PullQuote accent={C.red}>{str(body.exploit_plan)}</PullQuote>}

      {angles.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 6 }}>
          {angles.map((a, i) => (
            <div key={i} style={{ padding: '10px 14px', background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontFamily: mono, fontSize: 12 }}>
                <span style={{ color: C.red }}>{assets(a.send)}</span>
                <span style={{ color: C.dim }}>→</span>
                <span style={{ color: C.green }}>{assets(a.receive)}</span>
                {str(a.urgency) && <VerdictStamp verdict={str(a.urgency)} />}
              </div>
              {str(a.rationale) && (
                <p style={{ fontSize: 12, color: C.muted, lineHeight: 1.6, margin: '7px 0 0' }}>{str(a.rationale)}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {watch.length > 0 && (
        <MetaRow label="WATCH">{watch.join(' · ')}</MetaRow>
      )}
    </MemoSection>
  )
}

/** Single-call findings (trade / waiver / draft / lineup / prospect). */
function SingleCalls({ standing }: { standing: ReturnType<typeof buildStanding> }) {
  const kinds: Array<[string, string]> = [
    ['trade', 'Trade calls'],
    ['waiver', 'Waiver calls'],
    ['draft', 'Draft calls'],
    ['lineup', 'Lineup calls'],
    ['prospect', 'Prospect calls'],
  ]
  const present = kinds.filter(([k]) => (standing.byKind.get(k)?.length ?? 0) > 0)
  if (present.length === 0) return null

  return (
    <MemoSection eyebrow="§06" title="Logged Calls" accent={C.dim}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
        {present.map(([kind, label]) => {
          const items = standing.byKind.get(kind) ?? []
          return (
            <div key={kind}>
              <div
                style={{
                  fontFamily: barlow,
                  fontSize: 12,
                  fontWeight: 800,
                  letterSpacing: '0.16em',
                  color: C.muted,
                  textTransform: 'uppercase',
                  paddingBottom: 6,
                  marginBottom: 8,
                  borderBottom: `1px solid ${C.border}`,
                }}
              >
                {label} · {items.length}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {items.map((f) => {
                  const b = rec(f.body)
                  const headline =
                    str(b.player) || str(b.pick) || str(b.name) || str(b.partner) || str(b.start) || kind
                  const detail =
                    kind === 'trade'
                      ? `${assets(b.send)} → ${assets(b.receive)}`
                      : kind === 'waiver'
                        ? `$${str(b.faab_bid)}${str(b.drop) ? ` · drop ${str(b.drop)}` : ''}`
                        : kind === 'lineup'
                          ? `sit ${str(b.sit)}`
                          : str(b.verdict)
                  return (
                    <div key={f.finding_id}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{headline}</span>
                        {str(b.urgency) && <VerdictStamp verdict={str(b.urgency)} />}
                        {str(b.verdict) && kind === 'prospect' && <VerdictStamp verdict={str(b.verdict)} />}
                      </div>
                      {detail && kind !== 'prospect' && (
                        <div style={{ fontFamily: mono, fontSize: 11, color: C.dim, marginTop: 2 }}>{detail}</div>
                      )}
                      {str(b.rationale) && (
                        <p style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.55, margin: '4px 0 0' }}>
                          {str(b.rationale)}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </MemoSection>
  )
}

/**
 * The model's own caveats, collected across the standing set. Surfacing these
 * is the point of the self-critique loop — they belong in the document, not
 * hidden in the JSON.
 */
function DataQuality({ standing }: { standing: ReturnType<typeof buildStanding> }) {
  const acks = useMemo(() => {
    const seen = new Set<string>()
    const out: Array<{ kind: string; text: string }> = []
    for (const f of standing.sections) {
      const text = str(rec(f.body).data_quality_ack).trim()
      if (text && !seen.has(text)) {
        seen.add(text)
        out.push({ kind: f.kind, text })
      }
    }
    return out
  }, [standing])

  const [open, setOpen] = useState(false)
  if (acks.length === 0) return null

  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 2, marginBottom: 14 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 20px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.2em', color: C.amber }}>⚠</span>
        <span
          style={{
            fontFamily: barlow,
            fontWeight: 800,
            fontSize: 15,
            letterSpacing: '0.08em',
            color: C.muted,
            textTransform: 'uppercase',
          }}
        >
          What the GM admits it doesn't know
        </span>
        <span style={{ flex: 1, height: 1, background: C.border }} />
        <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>
          {acks.length} NOTE{acks.length === 1 ? '' : 'S'} · {open ? 'HIDE' : 'READ'}
        </span>
      </button>
      {open && (
        <div style={{ padding: '0 20px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {acks.map((a) => (
            <div key={a.kind}>
              <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: '0.14em', color: C.dim, marginBottom: 4 }}>
                {a.kind.replace(/_/g, ' ').toUpperCase()}
              </div>
              <p style={{ fontSize: 12, color: C.muted, lineHeight: 1.65, margin: 0, maxWidth: '86ch' }}>{a.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── manual fallback (demoted) ────────────────────────────────────────────────

function ManualFallback() {
  const [ctx, setCtx] = useState<NarrativeContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [open, setOpen] = useState(false)

  async function generate() {
    setLoading(true)
    setError(null)
    try {
      setCtx(await api.narrative())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to build context')
    } finally {
      setLoading(false)
    }
  }

  function copyPrompt() {
    if (!ctx?.prompt) return
    navigator.clipboard.writeText(ctx.prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 2 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 20px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span
          style={{
            fontFamily: barlow,
            fontWeight: 800,
            fontSize: 15,
            letterSpacing: '0.08em',
            color: C.muted,
            textTransform: 'uppercase',
          }}
        >
          Manual fallback
        </span>
        <span style={{ flex: 1, height: 1, background: C.border }} />
        <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>
          NO SELF-CRITIQUE · {open ? 'HIDE' : 'OPEN'}
        </span>
      </button>

      {open && (
        <div style={{ padding: '0 20px 18px' }}>
          <p style={{ fontSize: 12, color: C.muted, lineHeight: 1.65, margin: '0 0 12px', maxWidth: '80ch' }}>
            A plain context dump to paste into any LLM by hand when you can't run the skill. It skips the
            critique pass, so treat anything it produces as a first draft, not a verified call.
          </p>

          <button
            onClick={generate}
            disabled={loading}
            style={{
              padding: '9px 18px',
              background: 'transparent',
              border: `1px solid ${C.cyan}44`,
              borderRadius: 2,
              cursor: loading ? 'default' : 'pointer',
              fontFamily: barlow,
              fontWeight: 800,
              fontSize: 14,
              letterSpacing: '0.1em',
              color: loading ? C.muted : C.cyan,
            }}
          >
            {loading ? 'ASSEMBLING…' : ctx ? 'REBUILD CONTEXT' : 'BUILD CONTEXT'}
          </button>

          {error && (
            <div style={{ marginTop: 12, color: C.red, fontSize: 12, fontFamily: mono }}>{error}</div>
          )}

          {ctx && (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span style={{ fontFamily: mono, fontSize: 11, color: C.muted }}>
                  {ctx.season} · WK {ctx.week} · {ctx.prompt.length.toLocaleString()} chars
                </span>
                <button
                  onClick={copyPrompt}
                  style={{
                    background: copied ? `${C.green}22` : 'transparent',
                    border: `1px solid ${copied ? C.green : C.border2}`,
                    borderRadius: 2,
                    padding: '5px 12px',
                    cursor: 'pointer',
                    color: copied ? C.green : C.muted,
                    fontSize: 11,
                    fontFamily: mono,
                    letterSpacing: '0.06em',
                  }}
                >
                  {copied ? 'COPIED' : 'COPY PROMPT'}
                </button>
              </div>
              <pre
                style={{
                  background: C.bg,
                  border: `1px solid ${C.border}`,
                  borderRadius: 2,
                  padding: 14,
                  margin: 0,
                  fontSize: 10,
                  color: C.muted,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: mono,
                  lineHeight: 1.6,
                  maxHeight: 320,
                  overflowY: 'auto',
                }}
              >
                {ctx.prompt}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── page ─────────────────────────────────────────────────────────────────────

export function Narrative() {
  const { data: findings, isLoading } = useQuery({
    queryKey: ['standing'],
    queryFn: () => api.standing(),
    refetchInterval: 60_000,
  })

  const standing = useMemo(() => buildStanding(findings), [findings])
  const age = evaluationAge(standing.evaluatedAt)

  const narrative = standing.byKind.get('narrative')?.[0]
  const tradePlan = standing.byKind.get('trade_plan')?.[0]
  const marketEdge = standing.byKind.get('market_edge')?.[0]
  const waiverPlan = standing.byKind.get('waiver_plan')?.[0]
  const dossier = standing.byKind.get('owner_dossier')?.[0]

  return (
    <div style={{ padding: '20px 24px 40px' }}>
      {/* Masthead */}
      <div style={{ marginBottom: 6 }}>
        <h1
          style={{
            fontFamily: barlow,
            fontWeight: 800,
            fontSize: 34,
            color: C.text,
            margin: 0,
            letterSpacing: '0.03em',
            lineHeight: 1,
            textTransform: 'uppercase',
          }}
        >
          The GM's Desk
        </h1>
        <p style={{ color: C.muted, fontSize: 10.5, margin: '6px 0 0', letterSpacing: '0.16em', fontFamily: mono }}>
          STANDING EVALUATION · SELF-CRITIQUED · HOLDS UNTIL THE NEXT RUN
        </p>
      </div>

      {/* Standing-document banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          flexWrap: 'wrap',
          padding: '10px 16px',
          margin: '14px 0 18px',
          background: age.stale ? 'rgba(212,134,12,0.06)' : 'rgba(0,184,204,0.05)',
          border: `1px solid ${age.stale ? `${C.amber}44` : `${C.cyan}33`}`,
          borderRadius: 2,
        }}
      >
        <span
          className={standing.isEmpty ? undefined : 'war-pulse'}
          style={{ color: age.stale ? C.amber : C.cyan, fontSize: 10 }}
        >
          ●
        </span>
        <span style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: '0.14em', color: C.text }}>
          EVALUATED {stampDate(standing.evaluatedAt)}
        </span>
        <span style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: '0.14em', color: age.stale ? C.amber : C.dim }}>
          {age.label.toUpperCase()}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: mono, fontSize: 10, color: C.dim }}>
          {standing.sections.length} SECTION{standing.sections.length === 1 ? '' : 'S'} ·{' '}
          {standing.scouts.length} SCOUT REPORT{standing.scouts.length === 1 ? '' : 'S'}
        </span>
      </div>

      {isLoading ? (
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 2 }}>
          <Loading label="Opening the standing evaluation" rows={6} />
        </div>
      ) : standing.isEmpty ? (
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 2, marginBottom: 14 }}>
          <Empty
            title="THE DESK IS CLEAR"
            action={
              <Link to="/" style={{ fontSize: 11, color: C.cyan, letterSpacing: '0.08em', textDecoration: 'none' }}>
                ← BACK TO THE WAR ROOM
              </Link>
            }
          >
            No evaluation on file. Run the <code style={{ color: C.cyan }}>war-room-reason</code> skill in a Claude
            Code session — it reads the full briefing, reasons over the franchise, has a second agent critique the
            draft for invented facts or bad math, then posts one verified document here. It stands until the next
            run replaces it.
          </Empty>
        </div>
      ) : (
        <>
          {narrative && <StateOfFranchise finding={narrative} />}
          {tradePlan && <TradePlan finding={tradePlan} />}
          {marketEdge && <MarketEdges finding={marketEdge} />}
          {waiverPlan && <WaiverPlan finding={waiverPlan} />}
          {dossier && <RivalDossier finding={dossier} />}
          <SingleCalls standing={standing} />
          <DataQuality standing={standing} />
        </>
      )}

      <ManualFallback />
    </div>
  )
}
