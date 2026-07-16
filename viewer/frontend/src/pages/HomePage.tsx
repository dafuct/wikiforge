import { Link } from 'react-router-dom'
import { useRescanWikis, useWikis } from '../api/hooks'

export default function HomePage() {
  const { data: wikis, isLoading, error } = useWikis()
  const rescan = useRescanWikis()

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-4xl px-6 py-14 sm:py-20">
        <header className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-slate-400">
              read-only lens
            </p>
            <h1 className="mt-1 font-display text-4xl font-medium tracking-tight text-slate-900">
              Your wikis
            </h1>
            <p className="mt-2 max-w-md text-sm text-slate-500">
              Everything your knowledge bases have gathered — topics, sources, research and
              spend — across every project on this machine.
            </p>
          </div>
          <button
            onClick={() => rescan.mutate()}
            disabled={rescan.isPending}
            className="rounded-full border border-blue-700/25 bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
          >
            {rescan.isPending ? 'Rescanning…' : 'Rescan disk'}
          </button>
        </header>

        {isLoading && <p className="font-mono text-sm text-slate-400">Gathering wikis…</p>}
        {error && (
          <p className="rounded-lg border border-red-600/20 bg-red-100/50 px-4 py-3 text-sm text-red-700">
            Failed to load wikis: {String(error)}
          </p>
        )}

        {wikis?.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white/50 px-6 py-10 text-center">
            <p className="text-slate-600">No wikis found on this machine yet.</p>
            <p className="mt-2 text-sm text-slate-500">
              Point <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">wikiforge.viewer.scan-roots</code>{' '}
              at your projects, or set{' '}
              <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">WIKIFORGE_HOME</code>.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {wikis?.map((w) => (
            <Link
              key={w.id}
              to={`/w/${w.id}`}
              className="almanac-card group relative overflow-hidden rounded-xl p-5 transition duration-200 hover:-translate-y-0.5"
            >
              <span
                className={`absolute inset-y-0 left-0 w-1 ${
                  w.kind === 'GLOBAL' ? 'bg-blue-600' : 'bg-slate-300'
                }`}
                aria-hidden="true"
              />
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-medium text-slate-900">{w.name}</h2>
                {w.kind === 'GLOBAL' && (
                  <span className="rounded-full bg-blue-600/12 px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-blue-700">
                    GLOBAL
                  </span>
                )}
                <span className="ml-auto translate-x-1 text-slate-300 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100">
                  →
                </span>
              </div>
              <p className="mt-1 truncate font-mono text-xs text-slate-400">{w.path}</p>
              <div className="mt-4 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm">
                <span className="text-slate-600">
                  <span className="font-mono font-medium text-slate-900">{w.topics}</span> topics
                </span>
                <span className="text-slate-600">
                  <span className="font-mono font-medium text-slate-900">${w.spendUsd.toFixed(2)}</span> spent
                </span>
                {w.lastActivityAt && (
                  <span className="ml-auto font-mono text-xs text-slate-400">
                    active {w.lastActivityAt.slice(0, 10)}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
