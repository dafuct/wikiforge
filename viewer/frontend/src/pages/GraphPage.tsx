import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { useGraph } from '../api/hooks'

interface FgNode { id: string; name: string; val: number; color: string }

export default function GraphPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const navigate = useNavigate()
  const { data, isLoading, error } = useGraph(wikiId)

  // react-force-graph-2d's canvas does not auto-size to its parent — without an
  // explicit width/height it renders 0x0 (verified against v1.29.1 in a real
  // browser). So measure the container and pass its size explicitly.
  //
  // This MUST be a callback ref, not useRef + useEffect([]): the container only
  // mounts after the isLoading/error gates below return, so an effect with empty
  // deps runs while the ref is still null and never re-attaches — leaving a
  // permanently 0x0 canvas on any cold load. A callback ref fires whenever the
  // node actually mounts, regardless of render order.
  const [size, setSize] = useState({ width: 0, height: 0 })
  const observerRef = useRef<ResizeObserver | null>(null)

  const containerRef = useCallback((el: HTMLDivElement | null) => {
    observerRef.current?.disconnect()
    if (!el) {
      observerRef.current = null
      return
    }
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    observerRef.current = observer
  }, [])

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as FgNode[], links: [] }
    return {
      nodes: data.nodes.map((n) => ({
        id: n.slug,
        name: `${n.title}${n.confidence !== null ? ` (${(n.confidence * 100).toFixed(0)}%)` : ''}`,
        val: 2 + (n.confidence ?? 0) * 6,
        color: n.confidence === null ? '#94a3b8' : n.confidence >= 0.7 ? '#16a34a' : n.confidence >= 0.4 ? '#d97706' : '#dc2626',
      })),
      links: data.links.map((l) => ({ source: l.source, target: l.target })),
    }
  }, [data])

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <h1 className="border-b p-3 font-semibold">
        Topic graph — {graphData.nodes.length} topics, {graphData.links.length} links
      </h1>
      <div ref={containerRef} style={{ height: '70vh' }}>
        <ForceGraph2D
          graphData={graphData}
          width={size.width}
          height={size.height}
          nodeLabel="name"
          linkColor={() => '#cbd5e1'}
          onNodeClick={(node) => navigate(`/w/${wikiId}/topics/${(node as FgNode).id}`)}
        />
      </div>
    </div>
  )
}
