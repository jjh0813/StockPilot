import BorderGlow from './BorderGlow'
import DisclosureList from './DisclosureList'
import NewsList from './NewsList'
import StockChart from './StockChart'

// 테두리 글로우 공통 설정 (테마: 에메랄드/스카이/바이올렛). glowRadius를 작게 잡아 옆 카드로 번지지 않게.
const GLOW = {
  glowColor: '155 80 60',
  backgroundColor: '#0c1210',
  glowRadius: 16,
  coneSpread: 25,
  edgeSensitivity: 28,
  colors: ['#34d399', '#38bdf8', '#a78bfa'],
}

function formatPct(p) {
  if (p == null) return null
  const a = Math.abs(p).toFixed(2)
  if (p > 0) return { text: `▲ ${a}%`, cls: 'text-red-400' }
  if (p < 0) return { text: `▼ ${a}%`, cls: 'text-blue-400' }
  return { text: `- ${a}%`, cls: 'text-neutral-300' }
}

function formatDate(value) {
  if (!value) return '확인 불가'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function formatDateTime(value) {
  if (!value) return '확인 불가'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function recentTrend(ohlcv = []) {
  const closes = ohlcv
    .map((row) => Number(row.close))
    .filter((value) => Number.isFinite(value) && value !== 0)
  if (closes.length < 2) {
    return { label: '흐름을 판단할 데이터가 부족합니다.', delta: null, tone: 'text-neutral-300' }
  }
  const lookback = Math.min(20, closes.length - 1)
  const base = closes[closes.length - 1 - lookback]
  const latest = closes[closes.length - 1]
  const delta = ((latest - base) / base) * 100
  if (delta >= 3) {
    return { label: '요즘은 올라가는 추세입니다.', delta, tone: 'text-red-300' }
  }
  if (delta <= -3) {
    return { label: '요즘은 내려가는 추세입니다.', delta, tone: 'text-blue-300' }
  }
  return { label: '요즘은 큰 방향성 없이 오르내리는 흐름입니다.', delta, tone: 'text-neutral-300' }
}

function TrendSummary({ price }) {
  const trend = recentTrend(price.ohlcv || [])
  const pct = formatPct(price.change_pct)
  const tradeDays = price.ohlcv?.length || 0
  return (
    <div className="mb-4 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">요즘 흐름</h3>
        <span className="text-xs text-neutral-500">일봉 기준</span>
      </div>
      <p className={`text-lg font-semibold leading-snug ${trend.tone}`}>{trend.label}</p>
      <div className="mt-3 space-y-1 text-xs leading-relaxed text-neutral-400">
        <p>
          차트 기간: {tradeDays ? `최근 ${tradeDays}거래일` : '최근 기간'} · 기준일:{' '}
          {formatDate(price.as_of)}
        </p>
        <p>조회시각: {formatDateTime(price.snapshot_at)}</p>
        {pct && <p>등락률은 전 거래일 대비이며, 현재 {pct.text}입니다.</p>}
        {trend.delta !== null && <p>최근 흐름 변화폭은 약 {trend.delta.toFixed(2)}%입니다.</p>}
      </div>
    </div>
  )
}

function StockPanel({ price, news, disclosures }) {
  if (!price) return null
  const pct = formatPct(price.change_pct)

  return (
    <div className="flex w-full flex-col gap-4">
      {/* 종목별 헤더 */}
      <div className="flex items-baseline gap-3 px-1">
        <span className="text-base font-semibold text-white">{price.name || '종목'}</span>
        {price.current_price != null && (
          <span className="text-sm text-neutral-300">{Number(price.current_price).toLocaleString()}원</span>
        )}
        {pct && <span className={`text-sm font-medium ${pct.cls}`}>{pct.text}</span>}
      </div>

      {/* 위: 차트(크게) + 뉴스 — 각 카드는 콘텐츠 크기로 확정(삐져나옴/겹침 방지) */}
      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-5">
        <BorderGlow {...GLOW} borderRadius={16} className="sm:col-span-3">
          <div className="p-5">
            <StockChart name={price.name} ohlcv={price.ohlcv} changePct={price.change_pct} />
          </div>
        </BorderGlow>
        <BorderGlow {...GLOW} borderRadius={16} className="sm:col-span-2">
          <div className="p-5">
            <TrendSummary price={price} />
            <div className="h-[188px]">
              <NewsList news={news} />
            </div>
          </div>
        </BorderGlow>
      </div>

      {/* 아래: 공시정보 */}
      <BorderGlow {...GLOW} borderRadius={24}>
        <div className="px-6 py-4">
          <DisclosureList disclosures={disclosures} />
        </div>
      </BorderGlow>
    </div>
  )
}

export default StockPanel
