import { FormEvent, useEffect, useMemo, useState } from 'react'

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

type ChatMode = 'general' | 'documents'

type DocumentItem = {
  id: number
  title: string
  filename: string
  document_type: string
}

const SESSION_STORAGE_KEY = 'aln-session-id'

function createSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function getSessionId(): string {
  const saved = localStorage.getItem(SESSION_STORAGE_KEY)
  if (saved) {
    return saved
  }

  const created = createSessionId()
  localStorage.setItem(SESSION_STORAGE_KEY, created)
  return created
}

function apiPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/query`
}

function documentsPath(baseUrl: string): string {
  const cleaned = baseUrl.replace(/\/$/, '')
  return `${cleaned}/chat/documents?role=staff`
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

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello. Ask a question about ALN documents or a general topic.',
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<ChatMode>('general')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null)
  const [documentsLoading, setDocumentsLoading] = useState(false)

  const baseUrl = useMemo(() => {
    const fromEnv = import.meta.env.VITE_API_BASE_URL as string | undefined
    return fromEnv && fromEnv.trim() ? fromEnv : 'http://localhost:8000/api'
  }, [])

  const sessionId = useMemo(() => getSessionId(), [])

  useEffect(() => {
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
  }, [baseUrl])

  function resetSession() {
    const nextSession = createSessionId()
    localStorage.setItem(SESSION_STORAGE_KEY, nextSession)
    window.location.reload()
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = input.trim()
    if (!query || isLoading) {
      return
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
        },
        body: JSON.stringify({
          session_id: sessionId,
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

  return (
    <div className="min-h-screen text-slate-100">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-4 rounded-xl border border-white/10 bg-slate-950/50 p-4 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <img
                src="/logo.jpeg"
                alt="ALN logo"
                className="h-11 w-11 rounded-full border border-[var(--aln-secondary)]/60 object-cover"
              />
              <div>
                <h1 className="text-lg font-semibold">ALN Assistant</h1>
                <p className="text-xs text-slate-300">Session: {sessionId}</p>
              </div>
            </div>

            <div className="flex items-center gap-2 rounded-xl border border-white/15 bg-slate-900/70 p-1">
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

        <main className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/40 p-4 backdrop-blur">
          {messages.map((message) => (
            <article
              key={message.id}
              className={`max-w-3xl rounded-xl p-3 ${
                message.role === 'user'
                  ? 'ml-auto bg-[var(--aln-primary)]/80'
                  : 'mr-auto bg-slate-800/80'
              }`}
            >
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
              {message.sources && message.sources.length > 0 ? (
                <div className="mt-3 border-t border-white/10 pt-2 text-xs text-slate-200">
                  <p className="mb-2 font-medium">References</p>
                  <ul className="space-y-1">
                    {message.sources.slice(0, 3).map((source, index) => (
                      <li
                        key={`${message.id}-source-${index}`}
                        className="rounded-lg border border-white/15 bg-slate-900/60 px-2 py-2"
                      >
                        <p className="font-medium text-slate-100">
                          Ref {index + 1}: {source.title}
                        </p>
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

          {isLoading ? <p className="text-sm text-slate-300">Thinking...</p> : null}
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        </main>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
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

          <button
            type="button"
            onClick={resetSession}
            className="rounded-lg border border-white/20 bg-white/5 px-3 py-1 text-slate-200 transition hover:bg-white/10"
          >
            New session
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
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
      </div>
    </div>
  )
}
