export type WikiKind = 'GLOBAL' | 'PROJECT'

export interface WikiSummary {
  id: string; name: string; path: string; kind: WikiKind
  topics: number; lastActivityAt: string | null; spendUsd: number
}

export interface ConfidenceBucket { bucket: number; count: number }

export interface WikiStats {
  topics: number; articles: number; sources: number; chunks: number
  citations: number; spendUsd: number; staleTopics: number
  openConflicts: number; confidence: ConfidenceBucket[]
}

export interface TopicRow {
  id: number; slug: string; title: string; status: string; volatility: string
  confidence: number | null; stale: boolean
  lastResearchedAt: string | null; lastCompiledAt: string | null
}

export interface ArticleView {
  id: number; title: string; bodyMd: string; confidence: number
  version: number; createdAt: string
}

export interface VersionRef { articleId: number; version: number; confidence: number; createdAt: string }
export interface CitationView { claim: string; quote: string | null; sourceId: number; sourceTitle: string; sourceUrl: string | null }
export interface ConflictView { id: number; claim: string; nature: string; sourceIds: string; detectedAt: string }
export interface RelatedTopic { slug: string; title: string; score: number }

export interface TopicDetail {
  topic: TopicRow; article: ArticleView | null; versions: VersionRef[]
  citations: CitationView[]; conflicts: ConflictView[]; related: RelatedTopic[]
}

export interface PageResponse<T> { items: T[]; total: number; page: number; size: number }

export interface SourceRow {
  id: number; title: string; sourceType: string
  canonicalUrl: string | null; persona: string | null; fetchedAt: string
}

export interface CitedBy { articleId: number; articleTitle: string; topicSlug: string }

export interface SourceDetail extends SourceRow { text: string; provenance: string; citedBy: CitedBy[] }

export interface ResearchRow {
  id: number; topicSlug: string | null; topicTitle: string | null; thesisClaim: string | null
  mode: string; status: string; budgetUsd: number | null; spendUsd: number
  startedAt: string; endedAt: string | null
}

export interface Finding { persona: string; summary: string; stance: string; sourceId: number; sourceTitle: string }
export interface Verdict { claim: string; verdict: string; confidence: number; rationale: string; citations: string }
export interface ResearchDetail { session: ResearchRow; findings: Finding[]; verdicts: Verdict[] }

export interface SpendRow { key: string; calls: number; inputTokens: number; outputTokens: number; costUsd: number }
export interface ActivityRow { id: number; ts: string; command: string; summary: string; topicId: number | null }
export interface DevlogEntry { kind: 'dev_event' | 'activity'; refId: number; title: string; ts: string; extra: string }

export interface GraphNode { slug: string; title: string; confidence: number | null }
export interface GraphLink { source: string; target: string; score: number }
export interface GraphResponse { nodes: GraphNode[]; links: GraphLink[] }

export interface SearchHit { ownerType: 'article' | 'raw_source'; ownerId: number; snippet: string; title: string; linkSlug: string }
