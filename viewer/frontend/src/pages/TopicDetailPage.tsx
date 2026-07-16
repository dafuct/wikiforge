import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useArticle, useTopicDetail } from '../api/hooks'
import ConfidenceBadge from '../components/ConfidenceBadge'

type Tab = 'citations' | 'conflicts' | 'related'

export default function TopicDetailPage() {
  const { wikiId, slug } = useParams() as { wikiId: string; slug: string }
  const { data, isLoading, error } = useTopicDetail(wikiId, slug)
  const [tab, setTab] = useState<Tab>('citations')
  const [versionId, setVersionId] = useState<number | null>(null)
  const { data: oldArticle } = useArticle(wikiId, versionId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!data) return null

  const article = versionId && oldArticle ? oldArticle : data.article

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <article className="lg:col-span-2 rounded-lg border bg-white p-6">
        <div className="mb-4 flex items-center gap-3">
          <ConfidenceBadge value={article?.confidence ?? null} />
          {data.versions.length > 0 && (
            <select
              className="ml-auto rounded border px-2 py-1 text-sm"
              value={versionId ?? data.versions[0].articleId}
              onChange={(e) => setVersionId(Number(e.target.value))}
            >
              {data.versions.map((v) => (
                <option key={v.articleId} value={v.articleId}>
                  v{v.version} — {v.createdAt.slice(0, 10)}
                </option>
              ))}
            </select>
          )}
        </div>
        {article ? (
          <div className="prose prose-slate max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{article.bodyMd}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-slate-400">No compiled article yet.</p>
        )}
      </article>

      <aside className="rounded-lg border bg-white">
        <div className="flex border-b text-sm">
          {(['citations', 'conflicts', 'related'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 px-3 py-2 capitalize ${tab === t ? 'border-b-2 border-blue-600 font-semibold' : 'text-slate-500'}`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="p-4 text-sm">
          {tab === 'citations' && (
            <>
              <h3 className="mb-2 font-semibold">Citations ({data.citations.length})</h3>
              <ul className="space-y-3">
                {data.citations.length === 0 && <li className="text-slate-400">No citations.</li>}
                {data.citations.map((c, i) => (
                  <li key={i} className="rounded border p-2">
                    <p>{c.claim}</p>
                    {c.quote && <blockquote className="mt-1 border-l-2 pl-2 text-slate-500">“{c.quote}”</blockquote>}
                    <Link to={`/w/${wikiId}/sources/${c.sourceId}`} className="mt-1 block text-xs text-blue-600">
                      → {c.sourceTitle}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          {tab === 'conflicts' && (
            <ul className="space-y-3">
              {data.conflicts.length === 0 && <li className="text-slate-400">No conflicts.</li>}
              {data.conflicts.map((c) => (
                <li key={c.id} className="rounded border border-red-200 bg-red-50 p-2">
                  <p>{c.claim}</p>
                  <p className="mt-1 text-xs text-red-700">{c.nature} · sources {c.sourceIds} · {c.detectedAt.slice(0, 10)}</p>
                </li>
              ))}
            </ul>
          )}
          {tab === 'related' && (
            <ul className="space-y-2">
              {data.related.length === 0 && <li className="text-slate-400">No linked topics.</li>}
              {data.related.map((r) => (
                <li key={r.slug} className="flex justify-between">
                  <Link to={`/w/${wikiId}/topics/${r.slug}`} className="text-blue-700">{r.title}</Link>
                  <span className="text-xs text-slate-400">{r.score.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  )
}
