import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'

import Aurora from './components/Aurora'
import AuthModal from './components/AuthModal'
import ChatPanel from './components/ChatPanel'
import NavBar from './components/NavBar'
import Sidebar from './components/Sidebar'
import StockPanel from './components/StockPanel'
import { getUsername, loadConversations, saveConversations, setAuth } from './lib/api'

const AURORA_COLORS = ['#052e21', '#34d399', '#065f46']
const ANALYSIS_HINT = '종목명을 입력하면 등락의 원인을 분석해드려요. (예: 삼성전자)'

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
  const [username, setUsername] = useState(() => getUsername() || null)
  const [showAuth, setShowAuth] = useState(false)

  function persist(list) {
    setConversations(list)
    saveConversations(list)
  }

  function newConversation(seedText = '') {
    const id = 'c-' + Date.now()
    const sessionId = 'web-' + Math.random().toString(36).slice(2)
    const conv = { id, sessionId, title: '새 대화', messages: [], insights: [], favorite: false, createdAt: Date.now() }
    persist([conv, ...conversations])
    setActiveId(id)
    setStarted(true)
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

  // 종목 질문마다 결과를 누적한다 → 같은 대화창에서 다른 종목을 물으면
  // 기존 종목 카드는 그대로 두고 아래에 새 종목 차트/뉴스/공시가 쌓인다.
  function handleInsight(id, insight) {
    setConversations((prev) => {
      const next = prev.map((c) =>
        c.id === id ? { ...c, insights: [...(c.insights || []), insight] } : c
      )
      saveConversations(next)
      return next
    })
  }

  function deleteConversation(id) {
    const next = conversations.filter((c) => c.id !== id)
    persist(next)
    if (activeId === id) {
      if (next.length > 0) {
        // 즐겨찾기 우선 정렬 기준으로 남은 대화 중 하나로 이동
        const sorted = [...next].sort((a, b) => (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0))
        setActiveId(sorted[0].id)
        setStarted(true)
      } else {
        setActiveId(null)
        setStarted(false)
      }
    }
  }

  function toggleFavorite(id) {
    persist(conversations.map((c) => (c.id === id ? { ...c, favorite: !c.favorite } : c)))
  }

  function handleAuthed(name) { setUsername(name); setShowAuth(false) }
  function handleLogout() { setAuth(null); setUsername(null) }

  const active = conversations.find((c) => c.id === activeId) || null
  const insights = active?.insights || []
  const hasInsight = insights.length > 0

  return (
    <div className="relative min-h-screen bg-black text-neutral-100">
      <div className="fixed inset-0 z-0">
        <Aurora colorStops={AURORA_COLORS} blend={0.5} amplitude={1.0} speed={0.5} />
      </div>

      <NavBar
        username={username}
        onHome={goHome}
        onLoginClick={() => setShowAuth(true)}
        onLogout={handleLogout}
      />

      <Sidebar
        visible={started}
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={() => newConversation('')}
        onDelete={deleteConversation}
        onToggleFavorite={toggleFavorite}
      />

      <main
        className={
          started && active
            ? 'relative z-10 flex h-screen flex-col overflow-hidden px-4 pb-4 pt-24 lg:pl-72 lg:pr-8'
            : 'relative z-10 mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-8 pt-28'
        }
      >
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
          <div className="flex min-h-0 flex-1 items-stretch gap-6 animate-fade-in-up">
            {/* 왼쪽(가운데) 인사이트 패널: 자체적으로 세로 스크롤 → 오른쪽 채팅과 스크롤 분리.
                같은 대화에서 종목을 여러 번 물으면 카드가 위에서 아래로 쌓인다. */}
            <AnimatePresence>
              {hasInsight && (
                <motion.div
                  key="insight"
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: '62%', opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                  className="hidden min-h-0 overflow-hidden lg:block"
                >
                  <div className="no-scrollbar flex h-full w-full flex-col gap-8 overflow-y-auto px-2 pb-2 pt-1">
                    {insights.map((ins, i) => (
                      <StockPanel
                        key={i}
                        price={ins.price}
                        news={ins.news}
                        disclosures={ins.disclosures}
                      />
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <motion.div
              layout
              className={`flex min-h-0 w-full max-w-2xl flex-1 flex-col ${hasInsight ? 'mx-auto lg:mx-0' : 'mx-auto'}`}
            >
              <ChatPanel
                key={active.id}
                sessionId={active.sessionId}
                initialMessages={active.messages}
                seed={seed}
                hint={ANALYSIS_HINT}
                onMessagesChange={(msgs) => handleMessagesChange(active.id, msgs)}
                onInsight={(insight) => handleInsight(active.id, insight)}
              />
            </motion.div>
          </div>
        )}

        <p className="mt-3 shrink-0 text-center font-mono text-xs text-neutral-500 drop-shadow">
          ※ 투자 자문이 아닌 참고용 정보입니다.
        </p>
      </main>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} onAuthed={handleAuthed} />}
    </div>
  )
}

export default App
