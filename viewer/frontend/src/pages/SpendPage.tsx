import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useActivity, useDevlog, useSpend } from '../api/hooks'

const GROUPS = ['model', 'purpose', 'day'] as const

export default function SpendPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [group, setGroup] = useState<(typeof GROUPS)[number]>('model')
  const { data: spend, error } = useSpend(wikiId, group)
  const { data: activity } = useActivity(wikiId, 0)
  const { data: devlog } = useDevlog(wikiId, 0)

  if (error) return <p className="text-red-600">{String(error)}</p>

  const total = spend?.reduce((acc, r) => acc + r.costUsd, 0) ?? 0

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="font-semibold">LLM spend — ${total.toFixed(2)}</h1>
          <div className="flex gap-1 text-sm">
            {GROUPS.map((g) => (
              <button key={g} onClick={() => setGroup(g)}
                      className={`rounded px-2 py-1 ${group === g ? 'bg-blue-600 text-white' : 'border'}`}>
                by {g}
              </button>
            ))}
          </div>
        </div>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={spend ?? []}>
              <XAxis dataKey="key" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `$${Number(v).toFixed(4)}`} />
              <Bar dataKey="costUsd" fill="#2563eb" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="p-2">{group}</th><th className="p-2">Calls</th>
                <th className="p-2">In tokens</th><th className="p-2">Out tokens</th><th className="p-2">Cost</th></tr>
          </thead>
          <tbody className="divide-y">
            {spend?.map((r) => (
              <tr key={r.key}>
                <td className="p-2 font-medium">{r.key}</td>
                <td className="p-2">{r.calls}</td>
                <td className="p-2">{r.inputTokens.toLocaleString()}</td>
                <td className="p-2">{r.outputTokens.toLocaleString()}</td>
                <td className="p-2">${r.costUsd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Dev log</h2>
          <ul className="divide-y text-sm">
            {devlog?.items.map((e) => (
              <li key={`${e.kind}-${e.refId}`} className="py-2">
                <span className="mr-2 text-xs text-slate-400">{e.ts}</span>
                <span className={`mr-2 text-xs ${e.kind === 'dev_event' ? 'text-purple-600' : 'text-slate-500'}`}>
                  {e.kind}
                </span>
                {e.title}
              </li>
            ))}
            {devlog?.items.length === 0 && <li className="py-2 text-slate-400">empty</li>}
          </ul>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Command activity</h2>
          <ul className="divide-y text-sm">
            {activity?.items.map((a) => (
              <li key={a.id} className="py-2">
                <span className="mr-2 text-xs text-slate-400">{a.ts}</span>
                <span className="mr-2 font-mono text-xs text-blue-700">{a.command}</span>
                {a.summary}
              </li>
            ))}
            {activity?.items.length === 0 && <li className="py-2 text-slate-400">empty</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
