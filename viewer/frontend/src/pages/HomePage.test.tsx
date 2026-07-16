import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import HomePage from './HomePage'

const wikis = [
  { id: 'global', name: 'global', path: '/home/x/wiki/wiki.db', kind: 'GLOBAL', topics: 12, lastActivityAt: '2026-07-01 11:00:00', spendUsd: 1.25 },
  { id: 'projа-abc12345', name: 'projA', path: '/home/x/dev/projA/.wikiforge/wiki.db', kind: 'PROJECT', topics: 3, lastActivityAt: null, spendUsd: 0 },
]

describe('HomePage', () => {
  it('renders a card per wiki from the API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(wikis))))
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><HomePage /></MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('projA')).toBeInTheDocument()
    expect(screen.getByText('global')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rescan/i })).toBeInTheDocument()
  })
})
