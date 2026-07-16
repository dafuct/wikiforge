export default function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-slate-400">no article</span>
  const color =
    value >= 0.7 ? 'bg-green-100 text-green-800'
    : value >= 0.4 ? 'bg-amber-100 text-amber-800'
    : 'bg-red-100 text-red-800'
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {(value * 100).toFixed(0)}%
    </span>
  )
}
