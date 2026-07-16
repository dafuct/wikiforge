import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSources } from '../api/hooks'

const TYPES = ['', 'url', 'text', 'file', 'pdf', 'dev_event']

export default function SourcesPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [page, setPage] = useState(0)
  const [type, setType] = useState('')
  const [q, setQ] = useState('')
  const { data, isLoading, error } = useSources(wikiId, page, type || undefined, q || undefined)

  if (error) return <p className="text-red-600">{String(error)}</p>

  const pages = data ? Math.ceil(data.total / data.size) : 0

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center gap-3 border-b p-3">
        <h1 className="font-semibold">Sources ({data?.total ?? '…'})</h1>
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(0) }}
          placeholder="filter by title…"
          className="ml-auto rounded border px-2 py-1 text-sm"
        />
        <select value={type} onChange={(e) => { setType(e.target.value); setPage(0) }}
                className="rounded border px-2 py-1 text-sm">
          {TYPES.map((t) => <option key={t} value={t}>{t || 'all types'}</option>)}
        </select>
      </div>
      {isLoading ? <p className="p-3 text-slate-400">Loading…</p> : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="p-3">Title</th><th className="p-3">Type</th><th className="p-3">Persona</th><th className="p-3">Fetched</th></tr>
          </thead>
          <tbody className="divide-y">
            {data?.items.map((s) => (
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="p-3">
                  <Link to={`/w/${wikiId}/sources/${s.id}`} className="text-blue-700">{s.title}</Link>
                  {s.canonicalUrl && <p className="truncate text-xs text-slate-400">{s.canonicalUrl}</p>}
                </td>
                <td className="p-3 text-slate-500">{s.sourceType}</td>
                <td className="p-3 text-slate-500">{s.persona ?? '—'}</td>
                <td className="p-3 text-slate-500">{s.fetchedAt.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pages > 1 && (
        <div className="flex items-center gap-2 border-t p-3 text-sm">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}
                  className="rounded border px-2 py-1 disabled:opacity-40">←</button>
          <span>page {page + 1} / {pages}</span>
          <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}
                  className="rounded border px-2 py-1 disabled:opacity-40">→</button>
        </div>
      )}
    </div>
  )
}
