import { Link } from 'react-router-dom'
import { useRescanWikis, useWikis } from '../api/hooks'

export default function HomePage() {
  const { data: wikis, isLoading, error } = useWikis()
  const rescan = useRescanWikis()

  if (isLoading) return <p className="p-8 text-slate-400">Loading wikis…</p>
  if (error) return <p className="p-8 text-red-600">Failed to load wikis: {String(error)}</p>

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Your wikis</h1>
          <button
            onClick={() => rescan.mutate()}
            disabled={rescan.isPending}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {rescan.isPending ? 'Rescanning…' : 'Rescan'}
          </button>
        </div>
        {wikis?.length === 0 && (
          <p className="text-slate-500">
            No wikis found. Check <code>wikiforge.viewer.scan-roots</code> in application.yml
            or set <code>WIKIFORGE_HOME</code>.
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {wikis?.map((w) => (
            <Link
              key={w.id}
              to={`/w/${w.id}`}
              className="block rounded-lg border bg-white p-4 shadow-sm hover:shadow"
            >
              <div className="flex items-center gap-2">
                <span className="font-semibold">{w.name}</span>
                {w.kind === 'GLOBAL' && (
                  <span className="rounded bg-amber-100 px-1.5 text-xs text-amber-800">GLOBAL</span>
                )}
              </div>
              <p className="mt-1 truncate text-xs text-slate-400">{w.path}</p>
              <div className="mt-3 flex gap-4 text-sm text-slate-600">
                <span>{w.topics} topics</span>
                <span>${w.spendUsd.toFixed(2)} spent</span>
                {w.lastActivityAt && <span>active {w.lastActivityAt.slice(0, 10)}</span>}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
