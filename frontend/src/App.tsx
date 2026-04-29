import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

type Source = {
  title: string
  type: string
  year?: number | null
  snippet: string
}

type ChatResponse = {
  answer: string
  sources: Source[]
}

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

type HistoryMessage = {
  role: 'user' | 'assistant'
  message: string
  created_at: string
}

type ConversationSummary = {
  session_id: string
  message_count: number
  first_message: string
  created_at: string
  updated_at: string
}

type Conversation = {
  summary: ConversationSummary
  messages: HistoryMessage[]
}

type GroupedHistoryResponse = {
  conversations: Conversation[]
}

type HistoryResponse = GroupedHistoryResponse

type UserProfile = {
  id: number
  name: string
  email: string
}

type AuthResponse = {
  token: string
  user: UserProfile
}

type ChatMode = 'general' | 'documents'

type DocumentItem = {
  id: number
  title: string
  filename: string
  document_type: string
}

type SelectedRef = {
  label: string      // e.g. "Ref 1"
  title: string
  type: string
  year?: number | null
  snippet: string
}

const SESSION_STORAGE_KEY = 'aln-session-id'
const AUTH_TOKEN_STORAGE_KEY = 'aln-auth-token'

function createSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function getOrCreateSessionId(): string {
  const saved = localStorage.getItem(SESSION_STORAGE_KEY)
  if (saved) return saved
  const created = createSessionId()
  localStorage.setItem(SESSION_STORAGE_KEY, created)
  return created
}

function historyToMessages(conversation: Conversation): Message[] {
  return conversation.messages.map((m, i) => ({
    id: `history-${conversation.summary.session_id}-${i}`,
    role: m.role,
    content: m.message,
  }))
}

function getSavedToken(): string {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? ''
}

function apiPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/query`
}

function documentsPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/documents?role=staff`
}

function historyPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/history`
}

function loginPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/auth/login`
}

function registerPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/auth/register`
}

function mePath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/auth/me`
}

function logoutPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/auth/logout`
}

function deleteSessionPath(baseUrl: string, sessionId: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/history/${encodeURIComponent(sessionId)}`
}

function formatDocumentType(type: string): string {
  return type
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function cleanSnippet(snippet: string): string {
  return snippet.replace(/\s+/g, ' ').trim()
}

function buildReferenceTags(sources: Source[] | undefined, limit = 3): string {
  if (!sources || sources.length === 0) {
    return ''
  }

  const tags = sources
    .slice(0, limit)
    .map((_, index) => `[Ref ${index + 1}]`)
    .join(' ')

  return tags ? `\n\n${tags}` : ''
}

function clip(value: string, max = 120): string {
  if (value.length <= max) {
    return value
  }
  return `${value.slice(0, max)}...`
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello. Ask a question about ALN documents or a general topic.',
    },
  ])
  const [historyMessages, setHistoryMessages] = useState<Conversation[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<ChatMode>('general')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null)
  const [documentsLoading, setDocumentsLoading] = useState(false)
  const [token, setToken] = useState<string>(() => getSavedToken())
  const [user, setUser] = useState<UserProfile | null>(null)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  // Session management
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => getOrCreateSessionId())
  const [activeSessionId, setActiveSessionId] = useState<string>(() => getOrCreateSessionId())

  // Ref for auto-scrolling to the latest message
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Delete confirmation: holds the session_id pending deletion, or null
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  // Toast notification
  const [toast, setToast] = useState<string | null>(null)

  // Reference modal
  const [selectedRef, setSelectedRef] = useState<SelectedRef | null>(null)

  const baseUrl = useMemo(() => {
    const fromEnv = import.meta.env.VITE_API_BASE_URL as string | undefined
    return fromEnv && fromEnv.trim() ? fromEnv : 'http://localhost:8000/api'
  }, [])

  const isViewingHistory = activeSessionId !== currentSessionId

  async function loadHistory(authToken: string) {
    const response = await fetch(historyPath(baseUrl), {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    })

    if (!response.ok) {
      throw new Error('Could not load chat history')
    }

    const payload = (await response.json()) as GroupedHistoryResponse
    setHistoryMessages([])
    setHistoryMessages(payload.conversations)
  }

  useEffect(() => {
    let active = true

    async function bootstrapUser() {
      if (!token) {
        setUser(null)
        setHistoryMessages([])
        return
      }

      try {
        const response = await fetch(mePath(baseUrl), {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (!response.ok) {
          throw new Error('Session expired')
        }

        const me = (await response.json()) as UserProfile
        if (!active) {
          return
        }

        setUser(me)
        await loadHistory(token)
      } catch {
        if (!active) {
          return
        }

        setToken('')
        setUser(null)
        setHistoryMessages([])
        localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
      }
    }

    bootstrapUser()

    return () => {
      active = false
    }
  }, [baseUrl, token])

  // Auto-scroll to bottom whenever messages change or loading state toggles
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Auto-dismiss toast after 3 seconds
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (!user || mode !== 'documents' || documents.length > 0) {
      return
    }

    let isMounted = true

    async function loadDocuments() {
      setDocumentsLoading(true)
      try {
        const response = await fetch(documentsPath(baseUrl))
        if (!response.ok) {
          throw new Error(`Could not load documents (${response.status})`)
        }

        const data = (await response.json()) as DocumentItem[]
        if (!isMounted) {
          return
        }

        setDocuments(data)
        if (data.length > 0) {
          setSelectedDocumentId((current) => current ?? data[0].id)
        }
      } catch {
        if (isMounted) {
          setDocuments([])
        }
      } finally {
        if (isMounted) {
          setDocumentsLoading(false)
        }
      }
    }

    loadDocuments()
    return () => {
      isMounted = false
    }
  }, [baseUrl, mode, documents.length, user])

  function startNewChat() {
    const nextSession = createSessionId()
    localStorage.setItem(SESSION_STORAGE_KEY, nextSession)
    setCurrentSessionId(nextSession)
    setActiveSessionId(nextSession)
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: 'Hello. Ask a question about ALN documents or a general topic.',
      },
    ])
    setError(null)
  }

  function resumeSession(conversation: Conversation) {
    setActiveSessionId(conversation.summary.session_id)
    setMessages(historyToMessages(conversation))
    setError(null)
  }

  async function handleDeleteSession(sessionId: string) {
    setDeleteLoading(true)
    try {
      const response = await fetch(deleteSessionPath(baseUrl, sessionId), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || 'Delete failed')
      }

      // Remove from sidebar immediately
      setHistoryMessages((prev) => prev.filter((c) => c.summary.session_id !== sessionId))

      // If the deleted session is the currently open one, start a new chat
      if (activeSessionId === sessionId || currentSessionId === sessionId) {
        startNewChat()
      }

      setToast('Chat deleted successfully')
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not delete chat')
    } finally {
      setDeleteLoading(false)
      setDeleteConfirmId(null)
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (authLoading) {
      return
    }

    setAuthError(null)
    setAuthLoading(true)

    try {
      const endpoint = authMode === 'login' ? loginPath(baseUrl) : registerPath(baseUrl)
      const body =
        authMode === 'login'
          ? { email, password }
          : {
              name,
              email,
              password,
            }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      const payloadText = await response.text()
      const payload = payloadText ? (JSON.parse(payloadText) as AuthResponse | { detail?: string }) : null

      if (!response.ok || !payload || !('token' in payload)) {
        const detail = payload && 'detail' in payload ? payload.detail : null
        throw new Error(detail || 'Authentication failed')
      }

      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, payload.token)
      setToken(payload.token)
      setUser(payload.user)
      setPassword('')
      await loadHistory(payload.token)
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Unknown error'
      setAuthError(text)
    } finally {
      setAuthLoading(false)
    }
  }

  async function handleLogout() {
    try {
      if (token) {
        await fetch(logoutPath(baseUrl), {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
      }
    } catch {
      // Ignore logout network errors; local cleanup still proceeds.
    }

    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    setToken('')
    setUser(null)
    setHistoryMessages([])
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: 'Hello. Ask a question about ALN documents or a general topic.',
      },
    ])
  }


  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = input.trim()
    if (!query || isLoading || !token) {
      return
    }
    // If sending a message to a past session, adopt it as current too
    if (isViewingHistory) {
      setCurrentSessionId(activeSessionId)
      localStorage.setItem(SESSION_STORAGE_KEY, activeSessionId)
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setError(null)
    setIsLoading(true)

    try {
      const response = await fetch(apiPath(baseUrl), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: activeSessionId,
          query,
          mode,
          document_id: mode === 'documents' ? selectedDocumentId : null,
          document_type: null,
          use_latest_document: mode === 'documents',
        }),
      })

      if (!response.ok) {
        const responseText = await response.text()
        throw new Error(responseText || `Request failed (${response.status})`)
      }

      const data = (await response.json()) as ChatResponse
      const referenceTags = buildReferenceTags(data.sources)
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: `${data.answer}${referenceTags}`,
        sources: data.sources,
      }

      setMessages((prev) => [...prev, assistantMessage])
      await loadHistory(token)
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Unknown error'
      setError(text)
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-error-${Date.now()}`,
          role: 'assistant',
          content: 'I could not complete that request. Please try again.',
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  if (!user) {
    return (
      <div className="min-h-screen px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-md rounded-2xl border border-white/10 bg-slate-950/60 p-6 backdrop-blur">
          <div className="mb-5 flex items-center gap-3">
            <img
              src="/logo.jpeg"
              alt="ALN logo"
              className="h-12 w-12 rounded-full border border-[var(--aln-secondary)]/60 object-cover"
            />
            <div>
              <h1 className="text-xl font-semibold">ALN Assistant</h1>
              <p className="text-xs text-slate-300">Sign in to save chats and view your profile history.</p>
            </div>
          </div>

          <div className="mb-4 flex items-center gap-2 rounded-xl border border-white/15 bg-slate-900/70 p-1">
            <button
              type="button"
              onClick={() => setAuthMode('login')}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                authMode === 'login' ? 'bg-[var(--aln-primary)] text-white' : 'text-slate-300 hover:bg-white/10'
              }`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setAuthMode('register')}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                authMode === 'register'
                  ? 'bg-[var(--aln-secondary)] text-slate-950'
                  : 'text-slate-300 hover:bg-white/10'
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleAuthSubmit} className="space-y-3">
            {authMode === 'register' ? (
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="w-full rounded-xl border border-white/20 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none ring-[var(--aln-secondary)] transition focus:ring-2"
                placeholder="Full name"
                required
              />
            ) : null}

            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-xl border border-white/20 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none ring-[var(--aln-secondary)] transition focus:ring-2"
              placeholder="Email"
              required
            />

            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-xl border border-white/20 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none ring-[var(--aln-secondary)] transition focus:ring-2"
              placeholder="Password"
              minLength={8}
              required
            />

            {authError ? <p className="text-sm text-rose-300">{authError}</p> : null}

            <button
              type="submit"
              disabled={authLoading}
              className="w-full rounded-xl bg-[var(--aln-primary)] px-4 py-3 text-sm font-medium text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {authLoading ? 'Please wait...' : authMode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-hidden text-slate-100">
      {/* Grid: never taller than the viewport */}
      <div className="h-full overflow-hidden mx-auto grid w-full max-w-7xl gap-4 px-4 py-6 sm:px-6 lg:grid-cols-[300px_1fr] lg:px-8" style={{ gridTemplateRows: '1fr' }}>
        {/* Sidebar: flex column, fills grid cell, only conversation list scrolls */}
        <aside className="min-h-0 overflow-hidden flex flex-col rounded-2xl border border-white/10 bg-slate-950/60 p-4 backdrop-blur">
          <div className="mb-4 flex items-center gap-3">
            <img
              src="/logo.jpeg"
              alt="ALN logo"
              className="h-12 w-12 rounded-full border border-[var(--aln-secondary)]/60 object-cover"
            />
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">Profile</p>
              <p className="text-sm font-semibold text-slate-100">{user.name}</p>
              <p className="text-xs text-slate-400">{user.email}</p>
            </div>
          </div>

          <div className="mb-4 flex gap-2">
            <button
              type="button"
              onClick={startNewChat}
              className="flex-1 rounded-lg border border-[var(--aln-secondary)]/40 bg-[var(--aln-secondary)]/10 px-3 py-1.5 text-xs font-medium text-[var(--aln-secondary)] transition hover:bg-[var(--aln-secondary)]/20"
            >
              + New Chat
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-lg border border-rose-300/40 bg-rose-500/10 px-3 py-1 text-xs text-rose-200 transition hover:bg-rose-500/20"
            >
              Logout
            </button>
          </div>

          <div className="flex-1 rounded-xl border border-white/10 bg-slate-900/60 p-3 overflow-hidden flex flex-col">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-300">Conversations ({Array.isArray(historyMessages) ? historyMessages.length : 0})</p>
            <div className="flex-1 min-h-0 space-y-1.5 overflow-y-auto pr-1">
              {Array.isArray(historyMessages) && historyMessages.length > 0 ? (
                historyMessages.map((conversation) => {
                  const isActive = activeSessionId === conversation.summary.session_id
                  const formattedDate = new Date(conversation.summary.created_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  } as any)

                  return (
                    <div
                      key={conversation.summary.session_id}
                      className={`rounded-lg border transition group relative ${
                        isActive
                          ? 'border-[var(--aln-secondary)]/50 bg-[var(--aln-secondary)]/10'
                          : 'border-white/10 bg-slate-950/70'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => resumeSession(conversation)}
                        className="w-full px-3 py-2.5 pr-8 text-left transition hover:bg-slate-900/50"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">
                              {formattedDate} • {conversation.summary.message_count} msgs
                            </p>
                            <p className={`text-xs truncate ${ isActive ? 'text-[var(--aln-secondary)]' : 'text-slate-200' }`}>
                              {clip(conversation.summary.first_message, 90)}
                            </p>
                          </div>
                          {isActive ? (
                            <span className="flex-shrink-0 mt-0.5 text-[10px] font-medium text-[var(--aln-secondary)] border border-[var(--aln-secondary)]/40 rounded px-1.5 py-0.5">Active</span>
                          ) : (
                            <span className="flex-shrink-0 mt-0.5 text-[10px] text-slate-400 border border-white/20 rounded px-1.5 py-0.5 hover:border-[var(--aln-secondary)]/40 hover:text-[var(--aln-secondary)] transition">Resume</span>
                          )}
                        </div>
                      </button>

                      {/* Delete button — appears on hover */}
                      <button
                        type="button"
                        title="Delete this chat"
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteConfirmId(conversation.summary.session_id)
                        }}
                        className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 focus:opacity-100 rounded-md p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-all duration-150"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                  )
                })
              ) : (
                <p className="text-xs text-slate-400">No chat history yet. Ask your first question.</p>
              )}
            </div>
          </div>
        </aside>

        {/* ── Confirmation Dialog ── */}
        {deleteConfirmId ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(2,6,23,0.75)', backdropFilter: 'blur(4px)' }}>
            <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
              <div className="mb-1 flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-rose-500/15">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-rose-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                </span>
                <h2 className="text-sm font-semibold text-slate-100">Delete Chat</h2>
              </div>
              <p className="mb-5 mt-2 text-sm text-slate-300">
                Are you sure you want to delete this chat? This action cannot be undone.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setDeleteConfirmId(null)}
                  disabled={deleteLoading}
                  className="flex-1 rounded-xl border border-white/20 bg-slate-800 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteSession(deleteConfirmId)}
                  disabled={deleteLoading}
                  className="flex-1 rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deleteLoading ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Chat panel: flex column, fills grid cell, only <main> scrolls */}
        <section className="min-h-0 overflow-hidden flex flex-col rounded-2xl border border-white/10 bg-slate-950/40 backdrop-blur">
          {/* Header - Fixed */}
          <header className="flex-shrink-0 border-b border-white/10 bg-slate-950/50 p-4 rounded-t-2xl">
            {isViewingHistory ? (
              <div className="mb-3 flex items-center justify-between rounded-lg border border-amber-300/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                <span>Viewing past session — new messages will continue this conversation</span>
                <button
                  type="button"
                  onClick={startNewChat}
                  className="ml-3 rounded-lg border border-amber-300/40 px-2 py-1 text-amber-200 transition hover:bg-amber-500/20"
                >
                  Start fresh
                </button>
              </div>
            ) : null}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-semibold">ALN Assistant</h1>
                <p className="text-xs text-slate-300">Signed in as {user.name}</p>
              </div>

              <div className="flex items-center gap-2 rounded-lg border border-white/15 bg-slate-900/70 p-1">
                <button
                  type="button"
                  onClick={() => setMode('general')}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    mode === 'general'
                      ? 'bg-[var(--aln-primary)] text-white'
                      : 'text-slate-300 hover:bg-white/10'
                  }`}
                >
                  General mode
                </button>
                <button
                  type="button"
                  onClick={() => setMode('documents')}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    mode === 'documents'
                      ? 'bg-[var(--aln-secondary)] text-slate-950'
                      : 'text-slate-300 hover:bg-white/10'
                  }`}
                >
                  Document mode
                </button>
              </div>
            </div>
          </header>

          {/* Messages: THE ONLY scrollable area. flex-1 + min-h-0 is critical */}
          <main className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {messages.map((message) => (
              <article
                key={message.id}
                className={`max-w-3xl rounded-xl p-3 ${
                  message.role === 'user'
                    ? 'ml-auto bg-[var(--aln-primary)]/80'
                    : 'mr-auto bg-slate-800/80'
                }`}
              >
                {/* Render content — [Ref N] tokens become clickable buttons */}
                {(() => {
                  const parts = message.content.split(/(\[Ref \d+\])/g)
                  return (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {parts.map((part, i) => {
                        const match = part.match(/^\[Ref (\d+)\]$/)
                        if (match && message.sources) {
                          const refIndex = parseInt(match[1], 10) - 1
                          const source = message.sources[refIndex]
                          if (source) {
                            return (
                              <button
                                key={i}
                                type="button"
                                onClick={() =>
                                  setSelectedRef({
                                    label: `Ref ${refIndex + 1}`,
                                    title: source.title,
                                    type: source.type,
                                    year: source.year,
                                    snippet: source.snippet,
                                  })
                                }
                                className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold text-[var(--aln-secondary)] bg-[var(--aln-secondary)]/10 border border-[var(--aln-secondary)]/30 hover:bg-[var(--aln-secondary)]/20 hover:border-[var(--aln-secondary)]/60 transition-all duration-150 cursor-pointer mx-0.5"
                                title={`View ${source.title}`}
                              >
                                {part}
                              </button>
                            )
                          }
                        }
                        return <span key={i}>{part}</span>
                      })}
                    </p>
                  )
                })()}
                {message.sources && message.sources.length > 0 ? (
                  <div className="mt-3 border-t border-white/10 pt-2 text-xs text-slate-200">
                    <p className="mb-2 font-medium">References</p>
                    <ul className="space-y-1">
                      {message.sources.slice(0, 3).map((source, index) => (
                        <li
                          key={`${message.id}-source-${index}`}
                          className="rounded-lg border border-white/15 bg-slate-900/60 px-2 py-2"
                        >
                          <p className="font-medium text-slate-100">Ref {index + 1}: {source.title}</p>
                          <p className="text-[11px] uppercase tracking-wide text-slate-300">
                            {formatDocumentType(source.type)}
                            {source.year ? ` • ${source.year}` : ''}
                          </p>
                          {source.snippet ? (
                            <p className="mt-1 text-slate-300">"{cleanSnippet(source.snippet)}"</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </article>
            ))}

            {isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-[var(--aln-secondary)]"></span>
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-[var(--aln-secondary)] [animation-delay:0.15s]"></span>
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-[var(--aln-secondary)] [animation-delay:0.3s]"></span>
                <span>Thinking...</span>
              </div>
            ) : null}
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            {/* Sentinel div — scrolled into view on new messages */}
            <div ref={messagesEndRef} />
          </main>

          {/* Status Bar & Input - Fixed at Bottom */}
          <footer className="flex-shrink-0 border-t border-white/10 bg-slate-950/40 p-4 rounded-b-2xl space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-2 text-slate-300">
                <span className="inline-flex items-center rounded-full border border-white/20 px-3 py-1">
                  Active: {mode === 'general' ? 'General mode' : 'Document mode'}
                </span>
                {mode === 'documents' ? (
                  documentsLoading ? (
                    <span className="rounded-lg border border-white/20 bg-slate-900/80 px-2 py-1 text-slate-200">
                      Loading PDFs...
                    </span>
                  ) : documents.length > 0 ? (
                    <select
                      value={selectedDocumentId ?? ''}
                      onChange={(event) => setSelectedDocumentId(Number(event.target.value))}
                      className="max-w-[22rem] rounded-lg border border-white/20 bg-slate-900/80 px-2 py-1 text-slate-100"
                    >
                      {documents.map((doc) => (
                        <option key={doc.id} value={doc.id}>
                          {doc.title} ({doc.filename})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="rounded-lg border border-amber-300/40 bg-amber-500/10 px-2 py-1 text-amber-200">
                      No PDFs ingested yet
                    </span>
                  )
                ) : null}
              </div>

              <span className="text-slate-400 text-[10px]">
                Session: {activeSessionId.slice(0, 28)}...
              </span>
            </div>

            <form onSubmit={handleSubmit} className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="flex-1 rounded-xl border border-white/20 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none ring-[var(--aln-secondary)] transition focus:ring-2"
                placeholder={mode === 'general' ? 'Ask anything...' : 'Ask from selected PDF...'}
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim() || (mode === 'documents' && !selectedDocumentId)}
                className="rounded-xl bg-[var(--aln-primary)] px-5 py-3 text-sm font-medium text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Send
              </button>
            </form>
          </footer>
        </section>
      </div>

      {/* ── Toast Notification ── */}
      {toast ? (
        <div
          className={`fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl px-5 py-3 text-sm font-medium shadow-2xl border transition-all duration-300 ${
            toast.toLowerCase().includes('deleted') || toast.toLowerCase().includes('success')
              ? 'bg-emerald-900/90 border-emerald-500/40 text-emerald-100'
              : 'bg-rose-900/90 border-rose-500/40 text-rose-100'
          }`}
        >
          {toast.toLowerCase().includes('deleted') || toast.toLowerCase().includes('success') ? '✓ ' : '✕ '}
          {toast}
        </div>
      ) : null}

      {/* ── Reference Detail Modal ── */}
      {selectedRef ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(2,6,23,0.80)', backdropFilter: 'blur(6px)' }}
          onClick={() => setSelectedRef(null)}
        >
          <div
            className="relative w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              type="button"
              onClick={() => setSelectedRef(null)}
              className="absolute right-4 top-4 rounded-lg p-1.5 text-slate-400 hover:bg-slate-700 hover:text-slate-100 transition"
              aria-label="Close"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>

            {/* Header */}
            <div className="mb-4 flex items-start gap-3 pr-8">
              <span className="flex-shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-[var(--aln-secondary)]/15 border border-[var(--aln-secondary)]/30">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-[var(--aln-secondary)]" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
                </svg>
              </span>
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--aln-secondary)] mb-0.5">
                  {selectedRef.label}
                </p>
                <h2 className="text-sm font-semibold text-slate-100 leading-snug">{selectedRef.title}</h2>
                <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">
                  {formatDocumentType(selectedRef.type)}
                  {selectedRef.year ? ` • ${selectedRef.year}` : ''}
                </p>
              </div>
            </div>

            {/* Divider */}
            <div className="mb-4 h-px bg-white/10" />

            {/* Full snippet */}
            <div className="max-h-72 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/60 p-4">
              <p className="text-sm leading-relaxed text-slate-200 whitespace-pre-wrap">
                {selectedRef.snippet ? cleanSnippet(selectedRef.snippet) : 'No content available.'}
              </p>
            </div>

            {/* Footer close */}
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedRef(null)}
                className="rounded-xl border border-white/20 bg-slate-800 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
