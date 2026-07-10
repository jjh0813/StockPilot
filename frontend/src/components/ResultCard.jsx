function formatPct(p) {
  const a = Math.abs(p).toFixed(2)
  if (p > 0) return `▲ ${a}%`
  if (p < 0) return `▼ ${a}%`
  return `― ${a}%`
}
function colorFor(p) {
  if (p > 0) return 'text-red-400'
  if (p < 0) return 'text-blue-400'
  return 'text-neutral-300'
}
function dirWord(p) {
  if (p > 0) return '상승'
  if (p < 0) return '하락'
  return '보합'
}

function ResultCard({ status, thinking, price, answer, sources, errorMsg }) {
  const pct = price && price.change_pct !== null && price.change_pct !== undefined
    ? Number(price.change_pct)
    : null
  const hasPct = pct !== null && !Number.isNaN(pct)
  const showThinking = status === 'loading' && !answer

  return (
    <div className="w-full rounded-2xl border border-white/15 bg-white/5 p-6 backdrop-blur-lg">
      {showThinking && (
        <div className="flex items-center gap-2 text-neutral-300">
          <span className="flex gap-1">
            <span className="think-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
            <span className="think-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
            <span className="think-dot h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
          <span>{thinking || '생각 중입니다...'}</span>
        </div>
      )}

      {status === 'error' && <p className="text-red-300">{errorMsg}</p>}

      {hasPct && (
        <div className="mb-1 flex items-baseline gap-3">
          <span className="text-lg text-neutral-200">{price.name || '종목'}</span>
          <span className={`text-4xl font-bold ${colorFor(pct)}`}>
            {formatPct(pct)}
          </span>
          <span className="text-sm text-neutral-400">{dirWord(pct)}</span>
        </div>
      )}
      {price && price.current_price != null && (
        <p className="mb-4 text-neutral-300">
          현재가 {Number(price.current_price).toLocaleString()}원
        </p>
      )}

      {answer && (
        <div className="whitespace-pre-wrap leading-relaxed text-neutral-100">{answer}</div>
      )}

      {sources && sources.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-neutral-400">출처</p>
          <div className="flex flex-wrap gap-2">
            {sources.map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noreferrer"
                title={s.title || ''}
                className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 transition-colors hover:border-emerald-400/50 hover:text-white"
              >
                {s.source || '기사'} ↗
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default ResultCard
