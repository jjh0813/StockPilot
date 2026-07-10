import { useState } from 'react'

import AuthModal from './components/AuthModal'
import ChatPanel from './components/ChatPanel'
import LetterGlitch from './components/LetterGlitch'
import NavBar from './components/NavBar'
import { getUsername, setAuth } from './lib/api'

const GLITCH_COLORS = ['#404040', '#525252', '#737373', '#34d399']

function App() {
  const [started, setStarted] = useState(false)
  const [username, setUsername] = useState(() => getUsername() || null)
  const [showAuth, setShowAuth] = useState(false)

  function handleAuthed(name) {
    setUsername(name)
    setShowAuth(false)
  }
  function handleLogout() {
    setAuth(null)
    setUsername(null)
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-black text-neutral-100">
      <div className="absolute inset-0">
        <LetterGlitch
          glitchColors={GLITCH_COLORS}
          glitchSpeed={50}
          centerVignette={true}
          outerVignette={true}
          smooth={true}
        />
      </div>

      <NavBar
        username={username}
        onLoginClick={() => setShowAuth(true)}
        onLogout={handleLogout}
      />

      <main className="relative z-10 mx-auto flex min-h-screen max-w-2xl flex-col px-4 pt-28 pb-8">
        {!started ? (
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
              onClick={() => setStarted(true)}
              className="rounded-full border border-white/15 bg-white/10 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-black/20 backdrop-blur-lg transition-all hover:scale-[1.03] hover:bg-white/20 active:scale-95"
            >
              시작하기 →
            </button>
          </div>
        ) : (
          <div className="flex flex-1 flex-col animate-fade-in-up">
            <ChatPanel />
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
