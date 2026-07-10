function NavBar({ username, onHome, onNav, onLoginClick, onLogout }) {
  const menu = [
    { key: 'analysis', label: '종목 분석' },
    { key: 'screener', label: '급등·급락' },
    { key: 'glossary', label: '용어 사전' },
  ]
  return (
    <div className="fixed inset-x-0 top-4 z-20 px-4">
      <nav className="mx-auto flex h-14 max-w-5xl items-center justify-between rounded-2xl border border-white/15 bg-white/10 px-6 shadow-lg shadow-black/20 backdrop-blur-lg">
        <button onClick={onHome} className="font-mono text-lg font-semibold tracking-tight text-white">
          Stock<span className="text-emerald-400">Pilot</span>
        </button>
        <div className="flex items-center gap-2 sm:gap-4 text-sm">
          {menu.map((m) => (
            <button
              key={m.key}
              onClick={() => onNav(m.key)}
              className="rounded-lg px-2 py-1.5 text-neutral-300 transition-colors hover:text-white"
            >
              {m.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-white/15" />
          {username ? (
            <>
              <span className="hidden text-neutral-300 sm:inline">{username}님</span>
              <button onClick={onLogout} className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-neutral-200 transition-colors hover:text-white">
                로그아웃
              </button>
            </>
          ) : (
            <button onClick={onLoginClick} className="rounded-lg bg-emerald-500 px-4 py-1.5 font-semibold text-neutral-950 transition-colors hover:bg-emerald-400">
              로그인
            </button>
          )}
        </div>
      </nav>
    </div>
  )
}

export default NavBar
