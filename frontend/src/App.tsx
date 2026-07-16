import { BrowserRouter, Routes, Route } from 'react-router-dom'
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
import { Edges } from '@/routes/Edges'
import { Matchups } from '@/routes/Matchups'
import { MarketSignals } from '@/routes/MarketSignals'
import { Roster } from '@/routes/Roster'
import { Trades } from '@/routes/Trades'
import { Waivers } from '@/routes/Waivers'
import { Owners } from '@/routes/Owners'
import { ReportCard } from '@/routes/ReportCard'
import { Prospects } from '@/routes/Prospects'
import { Narrative } from '@/routes/Narrative'
import { api } from '@/lib/api'

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

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
      className="h-8 shrink-0 flex items-center px-4 gap-4"
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
      <span style={{ width: 1, height: 12, background: '#162035', display: 'inline-block' }} />
      <span className="text-[11px] tracking-[0.2em] uppercase" style={{ color: '#3d5070' }}>
        {state?.season ?? '—'} · {state?.season_type?.toUpperCase() ?? '—'} · WK{' '}
        {state?.week ?? '—'}
      </span>
      <div className="flex-1" />
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
      <span style={{ width: 1, height: 12, background: '#162035', display: 'inline-block' }} />
      <span className="text-[11px] tracking-[0.2em] uppercase" style={{ color: '#3a7cc0' }}>
        AI ASSISTED · CLAUDE
      </span>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="flex min-h-screen" style={{ background: '#060a12', color: '#e8eef6' }}>
          <Sidebar />
          <div className="flex flex-col flex-1 min-w-0">
            <OpsBar />
            <main className="flex-1 overflow-auto">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/draft" element={<DraftBoard />} />
                <Route path="/roster" element={<Roster />} />
                <Route path="/edges" element={<Edges />} />
                <Route path="/matchups" element={<Matchups />} />
                <Route path="/market-signals" element={<MarketSignals />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/waivers" element={<Waivers />} />
                <Route path="/owners" element={<Owners />} />
                <Route path="/report-card" element={<ReportCard />} />
                <Route path="/prospects" element={<Prospects />} />
                <Route path="/narrative" element={<Narrative />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
      <Toaster position="bottom-right" theme="dark" richColors />
    </QueryClientProvider>
  )
}
