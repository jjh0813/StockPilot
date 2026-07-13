import { useEffect, useRef, useState } from 'react'

import ResultCard from './ResultCard'
import { streamChat } from '../lib/api'

function ChatPanel({ sessionId, initialMessages, seed, hint, onMessagesChange, onInsight }) {
  const [messages, setMessages] = useState(initialMessages || [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const [model, setModel] = useState(() => {
    try { return localStorage.getItem('sp_model') || 'solar' } catch { return 'solar' }
  })
  const listRef = useRef(null)

  // 채팅 목록은 자체 컨테이너 안에서만 스크롤한다(가운데 주식 패널과 분리).
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    // 이미 맨 아래 근처일 때만 즉시 맨 아래로 고정 → 스트리밍 중 화면 흔들림 방지
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (nearBottom) el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    onMessagesChange(messages)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages])

  function patchLastAssistant(patch) {
    setMessages((prev) => {
      const next = [...prev]
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === 'assistant') {
          const delta = typeof patch === 'function' ? patch(next[i]) : patch
          next[i] = { ...next[i], ...delta }
          break
        }
      }
      return next
    })
  }

  async function send(query) {
    if (!query || !query.trim() || busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setInput('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: query },
      { role: 'assistant', status: 'loading', thinking: '분석을 시작할게요...', price: null, answer: '', sources: [], terms: [], usedModel: '', errorMsg: '' },
    ])
    try {
      await streamChat(query, {
        sessionId,
        model,
        onEvent: (e) => {
          if (e.type === 'thinking') {
            patchLastAssistant({ thinking: e.content || '', status: 'loading' })
          } else if (e.type === 'tool') {
            const tr = e.tool_result || {}
            const news = Array.isArray(tr.news) ? tr.news.filter((n) => n && n.url) : []
            const disclosures = Array.isArray(tr.disclosures) ? tr.disclosures : []
            patchLastAssistant({
              price: tr.price || null,
              sources: news,
              status: 'streaming',
            })
            if (tr.price) onInsight?.({ price: tr.price, news, disclosures })
          } else if (e.type === 'token') {
            patchLastAssistant((m) => ({ status: 'streaming', answer: (m.answer || '') + (e.content || '') }))
          } else if (e.type === 'response') {
            const patch = {}
            if (e.content) patch.answer = e.content
            if (e.model) patch.usedModel = e.model
            if (Object.keys(patch).length) patchLastAssistant(patch)
          } else if (e.type === 'glossary') {
            patchLastAssistant({ terms: e.terms || [] })
          } else if (e.type === 'error') {
            patchLastAssistant({ status: 'error', errorMsg: e.error || '오류가 발생했어요.' })
          } else if (e.type === 'done') {
            patchLastAssistant((m) => ({ status: m.status === 'error' ? 'error' : 'done' }))
          }
        },
      })
    } catch {
      patchLastAssistant({
        status: 'error',
        errorMsg: '서버에 연결하지 못했어요. 백엔드(uvicorn)가 켜져 있는지 확인해주세요.',
      })
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  useEffect(() => {
    if (seed && seed.text) send(seed.text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce])

  function handleSubmit(e) {
    e.preventDefault()
    send(input)
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {/* 메시지 영역: 이 컨테이너 안에서만 스크롤 */}
      <div ref={listRef} className="no-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <p className="mt-4 text-center text-neutral-400">
            {hint || '종목명을 입력하면 등락의 원인을 분석해드려요. (예: 삼성전자)'}
          </p>
        )}
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-emerald-500/90 px-4 py-2 text-neutral-950">
                {m.text}
              </div>
            </div>
          ) : (
            <ResultCard key={i} {...m} />
          )
        )}
      </div>

      {/* 입력창: 컬럼 하단에 고정 */}
      <form onSubmit={handleSubmit} className="shrink-0 pt-2">
        <div className="flex items-center gap-2 rounded-2xl border border-white/15 bg-white/10 p-2 backdrop-blur-lg">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
            placeholder="종목이나 궁금한 점을 입력하세요"
            className="flex-1 bg-transparent px-4 py-2 text-white placeholder-neutral-400 outline-none disabled:opacity-50"
          />
          <select
            value={model}
            onChange={(e) => {
              setModel(e.target.value)
              try { localStorage.setItem('sp_model', e.target.value) } catch { /* 무시 */ }
            }}
            disabled={busy}
            title="응답 생성에 사용할 모델 (실패 시 다른 모델로 자동 폴백)"
            className="rounded-xl border border-white/15 bg-white/5 px-2 py-2 text-sm text-neutral-200 outline-none disabled:opacity-50 [&>option]:text-black"
          >
            <option value="solar">Solar</option>
            <option value="gpt-4o-mini">GPT-4o mini</option>
            <option value="gemini-3.1-flash-lite">Gemini</option>
            <option value="claude-haiku">Claude</option>
          </select>
          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-emerald-500 px-5 py-2 font-semibold text-neutral-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? '분석 중' : '전송'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ChatPanel
