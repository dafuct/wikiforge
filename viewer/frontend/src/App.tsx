import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import DashboardPage from './pages/DashboardPage'
import TopicsPage from './pages/TopicsPage'
import TopicDetailPage from './pages/TopicDetailPage'
import SourcesPage from './pages/SourcesPage'
import SourceDetailPage from './pages/SourceDetailPage'
import ResearchPage from './pages/ResearchPage'
import ResearchDetailPage from './pages/ResearchDetailPage'
import SpendPage from './pages/SpendPage'
import GraphPage from './pages/GraphPage'
import SearchPage from './pages/SearchPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/w/:wikiId" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="topics/:slug" element={<TopicDetailPage />} />
        <Route path="sources" element={<SourcesPage />} />
        <Route path="sources/:sourceId" element={<SourceDetailPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="research/:sessionId" element={<ResearchDetailPage />} />
        <Route path="spend" element={<SpendPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="search" element={<SearchPage />} />
      </Route>
    </Routes>
  )
}
