import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { Toaster, toast } from 'sonner'
import { Sidebar } from '@/components/layout/Sidebar'
import { Dashboard } from '@/routes/Dashboard'
import { DraftBoard } from '@/routes/DraftBoard'
import { Market } from '@/routes/Market'
import { Matchups } from '@/routes/Matchups'
import { Roster } from '@/routes/Roster'
import { Trades } from '@/routes/Trades'
import { Waivers } from '@/routes/Waivers'
import { Owners } from '@/routes/Owners'
import { ReportCard } from '@/routes/ReportCard'
import { Prospects } from '@/routes/Prospects'
import { Narrative } from '@/routes/Narrative'
import { NotFound } from '@/routes/NotFound'
import { api } from '@/lib/api'

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

/** "3h ago" style relative-time label from an ISO timestamp. */
function freshnessLabel(iso: string | undefined): string | null {
  if (!iso) return null
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return null
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 48) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

function OpsBar() {
  const qc = useQueryClient()
  const { data: state, isError: stateError } = useQuery({
    queryKey: ['nfl-state'],
    queryFn: api.nflState,
  })
  const { data: status } = useQuery({
    queryKey: ['refresh-status'],
    queryFn: api.refreshStatus,
    refetchInterval: (q) => (q.state.data?.job.status === 'running' ? 3000 : 60_000),
  })

  const refreshing = status?.job.status === 'running'

  // Freshest mtime across every source the last refresh touched — the
  // "how current is this data" signal the audit found fetched-but-unshown.
  const freshMtimes = Object.values(status?.freshness ?? {})
    .map((f) => f.mtime)
    .filter((m): m is string => !!m)
    .map((m) => Date.parse(m))
    .filter((t) => !Number.isNaN(t))
  // Oldest of the per-source mtimes = the staleness bound worth surfacing —
  // "last refreshed" should reflect the least-current source, not the freshest.
  const stalestMtime = freshMtimes.length ? Math.min(...freshMtimes) : undefined
  const freshLabel = stalestMtime ? freshnessLabel(new Date(stalestMtime).toISOString()) : null

  const refresh = useMutation({
    mutationFn: api.refresh,
    onSuccess: () => {
      toast.success('Refreshing data sources…')
      qc.invalidateQueries({ queryKey: ['refresh-status'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  // Connectivity reflects the actual API, not a decorative always-on light.
  const online = !stateError && state !== undefined
  const dot = online ? '#1a9b5e' : '#c0453a'
  const label = online ? 'LIVE' : 'OFFLINE'

  return (
    <div
      className="min-h-8 shrink-0 flex flex-wrap items-center px-4 gap-x-4 gap-y-1 py-1.5"
      style={{ background: '#09111f', borderBottom: '1px solid #162035' }}
    >
      <div className="flex items-center gap-2">
        <span
          className={online ? 'war-pulse inline-block w-1.5 h-1.5 rounded-full' : 'inline-block w-1.5 h-1.5 rounded-full'}
          style={{ background: dot }}
        />
        <span
          className="text-[11px] font-semibold tracking-[0.3em] uppercase"
          style={{ color: dot }}
        >
          {label}
        </span>
      </div>
      <span className="hidden sm:inline-block" style={{ width: 1, height: 12, background: '#162035' }} />
      <span className="hidden sm:inline text-[11px] tracking-[0.2em] uppercase" style={{ color: '#3d5070' }}>
        {state?.season ?? '—'} · {state?.season_type?.toUpperCase() ?? '—'} · WK{' '}
        {state?.week ?? '—'}
      </span>
      <div className="flex-1" />
      {freshLabel && (
        <span
          className="hidden md:inline text-[11px] tracking-[0.15em] uppercase"
          style={{ color: '#3d5070' }}
          title="Oldest per-source cache mtime — how stale the current numbers can be"
        >
          last refreshed {freshLabel}
        </span>
      )}
      <button
        onClick={() => refresh.mutate()}
        disabled={refreshing || refresh.isPending}
        className="text-[11px] tracking-[0.2em] uppercase px-2 py-0.5"
        style={{
          color: refreshing ? '#3d5070' : '#3a7cc0',
          border: '1px solid #162035',
          borderRadius: 2,
          cursor: refreshing || refresh.isPending ? 'default' : 'pointer',
        }}
        title="Rebuild Sleeper, nflverse, and market caches"
      >
        {refreshing ? 'Refreshing…' : '↻ Refresh Data'}
      </button>
      <span className="hidden lg:inline-block" style={{ width: 1, height: 12, background: '#162035' }} />
      <span className="hidden lg:inline text-[11px] tracking-[0.2em] uppercase" style={{ color: '#3a7cc0' }}>
        AI ASSISTED · CLAUDE
      </span>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="flex flex-col md:flex-row min-h-screen" style={{ background: '#060a12', color: '#e8eef6' }}>
          <Sidebar />
          <div className="flex flex-col flex-1 min-w-0">
            <OpsBar />
            <main className="flex-1 overflow-auto">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/draft" element={<DraftBoard />} />
                <Route path="/roster" element={<Roster />} />
                <Route path="/market" element={<Market />} />
                {/* Market Edges + Market Signals merged into /market — keep old links alive. */}
                <Route path="/edges" element={<Navigate to="/market" replace />} />
                <Route
                  path="/market-signals"
                  element={<Navigate to={{ pathname: '/market', search: `?tab=${encodeURIComponent('VEGAS & MOVERS')}` }} replace />}
                />
                <Route path="/matchups" element={<Matchups />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/waivers" element={<Waivers />} />
                <Route path="/owners" element={<Owners />} />
                <Route path="/report-card" element={<ReportCard />} />
                <Route path="/prospects" element={<Prospects />} />
                <Route path="/narrative" element={<Narrative />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
      <Toaster position="bottom-right" theme="dark" richColors />
    </QueryClientProvider>
  )
}
