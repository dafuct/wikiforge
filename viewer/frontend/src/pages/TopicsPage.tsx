import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTopics } from '../api/hooks'
import ConfidenceBadge from '../components/ConfidenceBadge'

export default function TopicsPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [sort, setSort] = useState('title')
  const { data: topics, isLoading, error } = useTopics(wikiId, undefined, sort)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center justify-between border-b p-3">
        <h1 className="font-semibold">Topics ({topics?.length ?? 0})</h1>
        <select value={sort} onChange={(e) => setSort(e.target.value)}
                className="rounded border px-2 py-1 text-sm">
          <option value="title">by title</option>
          <option value="confidence">by confidence</option>
          <option value="researched">by last researched</option>
        </select>
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-slate-400">
          <tr>
            <th className="p-3">Topic</th>
            <th className="p-3">Confidence</th>
            <th className="p-3">Volatility</th>
            <th className="p-3">Researched</th>
            <th className="p-3">Compiled</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {topics?.map((t) => (
            <tr key={t.id} className="hover:bg-slate-50">
              <td className="p-3">
                <Link to={`/w/${wikiId}/topics/${t.slug}`} className="font-medium text-blue-700">
                  {t.title}
                </Link>
                {t.stale && <span className="ml-2 rounded bg-red-100 px-1.5 text-xs text-red-700">stale</span>}
              </td>
              <td className="p-3"><ConfidenceBadge value={t.confidence} /></td>
              <td className="p-3 text-slate-500">{t.volatility}</td>
              <td className="p-3 text-slate-500">{t.lastResearchedAt?.slice(0, 10) ?? '—'}</td>
              <td className="p-3 text-slate-500">{t.lastCompiledAt?.slice(0, 10) ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
