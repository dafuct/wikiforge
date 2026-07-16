import { Link, useParams } from 'react-router-dom'
import { useDevlog, useStats } from '../api/hooks'

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}

export default function DashboardPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const { data: stats, isLoading, error } = useStats(wikiId)
  const { data: devlog } = useDevlog(wikiId, 0)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!stats) return null

  const maxBucket = Math.max(1, ...stats.confidence.map((b) => b.count))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Topics" value={stats.topics} />
        <StatCard label="Articles" value={stats.articles} />
        <StatCard label="Sources" value={stats.sources} />
        <StatCard label="Spend" value={`$${stats.spendUsd.toFixed(2)}`} />
        <StatCard label="Citations" value={stats.citations} />
        <StatCard label="Chunks" value={stats.chunks} />
        <StatCard label="Stale topics" value={stats.staleTopics} />
        <StatCard label="Open conflicts" value={stats.openConflicts} />
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-semibold">Confidence distribution</h2>
        <div className="flex items-end gap-1" style={{ height: 96 }}>
          {Array.from({ length: 10 }, (_, i) => {
            const bucket = stats.confidence.find((b) => b.bucket === i)
            const h = bucket ? (bucket.count / maxBucket) * 100 : 0
            return (
              <div key={i} className="flex-1 text-center">
                <div className="mx-auto w-full rounded-t bg-blue-500" style={{ height: `${h}%` }} />
                <span className="text-[10px] text-slate-400">.{i}</span>
              </div>
            )
          })}
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-semibold">Recent dev log</h2>
          <Link to={`/w/${wikiId}/spend`} className="text-sm text-blue-600">all activity →</Link>
        </div>
        <ul className="divide-y text-sm">
          {devlog?.items.slice(0, 8).map((e) => (
            <li key={`${e.kind}-${e.refId}`} className="flex gap-3 py-2">
              <span className="w-36 shrink-0 text-slate-400">{e.ts}</span>
              <span className={`w-20 shrink-0 text-xs ${e.kind === 'dev_event' ? 'text-purple-600' : 'text-slate-500'}`}>
                {e.kind}
              </span>
              <span className="truncate">{e.title}</span>
            </li>
          ))}
          {devlog?.items.length === 0 && <li className="py-2 text-slate-400">no events yet</li>}
        </ul>
      </section>
    </div>
  )
}
