import { useEffect, useRef, useState } from 'react'

import ResultCard from './ResultCard'
import { streamChat } from '../lib/api'

function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  // 세션 유지: 패널이 살아있는 동안 같은 session_id 사용
  const sessionId = useRef('web-' + Math.random().toString(36).slice(2))
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
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
    if (!query.trim() || busy) return
    setBusy(true)
    setInput('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: query },
      {
        role: 'assistant',
        status: 'loading',
        thinking: '분석을 시작할게요...',
        price: null,
        answer: '',
        sources: [],
        errorMsg: '',
      },
    ])

    try {
      await streamChat(query, {
        sessionId: sessionId.current,
        onEvent: (e) => {
          if (e.type === 'thinking') {
            patchLastAssistant({ thinking: e.content || '', status: 'loading' })
          } else if (e.type === 'tool') {
            const tr = e.tool_result || {}
            patchLastAssistant({
              price: tr.price || null,
              sources: Array.isArray(tr.news) ? tr.news.filter((n) => n && n.url) : [],
              status: 'streaming',
            })
          } else if (e.type === 'token') {
            patchLastAssistant((m) => ({
              status: 'streaming',
              answer: (m.answer || '') + (e.content || ''),
            }))
          } else if (e.type === 'response') {
            if (e.content) patchLastAssistant({ answer: e.content })
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
      setBusy(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    send(input)
  }

  return (
    <div className="flex w-full flex-1 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <p className="mt-4 text-center text-neutral-400">
            종목명을 입력하면 등락의 원인을 분석해드려요. (예: 삼성전자)
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
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="sticky bottom-0 pt-2">
        <div className="flex items-center gap-2 rounded-2xl border border-white/15 bg-white/10 p-2 backdrop-blur-lg">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
            placeholder="종목이나 궁금한 점을 입력하세요"
            className="flex-1 bg-transparent px-4 py-2 text-white placeholder-neutral-400 outline-none disabled:opacity-50"
          />
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
