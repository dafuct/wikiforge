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

function SparkMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0" aria-hidden="true">
      <rect width="32" height="32" rx="7.5" fill="#241e15" />
      <path
        d="M16 4.2C16.9 11 18.9 13.1 26 14.2 18.9 15.3 16.9 17.4 16 24.2 15.1 17.4 13.1 15.3 6 14.2 13.1 13.1 15.1 11 16 4.2Z"
        fill="#dd8f3c"
      />
      <rect x="9" y="26.4" width="14" height="1.9" rx="0.95" fill="#e9ddc6" opacity="0.85" />
      <circle cx="24" cy="8" r="2.3" fill="#5ea587" />
    </svg>
  )
}

export default function Layout() {
  const { wikiId } = useParams()
  return (
    <div className="min-h-screen text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-[#fcf8ef]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-2.5">
          <Link to="/" className="group flex items-center gap-2.5">
            <SparkMark />
            <span className="font-display text-xl font-medium tracking-tight text-slate-900 transition-colors group-hover:text-blue-700">
              wikiforge
            </span>
          </Link>
          <nav className="flex flex-wrap items-center gap-1 text-sm">
            {tabs.map((t) => (
              <NavLink
                key={t.label}
                to={`/w/${wikiId}/${t.to}`}
                end={t.to === ''}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1 transition-colors ${
                    isActive
                      ? 'bg-blue-600/12 font-semibold text-blue-700'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          {wikiId && (
            <span
              className="ml-auto rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 font-mono text-xs text-slate-500"
              title={wikiId}
            >
              {wikiId}
            </span>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Outlet />
      </main>
    </div>
  )
}
