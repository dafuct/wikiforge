import { Link, useParams } from 'react-router-dom'
import { useResearch } from '../api/hooks'

export default function ResearchPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const { data: sessions, isLoading, error } = useResearch(wikiId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <h1 className="border-b p-3 font-semibold">Research sessions ({sessions?.length ?? 0})</h1>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-slate-400">
          <tr>
            <th className="p-3">Topic / thesis</th><th className="p-3">Mode</th>
            <th className="p-3">Status</th><th className="p-3">Spend</th><th className="p-3">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {sessions?.map((s) => (
            <tr key={s.id} className="hover:bg-slate-50">
              <td className="p-3">
                <Link to={`/w/${wikiId}/research/${s.id}`} className="font-medium text-blue-700">
                  {s.topicTitle ?? s.thesisClaim ?? `session #${s.id}`}
                </Link>
                {s.thesisClaim && s.topicTitle && (
                  <p className="text-xs text-slate-400">{s.thesisClaim}</p>
                )}
              </td>
              <td className="p-3 text-slate-500">{s.mode}</td>
              <td className="p-3">
                <span className={s.status === 'DONE' ? 'text-green-700' : 'text-amber-700'}>{s.status}</span>
              </td>
              <td className="p-3 text-slate-500">
                ${s.spendUsd.toFixed(2)}{s.budgetUsd !== null && <> / ${s.budgetUsd.toFixed(2)}</>}
              </td>
              <td className="p-3 text-slate-500">{s.startedAt.slice(0, 16)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
