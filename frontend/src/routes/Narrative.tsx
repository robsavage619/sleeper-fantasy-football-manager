import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { NarrativeContext } from '@/lib/api'

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

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 9, letterSpacing: '0.12em', color: C.muted,
      fontFamily: "'DM Mono', monospace", marginBottom: 6,
    }}>
      {children}
    </div>
  )
}

function SectionCard({
  title,
  accent,
  children,
}: {
  title: string
  accent: string
  children: React.ReactNode
}) {
  return (
    <div style={{
      background: C.card, borderRadius: 2, border: `1px solid ${C.border}`,
      boxShadow: `inset 3px 0 0 ${accent}`,
      padding: '12px 16px',
    }}>
      <div style={{
        fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
        fontSize: 14, color: accent, letterSpacing: '0.08em', marginBottom: 10,
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function PreviewRow({ text }: { text: string }) {
  return (
    <div style={{
      fontFamily: "'DM Mono', monospace", fontSize: 11, color: C.text,
      padding: '3px 0', borderBottom: `1px solid ${C.border}`, lineHeight: 1.4,
    }}>
      {text}
    </div>
  )
}

export function Narrative() {
  const [ctx, setCtx] = useState<NarrativeContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [showFullPrompt, setShowFullPrompt] = useState(false)

  async function generate() {
    setLoading(true)
    setError(null)
    try {
      const result = await api.narrative()
      setCtx(result)
      setShowFullPrompt(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate narrative')
    } finally {
      setLoading(false)
    }
  }

  function copyPrompt() {
    if (ctx?.prompt) {
      navigator.clipboard.writeText(ctx.prompt)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const isOffSeason = ctx?.season_type !== 'regular'

  return (
    <div style={{ padding: '20px 24px' }}>
      <h1 style={{
        fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
        fontSize: 30, color: C.cyan, margin: 0, letterSpacing: '0.04em', lineHeight: 1,
      }}>
        AI BRIEFING
      </h1>
      <p style={{ color: C.muted, fontSize: 11, margin: '4px 0 16px', letterSpacing: '0.1em' }}>
        MANUAL CONTEXT BUILDER · NOT THE AUTOMATED LOOP — SEE NOTE BELOW
      </p>

      {/* Where the real output lands */}
      <div style={{
        background: C.card, border: `1px solid ${C.cyan}44`,
        boxShadow: `inset 3px 0 0 ${C.cyan}`,
        borderRadius: 2, padding: '14px 16px', marginBottom: 16,
      }}>
        <div style={{
          fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
          fontSize: 16, color: C.cyan, letterSpacing: '0.05em', marginBottom: 6,
        }}>
          The real AI GM loop runs outside this page
        </div>
        <p style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, margin: 0 }}>
          Every week, run the <code style={{ color: C.text }}>war-room-reason</code> skill in a Claude Code
          session (or ask Claude to "run the war room"). It fetches the full briefing, reasons over your
          whole franchise, drafts recommendations, has a second independent agent critique the draft for
          invented facts or bad math, fixes anything flagged, then posts one verified document straight to
          the findings store — no copy-paste required. That output shows up as{' '}
          <Link to="/" style={{ color: C.cyan }}>INTEL · FINDINGS on the War Room</Link> dashboard.
        </p>
        <p style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, margin: '8px 0 0' }}>
          The generator below is a <strong style={{ color: C.text }}>manual fallback</strong> — a plain
          context dump you can paste into any LLM by hand when you can't run the skill. It has no
          self-critique step, so treat anything it produces as a first draft, not a verified call.
        </p>
      </div>

      {/* Generate button */}
      <button
        onClick={generate}
        disabled={loading}
        style={{
          width: '100%', padding: '12px 0', marginBottom: 16,
          background: loading ? C.border : C.border,
          border: `1px solid ${C.cyan}44`, borderRadius: 2,
          cursor: loading ? 'default' : 'pointer',
          fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
          fontSize: 16, letterSpacing: '0.1em',
          color: loading ? C.muted : C.cyan,
          transition: 'background 0.12s',
        }}
      >
        {loading ? 'ASSEMBLING CONTEXT…' : ctx ? 'REGENERATE MANUAL CONTEXT' : 'BUILD MANUAL CONTEXT (FALLBACK)'}
      </button>

      {error && (
        <div style={{
          background: C.card, border: `1px solid ${C.red}44`,
          borderRadius: 2, padding: '10px 14px', marginBottom: 16,
          color: C.red, fontSize: 12, fontFamily: "'DM Mono', monospace",
        }}>
          {error}
        </div>
      )}

      {ctx && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {/* Header bar */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14,
            padding: '10px 14px', background: C.card, border: `1px solid ${C.border}`,
            borderRadius: 2,
          }}>
            <div>
              <Label>SEASON</Label>
              <div style={{ fontFamily: "'DM Mono', monospace", color: C.text, fontSize: 14 }}>
                {ctx.season}
              </div>
            </div>
            <div>
              <Label>WEEK</Label>
              <div style={{ fontFamily: "'DM Mono', monospace", color: C.cyan, fontSize: 22, lineHeight: 1 }}>
                {ctx.week}
              </div>
            </div>
            <div>
              <span style={{
                fontSize: 10, padding: '2px 8px', borderRadius: 1,
                background: isOffSeason ? C.muted + '22' : C.green + '22',
                color: isOffSeason ? C.muted : C.green,
                fontFamily: "'DM Mono', monospace", letterSpacing: '0.06em',
              }}>
                {ctx.season_type.toUpperCase()}
              </span>
            </div>
            <div style={{ marginLeft: 'auto', color: C.muted, fontSize: 9, fontFamily: "'DM Mono', monospace" }}>
              {new Date(ctx.assembled_at).toLocaleTimeString()}
            </div>
          </div>

          {/* Context sections grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <SectionCard title="MY STARTERS" accent={C.cyan}>
              {ctx.sections.starters.length === 0 ? (
                <div style={{ color: C.muted, fontSize: 11 }}>No starters found</div>
              ) : ctx.sections.starters.map((line, i) => (
                <PreviewRow key={i} text={line} />
              ))}
            </SectionCard>

            <SectionCard title="WAIVER WIRE" accent={C.amber}>
              {ctx.sections.waiver_adds.length === 0 ? (
                <div style={{ color: C.muted, fontSize: 11 }}>No trending adds</div>
              ) : ctx.sections.waiver_adds.map((line, i) => (
                <PreviewRow key={i} text={line} />
              ))}
            </SectionCard>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <SectionCard title="THIS WEEK'S MATCHUP" accent={C.red}>
              <div style={{
                fontFamily: "'DM Mono', monospace", fontSize: 11, color: C.text,
                whiteSpace: 'pre-line', lineHeight: 1.5,
              }}>
                {ctx.sections.matchup}
              </div>
            </SectionCard>

            <SectionCard title="TRADE ANGLES" accent={C.green}>
              {ctx.sections.trade_angles.length === 0 ? (
                <div style={{ color: C.muted, fontSize: 11 }}>No clear positional gaps</div>
              ) : ctx.sections.trade_angles.map((line, i) => (
                <PreviewRow key={i} text={line} />
              ))}
            </SectionCard>
          </div>

          {ctx.sections.bench.length > 0 && (
            <SectionCard title="BENCH / DEPTH" accent={C.muted}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
                {ctx.sections.bench.join('  ·  ')}
              </div>
            </SectionCard>
          )}

          {/* Prompt section */}
          <div style={{
            background: C.card, border: `1px solid ${C.border}`,
            boxShadow: `inset 3px 0 0 ${C.cyan}`,
            borderRadius: 2, padding: '14px 16px', marginTop: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div>
                <div style={{
                  fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800,
                  fontSize: 18, color: C.cyan, letterSpacing: '0.06em',
                }}>
                  MANUAL FALLBACK PROMPT
                </div>
                <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.06em', marginTop: 2, fontFamily: "'DM Mono', monospace" }}>
                  NO SELF-CRITIQUE · PASTE INTO ANY LLM SESSION BY HAND
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={copyPrompt}
                  style={{
                    background: copied ? C.green + '22' : 'none',
                    border: `1px solid ${copied ? C.green : C.border}`,
                    borderRadius: 2, padding: '6px 14px', cursor: 'pointer',
                    color: copied ? C.green : C.muted,
                    fontSize: 11, letterSpacing: '0.06em', fontFamily: "'DM Mono', monospace",
                    transition: 'all 0.15s',
                  }}
                >
                  {copied ? 'COPIED!' : 'COPY PROMPT'}
                </button>
                <button
                  onClick={() => setShowFullPrompt(v => !v)}
                  style={{
                    background: 'none', border: `1px solid ${C.border}`,
                    borderRadius: 2, padding: '6px 12px', cursor: 'pointer',
                    color: C.muted, fontSize: 11, letterSpacing: '0.06em',
                    fontFamily: "'DM Mono', monospace",
                  }}
                >
                  {showFullPrompt ? 'HIDE' : 'PREVIEW'}
                </button>
              </div>
            </div>

            {showFullPrompt ? (
              <pre style={{
                background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2,
                padding: 14, margin: 0, fontSize: 10, color: C.muted,
                overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                fontFamily: "'DM Mono', monospace", lineHeight: 1.6,
                maxHeight: 500, overflowY: 'auto',
              }}>
                {ctx.prompt}
              </pre>
            ) : (
              <div style={{
                background: C.bg, border: `1px solid ${C.border}`, borderRadius: 2,
                padding: '10px 14px', color: C.muted, fontSize: 11,
                fontFamily: "'DM Mono', monospace", lineHeight: 1.5,
              }}>
                <div style={{ marginBottom: 4, color: C.text }}>
                  # Weekly Dynasty War Room — {ctx.season} Week {ctx.week}
                </div>
                <div style={{ color: C.muted }}>
                  Covers: starters · matchup · waiver targets · trade proposals · dynasty angle
                </div>
                <div style={{ marginTop: 6, color: C.cyan + 'aa', fontSize: 10 }}>
                  {ctx.prompt.length.toLocaleString()} chars · click PREVIEW to expand
                </div>
              </div>
            )}
          </div>

          {/* How to use the fallback */}
          <div style={{
            marginTop: 12, padding: '10px 14px',
            background: C.card, border: `1px solid ${C.border}`, borderRadius: 2,
          }}>
            <div style={{ color: C.muted, fontSize: 10, letterSpacing: '0.08em', marginBottom: 8, fontFamily: "'DM Mono', monospace" }}>
              WHEN YOU CAN'T RUN THE SKILL
            </div>
            <ol style={{ margin: 0, padding: '0 0 0 16px', color: C.muted, fontSize: 11, lineHeight: 1.8 }}>
              <li>Click <span style={{ color: C.cyan }}>COPY PROMPT</span> above</li>
              <li>Paste it into any LLM chat session by hand</li>
              <li>Read the output as an unverified first draft — it skipped the critique pass</li>
              <li>
                If you can, run <code style={{ color: C.text }}>war-room-reason</code> in Claude Code instead —
                it produces a verified finding that appears on the{' '}
                <Link to="/" style={{ color: C.amber }}>War Room dashboard</Link> automatically
              </li>
            </ol>
          </div>
        </motion.div>
      )}
    </div>
  )
}
