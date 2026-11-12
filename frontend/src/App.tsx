import { Route, Routes } from 'react-router'
import DashboardPage from './pages/DashboardPage.tsx'

// Top-level routes. New pages (e.g. trend deep-dives) get added here.
function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
    </Routes>
  )
}

export default App
