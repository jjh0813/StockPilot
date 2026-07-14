import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'

import Aurora from './components/Aurora'
import AuthModal from './components/AuthModal'
import ChatPanel from './components/ChatPanel'
import NavBar from './components/NavBar'
import Sidebar from './components/Sidebar'
import StockPanel from './components/StockPanel'
import {
  bulkSaveConversations,
  deleteConversationRemote,
  fetchConversations,
  getToken,
  getUsername,
  loadConversations,
  saveConversations,
  setAuth,
} from './lib/api'

const AURORA_COLORS = ['#052e21', '#34d399', '#065f46']
const ANALYSIS_HINT = '종목명을 입력하면 등락의 원인을 분석해드려요. (예: 삼성전자)'

function deriveTitle(messages, fallback) {
  const firstUser = (messages || []).find((m) => m.role === 'user')
  if (firstUser && firstUser.text) return firstUser.text.slice(0, 24)
  return fallback || '새 대화'
}

function App() {
  // 로그인 상태로 시작하면 서버에서 불러오므로 빈 배열, 게스트면 로컬에서 복원
  const [conversations, setConversations] = useState(() =>
    getToken() ? [] : loadConversations().filter((c) => (c.messages || []).length > 0)
  )
  const [activeId, setActiveId] = useState(null)
  const [started, setStarted] = useState(false)
  const [seed, setSeed] = useState(null)
  const [username, setUsername] = useState(() => getUsername() || null)
  const [showAuth, setShowAuth] = useState(false)
  const syncTimer = useRef(null)

  // 로그인 상태로 앱을 열면 서버의 내 대화를 불러온다.
  useEffect(() => {
    if (!getToken()) return
    fetchConversations()
      .then((list) => setConversations(Array.isArray(list) ? list : []))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 저장: 로그인=서버(디바운스), 게스트=로컬 (둘을 분리해 서로 안 섞임)
  useEffect(() => {
    if (username && getToken()) {
      clearTimeout(syncTimer.current)
      syncTimer.current = setTimeout(() => {
        bulkSaveConversations(conversations).catch(() => {})
      }, 700)
      return () => clearTimeout(syncTimer.current)
    }
    saveConversations(conversations)
    return undefined
  }, [conversations, username])

  function persist(list) {
    setConversations(list)
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
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, messages, title: deriveTitle(messages, c.title) } : c
      )
    )
  }

  function handleInsight(id, insight) {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, insights: [...(c.insights || []), insight] } : c
      )
    )
  }

  function deleteConversation(id) {
    const next = conversations.filter((c) => c.id !== id)
    setConversations(next)
    if (username && getToken()) deleteConversationRemote(id).catch(() => {})
    if (activeId === id) {
      if (next.length > 0) {
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
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, favorite: !c.favorite } : c)))
  }

  // 로그인: 게스트 대화를 내 계정으로 이전 → 로컬 비우고 서버 목록 로드
  async function handleAuthed(name) {
    setUsername(name)
    setShowAuth(false)
    let list = conversations
    try {
      const guest = conversations
      if (guest.length) await bulkSaveConversations(guest)
      saveConversations([])
      const server = await fetchConversations()
      list = Array.isArray(server) && server.length ? server : guest
      setConversations(list)
    } catch {
      // 서버 실패 시 현재 대화 유지(앱은 계속 동작)
    }
    // 로그인 후: 가장 최신 대화로 바로 이동(의미없는 새 대화 생성 방지). 없으면 시작 화면.
    const pick = list.find((c) => (c.messages || []).length > 0) || list[0]
    if (pick) {
      setActiveId(pick.id)
      setStarted(true)
    } else {
      setActiveId(null)
      setStarted(false)
    }
  }

  // 로그아웃: 화면 비움(게스트 대화는 이미 계정으로 이전됨)
  function handleLogout() {
    setAuth(null)
    setUsername(null)
    setConversations([])
    saveConversations([])
    setActiveId(null)
    setStarted(false)
  }

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
            <h1 className="mb-5 text-4xl font-semibold leading-tight tracking-tight text-white drop-shadow-lg sm:text-5xl">
              <span className="block">차트는 결과를 보여줍니다.</span>
              <span className="block">우리는 이유를 찾아냅니다.</span>
            </h1>
            <p className="mb-10 max-w-lg text-balance text-neutral-300 drop-shadow">
              <span className="block">종목을 검색하면 뉴스와 공시를 분석해</span>
              <span className="block">주가 변동의 원인을 근거와 함께 설명합니다.</span>
            </p>
            <button
              type="button"
              onClick={() => newConversation('')}
              className="rounded-full border border-white/15 bg-white/10 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-black/20 backdrop-blur-lg transition-all hover:scale-[1.03] hover:bg-white/20 active:scale-95"
            >
              분석 시작하기 →
            </button>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 items-stretch gap-6 animate-fade-in-up">
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
