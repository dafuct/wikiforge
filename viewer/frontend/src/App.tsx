import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'

const Todo = ({ name }: { name: string }) => <div className="text-slate-400">{name} — coming in a later task</div>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/w/:wikiId" element={<Layout />}>
        <Route index element={<Todo name="Dashboard" />} />
        <Route path="topics" element={<Todo name="Topics" />} />
        <Route path="topics/:slug" element={<Todo name="TopicDetail" />} />
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
