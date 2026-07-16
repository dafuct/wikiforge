import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, postJson } from './client'
import type {
  ActivityRow, DevlogEntry, GraphResponse, PageResponse, ResearchDetail,
  ResearchRow, SearchHit, SourceDetail, SourceRow, SpendRow, TopicDetail,
  TopicRow, ArticleView, WikiStats, WikiSummary,
} from './types'

const qs = (params: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const useWikis = () =>
  useQuery({ queryKey: ['wikis'], queryFn: () => fetchJson<WikiSummary[]>('/api/wikis') })

export const useRescanWikis = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<WikiSummary[]>('/api/wikis/rescan'),
    onSuccess: (data) => qc.setQueryData(['wikis'], data),
  })
}

export const useStats = (wikiId: string) =>
  useQuery({ queryKey: ['stats', wikiId], queryFn: () => fetchJson<WikiStats>(`/api/wikis/${wikiId}/stats`) })

export const useTopics = (wikiId: string, status?: string, sort?: string) =>
  useQuery({
    queryKey: ['topics', wikiId, status, sort],
    queryFn: () => fetchJson<TopicRow[]>(`/api/wikis/${wikiId}/topics${qs({ status, sort })}`),
  })

export const useTopicDetail = (wikiId: string, slug: string) =>
  useQuery({
    queryKey: ['topic', wikiId, slug],
    queryFn: () => fetchJson<TopicDetail>(`/api/wikis/${wikiId}/topics/${slug}`),
  })

export const useArticle = (wikiId: string, articleId: number | null) =>
  useQuery({
    queryKey: ['article', wikiId, articleId],
    queryFn: () => fetchJson<ArticleView>(`/api/wikis/${wikiId}/articles/${articleId}`),
    enabled: articleId !== null,
  })

export const useSources = (wikiId: string, page: number, type?: string, q?: string) =>
  useQuery({
    queryKey: ['sources', wikiId, page, type, q],
    queryFn: () => fetchJson<PageResponse<SourceRow>>(`/api/wikis/${wikiId}/sources${qs({ page, type, q })}`),
  })

export const useSourceDetail = (wikiId: string, id: string) =>
  useQuery({
    queryKey: ['source', wikiId, id],
    queryFn: () => fetchJson<SourceDetail>(`/api/wikis/${wikiId}/sources/${id}`),
  })

export const useResearch = (wikiId: string) =>
  useQuery({ queryKey: ['research', wikiId], queryFn: () => fetchJson<ResearchRow[]>(`/api/wikis/${wikiId}/research`) })

export const useResearchDetail = (wikiId: string, id: string) =>
  useQuery({
    queryKey: ['research', wikiId, id],
    queryFn: () => fetchJson<ResearchDetail>(`/api/wikis/${wikiId}/research/${id}`),
  })

export const useSpend = (wikiId: string, group: string, since?: string) =>
  useQuery({
    queryKey: ['spend', wikiId, group, since],
    queryFn: () => fetchJson<SpendRow[]>(`/api/wikis/${wikiId}/spend${qs({ group, since })}`),
  })

export const useActivity = (wikiId: string, page: number) =>
  useQuery({
    queryKey: ['activity', wikiId, page],
    queryFn: () => fetchJson<PageResponse<ActivityRow>>(`/api/wikis/${wikiId}/activity${qs({ page })}`),
  })

export const useDevlog = (wikiId: string, page: number) =>
  useQuery({
    queryKey: ['devlog', wikiId, page],
    queryFn: () => fetchJson<PageResponse<DevlogEntry>>(`/api/wikis/${wikiId}/devlog${qs({ page })}`),
  })

export const useGraph = (wikiId: string) =>
  useQuery({ queryKey: ['graph', wikiId], queryFn: () => fetchJson<GraphResponse>(`/api/wikis/${wikiId}/graph`) })

export const useSearch = (wikiId: string, q: string) =>
  useQuery({
    queryKey: ['search', wikiId, q],
    queryFn: () => fetchJson<SearchHit[]>(`/api/wikis/${wikiId}/search${qs({ q })}`),
    enabled: q.trim().length > 0,
  })
