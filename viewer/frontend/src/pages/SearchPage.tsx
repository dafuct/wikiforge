import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSearch } from '../api/hooks'
import type { SearchHit } from '../api/types'

function hitLink(wikiId: string, hit: SearchHit): string {
  return hit.ownerType === 'article'
    ? `/w/${wikiId}/topics/${hit.linkSlug}`
    : `/w/${wikiId}/sources/${hit.linkSlug}`
}

// Render the FTS5 snippet WITHOUT dangerouslySetInnerHTML. SQLite's snippet()
// injects <mark> around matches but does NOT escape the surrounding chunk text —
// and that text is whatever was ingested (a scraped page's body can contain
// markup). Splitting on the markers and returning text nodes lets React escape
// everything; any markup in the source shows as visible text, which is correct.
function Snippet({ html }: { html: string }) {
  return (
    <p className="mt-1 text-slate-600">
      {html.split(/<mark>|<\/mark>/).map((part, i) =>
        i % 2 === 1
          ? <mark key={i} className="bg-yellow-200">{part}</mark>
          : <span key={i}>{part}</span>,
      )}
    </p>
  )
}

export default function SearchPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const { data: hits, isFetching, error } = useSearch(wikiId, q)

  const articles = hits?.filter((h) => h.ownerType === 'article') ?? []
  const sources = hits?.filter((h) => h.ownerType === 'raw_source') ?? []

  const section = (title: string, items: SearchHit[]) => (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 font-semibold">{title} ({items.length})</h2>
      <ul className="space-y-2 text-sm">
        {items.map((h, i) => (
          <li key={i} className="rounded border p-2">
            <Link to={hitLink(wikiId, h)} className="font-medium text-blue-700">{h.title}</Link>
            <Snippet html={h.snippet} />
          </li>
        ))}
        {items.length === 0 && <li className="text-slate-400">nothing</li>}
      </ul>
    </section>
  )

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => { e.preventDefault(); setQ(input) }}
        className="flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="search articles and sources…"
          className="flex-1 rounded border px-3 py-2"
        />
        <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-white">
          {isFetching ? '…' : 'Search'}
        </button>
      </form>
      {error && <p className="text-red-600">{String(error)}</p>}
      {q && hits && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {section('Articles', articles)}
          {section('Sources', sources)}
        </div>
      )}
    </div>
  )
}
