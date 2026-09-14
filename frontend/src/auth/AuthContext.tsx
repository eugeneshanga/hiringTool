import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from '../api/client'
import type { User } from '../api/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  // True right after an API call comes back 401 on an already-logged-in
  // session (an expired or otherwise invalidated token) - LoginPage shows a
  // "please sign in again" message while this is set, distinguishing it
  // from landing there fresh/by choice. Cleared on the next successful login.
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  updateUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  // Registered once, for the lifetime of the app - see httpClient.ts's
  // setUnauthorizedHandler. Firing this just clears `user`; that alone is
  // enough for every ProtectedRoute already in the tree to redirect to
  // /login on its very next render, without this needing to know about
  // routing at all.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      setSessionExpired(true)
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  async function login(email: string, password: string) {
    const { access_token, user } = await api.login(email, password)
    setToken(access_token)
    setUser(user)
    setSessionExpired(false)
  }

  function logout() {
    setToken(null)
    setUser(null)
    setSessionExpired(false)
  }

  // Lets a page that edits the logged-in user's own info (e.g. Profile) push
  // the saved result back into context, so the header/menu reflect it
  // immediately without a full re-fetch.
  function updateUser(updated: User) {
    setUser(updated)
  }

  return (
    <AuthContext.Provider value={{ user, loading, sessionExpired, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
