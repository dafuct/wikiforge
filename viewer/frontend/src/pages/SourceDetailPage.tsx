import { Link, useParams } from 'react-router-dom'
import { useSourceDetail } from '../api/hooks'

export default function SourceDetailPage() {
  const { wikiId, sourceId } = useParams() as { wikiId: string; sourceId: string }
  const { data: s, isLoading, error } = useSourceDetail(wikiId, sourceId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!s) return null

  return (
    <div className="space-y-4">
      <header className="rounded-lg border bg-white p-4">
        <h1 className="text-lg font-semibold">{s.title}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {s.sourceType} · fetched {s.fetchedAt}
          {s.persona && <> · persona: {s.persona}</>}
        </p>
        {s.canonicalUrl && (
          <a href={s.canonicalUrl} target="_blank" rel="noreferrer"
             className="text-sm text-blue-600">{s.canonicalUrl}</a>
        )}
      </header>

      {s.citedBy.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold">Cited by</h2>
          <ul className="space-y-1 text-sm">
            {s.citedBy.map((c) => (
              <li key={c.articleId}>
                <Link to={`/w/${wikiId}/topics/${c.topicSlug}`} className="text-blue-700">
                  {c.articleTitle}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Provenance</h2>
        <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs">{s.provenance}</pre>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Full text</h2>
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">
          {s.text}
        </pre>
      </section>
    </div>
  )
}
