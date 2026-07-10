import { useState } from 'react'

import Aurora from './components/Aurora'
import AuthModal from './components/AuthModal'
import ChatPanel from './components/ChatPanel'
import NavBar from './components/NavBar'
import Sidebar from './components/Sidebar'
import { getUsername, loadConversations, saveConversations, setAuth } from './lib/api'

const AURORA_COLORS = ['#052e21', '#34d399', '#065f46']
const ANALYSIS_HINT = '종목명을 입력하면 등락의 원인을 분석해드려요. (예: 삼성전자)'
const GLOSSARY_HINT = '궁금한 투자 용어를 입력해보세요. (예: PER, PBR, 유상증자, 공매도)'

function deriveTitle(messages, fallback) {
  const firstUser = (messages || []).find((m) => m.role === 'user')
  if (firstUser && firstUser.text) return firstUser.text.slice(0, 24)
  return fallback || '새 대화'
}

function App() {
  const [conversations, setConversations] = useState(() =>
    loadConversations().filter((c) => (c.messages || []).length > 0)
  )
  const [activeId, setActiveId] = useState(null)
  const [started, setStarted] = useState(false)
  const [seed, setSeed] = useState(null)
  const [hint, setHint] = useState(ANALYSIS_HINT)
  const [username, setUsername] = useState(() => getUsername() || null)
  const [showAuth, setShowAuth] = useState(false)

  function persist(list) {
    setConversations(list)
    saveConversations(list)
  }

  function newConversation(seedText = '', convHint = ANALYSIS_HINT) {
    const id = 'c-' + Date.now()
    const sessionId = 'web-' + Math.random().toString(36).slice(2)
    const conv = { id, sessionId, title: '새 대화', messages: [], createdAt: Date.now() }
    persist([conv, ...conversations])
    setActiveId(id)
    setStarted(true)
    setHint(convHint)
    setSeed({ text: seedText, nonce: Date.now() })
  }

  // 로고 클릭 → 메인 화면(새 대화 생성 안 함)
  function goHome() {
    setStarted(false)
    setActiveId(null)
    setSeed(null)
  }

  function selectConversation(id) {
    setActiveId(id)
    setStarted(true)
    setSeed(null)
    setHint(ANALYSIS_HINT)
  }

  function handleMessagesChange(id, messages) {
    setConversations((prev) => {
      const next = prev.map((c) =>
        c.id === id ? { ...c, messages, title: deriveTitle(messages, c.title) } : c
      )
      saveConversations(next)
      return next
    })
  }

  function deleteConversation(id) {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id)
      saveConversations(next)
      return next
    })
    if (activeId === id) {
      setActiveId(null)
      setStarted(false)
    }
  }

  function handleNav(kind) {
    if (kind === 'screener') newConversation('오늘 급등하거나 급락한 종목과 그 이유를 알려줘')
    else if (kind === 'glossary') newConversation('', GLOSSARY_HINT)
    else newConversation('', ANALYSIS_HINT) // 종목 분석
  }
  function handleAuthed(name) { setUsername(name); setShowAuth(false) }
  function handleLogout() { setAuth(null); setUsername(null) }

  const active = conversations.find((c) => c.id === activeId) || null

  return (
    <div className="relative min-h-screen bg-black text-neutral-100">
      <div className="fixed inset-0 z-0">
        <Aurora colorStops={AURORA_COLORS} blend={0.5} amplitude={1.0} speed={0.5} />
      </div>

      <NavBar
        username={username}
        onHome={goHome}
        onNav={handleNav}
        onLoginClick={() => setShowAuth(true)}
        onLogout={handleLogout}
      />

      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={() => newConversation('')}
        onDelete={deleteConversation}
      />

      <main className="relative z-10 mx-auto flex min-h-screen max-w-2xl flex-col px-4 pt-28 pb-8">
        {!started || !active ? (
          <div className="flex flex-1 flex-col items-center justify-center text-center animate-fade-in">
            <span className="mb-4 block font-mono text-xs uppercase tracking-[0.35em] text-neutral-400 drop-shadow">
              Stock Research Assistant
            </span>
            <h1 className="mb-3 text-4xl font-semibold tracking-tight text-white drop-shadow-lg sm:text-5xl">
              무슨 일이 있었는지, 물어보세요
            </h1>
            <p className="mb-10 max-w-md text-neutral-300 drop-shadow">
              종목을 검색하면 뉴스·공시를 분석해 등락의 원인을 근거와 함께 설명해드려요.
            </p>
            <button
              type="button"
              onClick={() => newConversation('')}
              className="rounded-full border border-white/15 bg-white/10 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-black/20 backdrop-blur-lg transition-all hover:scale-[1.03] hover:bg-white/20 active:scale-95"
            >
              시작하기 →
            </button>
          </div>
        ) : (
          <div className="flex flex-1 flex-col animate-fade-in-up">
            <ChatPanel
              key={active.id}
              sessionId={active.sessionId}
              initialMessages={active.messages}
              seed={seed}
              hint={hint}
              onMessagesChange={(msgs) => handleMessagesChange(active.id, msgs)}
            />
          </div>
        )}

        <p className="mt-6 text-center font-mono text-xs text-neutral-500 drop-shadow">
          ※ 투자 자문이 아닌 참고용 정보입니다.
        </p>
      </main>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} onAuthed={handleAuthed} />}
    </div>
  )
}

export default App
