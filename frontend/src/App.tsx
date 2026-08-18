import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { HomePage } from './pages/HomePage'
import { JobsPage } from './pages/JobsPage'
import { JobDetailLayout } from './pages/JobDetailLayout'
import { JobDetailsPage } from './pages/JobDetailsPage'
import { JobMeetingStagesPage } from './pages/JobMeetingStagesPage'
import { StageEditorLayout } from './pages/StageEditorLayout'
import { StageSchedulePage } from './pages/StageSchedulePage'
import { JobScreeningQuestionsPage } from './pages/JobScreeningQuestionsPage'
import { CandidatesPage } from './pages/CandidatesPage'
import { CandidateDetailsPage } from './pages/CandidateDetailsPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
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
          <Route path="screening-questions" element={<JobScreeningQuestionsPage />} />
        </Route>
        <Route
          path="/jobs/:jobId/meeting-stages/:templateId"
          element={
            <ProtectedRoute>
              <Layout>
                <StageEditorLayout />
              </Layout>
            </ProtectedRoute>
          }
        >
          <Route index element={<StageSchedulePage />} />
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
        <Route
          path="/candidates/:candidateId"
          element={
            <ProtectedRoute>
              <Layout>
                <CandidateDetailsPage />
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
