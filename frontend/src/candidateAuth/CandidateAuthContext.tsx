import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { candidateApi, getCandidateToken, setCandidateToken } from '../api/candidateClient'
import type { CandidateAccount } from '../api/types'

interface CandidateAuthContextValue {
  candidate: CandidateAccount | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: {
    first_name: string
    last_name: string
    email: string
    phone?: string
    password: string
  }) => Promise<void>
  logout: () => void
}

const CandidateAuthContext = createContext<CandidateAuthContextValue | undefined>(undefined)

export function CandidateAuthProvider({ children }: { children: ReactNode }) {
  const [candidate, setCandidate] = useState<CandidateAccount | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getCandidateToken()
    if (!token) {
      setLoading(false)
      return
    }
    candidateApi
      .me()
      .then(setCandidate)
      .catch(() => setCandidateToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    const { access_token, candidate } = await candidateApi.login(email, password)
    setCandidateToken(access_token)
    setCandidate(candidate)
  }

  async function register(data: {
    first_name: string
    last_name: string
    email: string
    phone?: string
    password: string
  }) {
    const { access_token, candidate } = await candidateApi.register(data)
    setCandidateToken(access_token)
    setCandidate(candidate)
  }

  function logout() {
    setCandidateToken(null)
    setCandidate(null)
  }

  return (
    <CandidateAuthContext.Provider value={{ candidate, loading, login, register, logout }}>
      {children}
    </CandidateAuthContext.Provider>
  )
}

export function useCandidateAuth() {
  const ctx = useContext(CandidateAuthContext)
  if (!ctx) throw new Error('useCandidateAuth must be used within CandidateAuthProvider')
  return ctx
}
