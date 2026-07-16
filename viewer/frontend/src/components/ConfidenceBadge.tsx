export default function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <span className="inline-flex items-center rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-xs text-slate-400">
        no article
      </span>
    )
  }
  const tone =
    value >= 0.7
      ? { chip: 'bg-green-100 text-green-800', dot: 'bg-green-600' }
      : value >= 0.4
        ? { chip: 'bg-amber-100 text-amber-800', dot: 'bg-amber-800' }
        : { chip: 'bg-red-100 text-red-800', dot: 'bg-red-600' }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${tone.chip}`}
      title="compile confidence"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden="true" />
      <span className="font-mono tabular-nums">{(value * 100).toFixed(0)}%</span>
    </span>
  )
}
