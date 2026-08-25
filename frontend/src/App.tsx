import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { CandidateAuthProvider } from './candidateAuth/CandidateAuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AdminRoute } from './components/AdminRoute'
import { CandidateProtectedRoute } from './components/CandidateProtectedRoute'
import { Layout } from './components/Layout'
import { CandidateLayout } from './components/CandidateLayout'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { HomePage } from './pages/HomePage'
import { ProfilePage } from './pages/ProfilePage'
import { JobsPage } from './pages/JobsPage'
import { JobDetailLayout } from './pages/JobDetailLayout'
import { JobDetailsPage } from './pages/JobDetailsPage'
import { JobMeetingStagesPage } from './pages/JobMeetingStagesPage'
import { StageEditorLayout } from './pages/StageEditorLayout'
import { StageSchedulePage } from './pages/StageSchedulePage'
import { StagePreScreenPage } from './pages/StagePreScreenPage'
import { StageOnboardingPage } from './pages/StageOnboardingPage'
import { OrganizationLayout } from './pages/OrganizationLayout'
import { OrganizationSettingsPage } from './pages/OrganizationSettingsPage'
import { OrganizationUsersPage } from './pages/OrganizationUsersPage'
import { OrganizationBlocklistPage } from './pages/OrganizationBlocklistPage'
import { CandidatesPage } from './pages/CandidatesPage'
import { CandidateDetailsPage } from './pages/CandidateDetailsPage'
import { CandidateLoginPage } from './pages/candidate/CandidateLoginPage'
import { CandidateRegisterPage } from './pages/candidate/CandidateRegisterPage'
import { CandidateHomePage } from './pages/candidate/CandidateHomePage'
import { PublicApplyPage } from './pages/publicApply/PublicApplyPage'
import { ScheduleApplicationPage } from './pages/publicApply/ScheduleApplicationPage'
import { ApplicationStatusPage } from './pages/publicApply/ApplicationStatusPage'

function App() {
  return (
    <AuthProvider>
      <CandidateAuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/apply/login" element={<CandidateLoginPage />} />
          <Route path="/apply/register" element={<CandidateRegisterPage />} />
          {/* Public apply flow — no login, see src/pages/publicApply/. Distinct
              path segments from /apply, /apply/login, /apply/register above
              (candidate-account territory) so there's no collision. */}
          <Route path="/apply/job/:jobId" element={<PublicApplyPage />} />
          <Route path="/apply/schedule/:token" element={<ScheduleApplicationPage />} />
          <Route path="/status" element={<ApplicationStatusPage />} />
          <Route
            path="/apply"
            element={
              <CandidateProtectedRoute>
                <CandidateLayout>
                  <CandidateHomePage />
                </CandidateLayout>
              </CandidateProtectedRoute>
            }
          />
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
            path="/profile"
            element={
              <ProtectedRoute>
                <Layout>
                  <ProfilePage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/organization"
            element={
              <ProtectedRoute>
                <AdminRoute>
                  <Layout>
                    <OrganizationLayout />
                  </Layout>
                </AdminRoute>
              </ProtectedRoute>
            }
          >
            <Route index element={<OrganizationSettingsPage />} />
            <Route path="users" element={<OrganizationUsersPage />} />
            <Route path="blocklist" element={<OrganizationBlocklistPage />} />
          </Route>
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
            <Route path="pre-screen" element={<StagePreScreenPage />} />
            <Route path="onboarding" element={<StageOnboardingPage />} />
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
      </CandidateAuthProvider>
    </AuthProvider>
  )
}

export default App
