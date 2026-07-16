import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import TopicDetailPage from './TopicDetailPage'

const detail = {
  topic: { id: 1, slug: 'rust-async', title: 'Rust Async', status: 'ACTIVE', volatility: 'MEDIUM', confidence: 0.82, stale: false, lastResearchedAt: null, lastCompiledAt: null },
  article: { id: 11, title: 'Rust Async', bodyMd: '# Rust Async\n\nTokio is the dominant runtime.', confidence: 0.82, version: 2, createdAt: '2026-07-01 11:00:00' },
  versions: [{ articleId: 11, version: 2, confidence: 0.82, createdAt: '2026-07-01 11:00:00' }],
  citations: [{ claim: 'Tokio is the dominant async runtime', quote: 'tokio runtime text', sourceId: 1, sourceTitle: 'Async Book', sourceUrl: null }],
  conflicts: [],
  related: [],
}

describe('TopicDetailPage', () => {
  it('renders markdown body and citations', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(detail))))
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/w/global/topics/rust-async']}>
          <Routes>
            <Route path="/w/:wikiId/topics/:slug" element={<TopicDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Rust Async', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/Tokio is the dominant runtime/)).toBeInTheDocument()
    expect(screen.getByText('Citations (1)')).toBeInTheDocument()
  })
})
