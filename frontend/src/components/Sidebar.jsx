import LineSidebar from './LineSidebar'

function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }) {
  const items = conversations.map((c) => c.title || '새 대화')
  const activeIndex = conversations.findIndex((c) => c.id === activeId)
  const active = conversations.find((c) => c.id === activeId)

  return (
    <aside className="fixed bottom-4 left-4 top-24 z-20 hidden w-64 flex-col rounded-2xl border border-white/15 bg-white/10 p-4 shadow-lg shadow-black/20 backdrop-blur-lg lg:flex">
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm font-semibold text-neutral-200">내 대화</span>
        <button
          onClick={onNew}
          className="rounded-lg bg-emerald-500 px-2 py-1 text-xs font-semibold text-neutral-950 transition-colors hover:bg-emerald-400"
        >
          + 새 대화
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <p className="px-1 py-4 text-xs text-neutral-400">아직 대화가 없어요.</p>
        ) : (
          <LineSidebar
            key={`${conversations.length}-${activeIndex}`}
            items={items}
            accentColor="#34d399"
            textColor="#c4c4c4"
            markerColor="#6c6c6c"
            markerLength={28}
            fontSize={0.95}
            itemGap={16}
            defaultActive={activeIndex >= 0 ? activeIndex : null}
            onItemClick={(index) => onSelect(conversations[index].id)}
          />
        )}
      </div>

      {active && (
        <button
          onClick={() => onDelete(active.id)}
          className="mt-3 flex items-center justify-center gap-1 rounded-xl border border-red-400/30 bg-red-500/10 py-2 text-xs font-medium text-red-300 transition-colors hover:bg-red-500/20"
        >
          🗑 현재 대화 삭제
        </button>
      )}
    </aside>
  )
}

export default Sidebar
