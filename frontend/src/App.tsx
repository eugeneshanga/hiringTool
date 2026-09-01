import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AdminRoute } from './components/AdminRoute'
import { Layout } from './components/Layout'
import { PublicPageLayout } from './components/PublicPageLayout'
import { LoginPage } from './pages/LoginPage'
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
import { PublicApplyPage } from './pages/publicApply/PublicApplyPage'
import { ScheduleApplicationPage } from './pages/publicApply/ScheduleApplicationPage'
import { ApplicationStatusPage } from './pages/publicApply/ApplicationStatusPage'
import { CareersLandingPage } from './pages/publicApply/CareersLandingPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* Public apply flow — no login, see src/pages/publicApply/.
            Candidates never get their own account/login (see
            ApplicationStatusPage - phone/confirmation-code lookup, plus
            onboarding document upload, covers everything they need). */}
        <Route path="/apply/job/:jobId" element={<PublicPageLayout><PublicApplyPage /></PublicPageLayout>} />
        <Route
          path="/apply/schedule/:token"
          element={<PublicPageLayout><ScheduleApplicationPage /></PublicPageLayout>}
        />
        <Route path="/status" element={<PublicPageLayout><ApplicationStatusPage /></PublicPageLayout>} />
        {/* The site's default landing page - see CareersLandingPage's
            docstring. Public, unauthenticated, and deliberately at the
            root path: this app is hosted on its own dedicated subdomain
            (careers.fprecioushomecare.com), so "/" is what a candidate
            sees, not a recruiter dashboard - that's moved to /dashboard
            below. */}
        <Route path="/" element={<PublicPageLayout><CareersLandingPage /></PublicPageLayout>} />
        <Route
          path="/dashboard"
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
    </AuthProvider>
  )
}

export default App
