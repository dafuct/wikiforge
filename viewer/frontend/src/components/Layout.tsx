import { Link, NavLink, Outlet, useParams } from 'react-router-dom'

const tabs = [
  { to: '', label: 'Dashboard' },
  { to: 'topics', label: 'Topics' },
  { to: 'sources', label: 'Sources' },
  { to: 'research', label: 'Research' },
  { to: 'spend', label: 'Spend' },
  { to: 'graph', label: 'Graph' },
  { to: 'search', label: 'Search' },
]

export default function Layout() {
  const { wikiId } = useParams()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white px-6 py-3 flex items-center gap-6">
        <Link to="/" className="font-bold text-lg">wikiforge</Link>
        <nav className="flex gap-4 text-sm">
          {tabs.map((t) => (
            <NavLink
              key={t.label}
              to={`/w/${wikiId}/${t.to}`}
              end={t.to === ''}
              className={({ isActive }) =>
                isActive ? 'font-semibold text-blue-700' : 'text-slate-600 hover:text-slate-900'
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
        <span className="ml-auto text-xs text-slate-400">{wikiId}</span>
      </header>
      <main className="p-6 max-w-6xl mx-auto">
        <Outlet />
      </main>
    </div>
  )
}
