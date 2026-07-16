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
        d="M22.5 5.2c.5 2.7 1.3 3.5 4 4-2.7.5-3.5 1.3-4 4-.5-2.7-1.3-3.5-4-4 2.7-.5 3.5-1.3 4-4Z"
        fill="#e7b25b"
      />
      <g fill="#dd8f3c">
        <path d="M4 15.1c-.8.7-.3 1.9.8 1.9h13.5c.6 0 .9-.5.7-1l-.5-1.1c-.2-.5.1-1 .7-1h5.3c.7 0 1-.9.4-1.3-2.2-1.6-4.9-2.5-7.7-2.5H9.2c-.5 0-.9.5-.7 1l.5 1.2c.2.5-.1 1-.7 1-2.2 0-4.3.6-5.9 1.9l1.5-.1Z" />
        <rect x="12.4" y="16.6" width="6" height="2.6" />
        <path d="M8.8 19.2h13.4c.6 0 1 .6.8 1.1l-.9 2.4c-.2.6-.7.9-1.3.9H10.2c-.6 0-1.1-.3-1.3-.9l-.9-2.4c-.2-.5.2-1.1.8-1.1Z" />
      </g>
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
