import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import DashboardPage from './pages/DashboardPage'
import TopicsPage from './pages/TopicsPage'
import TopicDetailPage from './pages/TopicDetailPage'

const Todo = ({ name }: { name: string }) => <div className="text-slate-400">{name} — coming in a later task</div>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/w/:wikiId" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="topics/:slug" element={<TopicDetailPage />} />
        <Route path="sources" element={<Todo name="Sources" />} />
        <Route path="sources/:sourceId" element={<Todo name="SourceDetail" />} />
        <Route path="research" element={<Todo name="Research" />} />
        <Route path="research/:sessionId" element={<Todo name="ResearchDetail" />} />
        <Route path="spend" element={<Todo name="Spend" />} />
        <Route path="graph" element={<Todo name="Graph" />} />
        <Route path="search" element={<Todo name="Search" />} />
      </Route>
    </Routes>
  )
}
