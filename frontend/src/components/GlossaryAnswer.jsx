import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// LLM 답변을 마크다운으로 렌더링하면서, RAG 용어 사전에 있는 단어에는
// 밑줄 + 클릭 시 나무위키식 각주(정의 툴팁)를 붙인다.
function GlossaryAnswer({ text, terms }) {
  const [openKey, setOpenKey] = useState(null)
  const rootRef = useRef(null)

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpenKey(null)
    }
    document.addEventListener('pointerdown', onDocClick)
    return () => document.removeEventListener('pointerdown', onDocClick)
  }, [])

  if (!text) return null

  const list = (terms || []).filter((t) => t && t.matched_text)
  // 긴 표기부터 매칭해 짧은 표기가 긴 표기 안쪽을 먼저 잘라먹지 않게 한다.
  const sorted = [...list].sort((a, b) => b.matched_text.length - a.matched_text.length)
  const re = sorted.length
    ? new RegExp(`(${sorted.map((t) => escapeRegExp(t.matched_text)).join('|')})`, 'g')
    : null

  // 렌더 1회 내에서 각주 버튼 key를 고유하게 만들기 위한 카운터
  let seq = 0

  // 문자열을 용어 기준으로 쪼개, 매칭된 부분만 클릭 각주 버튼으로 바꾼다.
  function renderString(str, keyBase) {
    if (!re) return str
    const parts = str.split(re)
    return parts.map((part, i) => {
      const term = sorted.find((t) => t.matched_text === part)
      if (!term) return <span key={`${keyBase}-t${i}`}>{part}</span>
      const key = `${term.term}-${seq++}`
      const isOpen = openKey === key
      return (
        <span key={key} className="relative inline-block">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setOpenKey(isOpen ? null : key)
            }}
            className="cursor-pointer text-emerald-300 underline decoration-dotted decoration-emerald-400/50 underline-offset-4 transition-colors hover:text-emerald-200"
          >
            {part}
          </button>
          {isOpen && (
            <span className="absolute left-0 top-full z-30 mt-2 w-64 max-w-[16rem] rounded-xl border border-white/15 bg-neutral-900/95 p-3 text-left text-sm normal-case leading-relaxed text-neutral-200 shadow-xl backdrop-blur">
              <span className="mb-1 block text-xs font-semibold text-emerald-300">{term.term}</span>
              <span className="block text-neutral-300">{term.definition}</span>
              {term.example && (
                <span className="mt-2 block text-xs text-neutral-500">예) {term.example}</span>
              )}
            </span>
          )}
        </span>
      )
    })
  }

  // 각 요소의 "직접 자식" 중 문자열만 용어 처리한다.
  // 중첩 요소(굵게/기울임/링크 등)는 각자의 override에서 이미 처리되므로 그대로 통과.
  function decorate(children, keyBase) {
    const arr = Array.isArray(children) ? children : [children]
    return arr.map((child, i) =>
      typeof child === 'string' ? (
        <span key={`${keyBase}-s${i}`}>{renderString(child, `${keyBase}-${i}`)}</span>
      ) : (
        child
      )
    )
  }

  const components = {
    p: ({ children }) => (
      <p className="mb-3 leading-relaxed last:mb-0">{decorate(children, 'p')}</p>
    ),
    li: ({ children }) => <li className="leading-relaxed">{decorate(children, 'li')}</li>,
    ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
    ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
    strong: ({ children }) => (
      <strong className="font-semibold text-white">{decorate(children, 'strong')}</strong>
    ),
    em: ({ children }) => <em className="italic">{decorate(children, 'em')}</em>,
    del: ({ children }) => <del className="opacity-70">{decorate(children, 'del')}</del>,
    h1: ({ children }) => (
      <h1 className="mb-2 mt-4 text-lg font-semibold text-white first:mt-0">{decorate(children, 'h1')}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-2 mt-4 text-base font-semibold text-white first:mt-0">{decorate(children, 'h2')}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-1 mt-3 text-sm font-semibold text-neutral-100 first:mt-0">{decorate(children, 'h3')}</h3>
    ),
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-emerald-300 underline decoration-emerald-400/40 underline-offset-2 hover:text-emerald-200"
      >
        {decorate(children, 'a')}
      </a>
    ),
    blockquote: ({ children }) => (
      <blockquote className="mb-3 border-l-2 border-white/20 pl-3 text-neutral-300 last:mb-0">
        {children}
      </blockquote>
    ),
    // react-markdown v9: 인라인 코드는 <code>, 블록 코드는 <pre><code>로 온다.
    code: ({ children }) => (
      <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em] text-emerald-200">
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="mb-3 overflow-x-auto rounded-lg bg-black/40 p-3 font-mono text-xs text-neutral-200 last:mb-0">
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="mb-3 overflow-x-auto last:mb-0">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border border-white/15 px-2 py-1 text-left font-semibold text-neutral-200">
        {decorate(children, 'th')}
      </th>
    ),
    td: ({ children }) => (
      <td className="border border-white/10 px-2 py-1 text-neutral-100">{decorate(children, 'td')}</td>
    ),
  }

  return (
    <div ref={rootRef} className="relative text-neutral-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

export default GlossaryAnswer
