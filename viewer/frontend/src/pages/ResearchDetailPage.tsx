import { Link, useParams } from 'react-router-dom'
import { useResearchDetail } from '../api/hooks'

const stanceColor: Record<string, string> = {
  support: 'text-green-700',
  oppose: 'text-red-700',
  neutral: 'text-slate-500',
}

export default function ResearchDetailPage() {
  const { wikiId, sessionId } = useParams() as { wikiId: string; sessionId: string }
  const { data, isLoading, error } = useResearchDetail(wikiId, sessionId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!data) return null

  const byPersona = new Map<string, typeof data.findings>()
  for (const f of data.findings) {
    byPersona.set(f.persona, [...(byPersona.get(f.persona) ?? []), f])
  }

  return (
    <div className="space-y-4">
      <header className="rounded-lg border bg-white p-4">
        <h1 className="text-lg font-semibold">
          {data.session.topicTitle ?? `Session #${data.session.id}`}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {data.session.mode} · {data.session.status} · ${data.session.spendUsd.toFixed(2)}
          {data.session.budgetUsd !== null && <> of ${data.session.budgetUsd.toFixed(2)} budget</>}
        </p>
        {data.session.thesisClaim && (
          <p className="mt-2 rounded bg-slate-50 p-2 text-sm">Thesis: {data.session.thesisClaim}</p>
        )}
      </header>

      {data.verdicts.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Verdicts</h2>
          {data.verdicts.map((v, i) => (
            <div key={i} className="mb-2 rounded border p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{v.verdict}</span>
                <span className="text-xs text-slate-400">{(v.confidence * 100).toFixed(0)}%</span>
              </div>
              <p className="mt-1">{v.claim}</p>
              <p className="mt-1 text-slate-500">{v.rationale}</p>
            </div>
          ))}
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 font-semibold">Findings by persona</h2>
        {[...byPersona.entries()].map(([persona, findings]) => (
          <div key={persona} className="mb-4">
            <h3 className="mb-1 text-sm font-semibold text-purple-700">{persona}</h3>
            <ul className="space-y-2 text-sm">
              {findings.map((f, i) => (
                <li key={i} className="rounded border p-2">
                  <span className={`mr-2 text-xs uppercase ${stanceColor[f.stance] ?? 'text-slate-500'}`}>
                    {f.stance}
                  </span>
                  {f.summary}
                  <Link to={`/w/${wikiId}/sources/${f.sourceId}`}
                        className="ml-2 text-xs text-blue-600">→ {f.sourceTitle}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {data.findings.length === 0 && <p className="text-sm text-slate-400">No findings recorded.</p>}
      </section>
    </div>
  )
}
