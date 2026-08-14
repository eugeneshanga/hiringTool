import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { HomePage } from './pages/HomePage'
import { JobsPage } from './pages/JobsPage'
import { JobDetailLayout } from './pages/JobDetailLayout'
import { JobDetailsPage } from './pages/JobDetailsPage'
import { JobMeetingStagesPage } from './pages/JobMeetingStagesPage'
import { CandidatesPage } from './pages/CandidatesPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout>
                <HomePage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/jobs"
          element={
            <ProtectedRoute>
              <Layout>
                <JobsPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/jobs/:jobId"
          element={
            <ProtectedRoute>
              <Layout>
                <JobDetailLayout />
              </Layout>
            </ProtectedRoute>
          }
        >
          <Route index element={<JobDetailsPage />} />
          <Route path="meeting-stages" element={<JobMeetingStagesPage />} />
        </Route>
        <Route
          path="/candidates"
          element={
            <ProtectedRoute>
              <Layout>
                <CandidatesPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
