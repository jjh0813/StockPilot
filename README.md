# 스톡파일럿 (Stock Pilot)

> 종목을 검색하면 뉴스·공시를 AI가 분석해 **"지금 이 종목에 무슨 일이 있는지"** 설명해주는 국내 주식 리서치 어시스턴트

가천대 AI 부트캠프 · 생성형 AI 고급과정 프로젝트입니다. 초보 투자자를 위해 흩어진 정보(시세·공시·뉴스)를 한 번의 질문으로 모아, 종목의 최근 등락률을 크게 보여주고, 그 등락의 원인을 뉴스·공시에서 찾아 근거·출처와 함께 설명합니다. 토스증권 'AI 시그널'을 벤치마크로, 루미 에이전트에서 쓴 스택(LangGraph · Solar · FastAPI · SSE)을 그대로 활용해 구현합니다.

> ⚠️ 이 서비스는 투자 자문이 아니라 공개 데이터를 모아 이해를 돕는 참고용 도구입니다. 매수·매도 추천이나 주가 예측은 하지 않으며, 가격 변동의 원인도 '단정'이 아니라 관련 이슈로 제시합니다. 투자 판단과 책임은 사용자에게 있습니다.

---

## ✨ 주요 기능

- **종목 분석**: 종목명을 물으면 시세·뉴스·공시를 모아 최근 이슈를 요약 (등락 폭과 무관하게 항상 동작)
- **등락 표시**: 종목의 상승(▲·빨강)/하락(▼·파랑) 등락률을 크게 표시
- **원인 분석(리즈닝)**: 그 등락의 원인으로 볼 수 있는 이슈를 뉴스·공시에서 찾아 근거·출처와 함께 정리
- **오늘의 급등·급락 종목** *(여유 시)*: 유니버스(시총 상위/관심종목 **10개**)에서 크게 움직인 종목을 등락률·원인과 함께 정리 (배치로 미리 계산해 캐시)
- **개념·공시 설명 (RAG)**: 투자 용어와 사업보고서 리스크 요인을 문서에서 찾아 초보자 눈높이로 설명
- **가격 차트 + 뉴스 마커** *(여유 시)*: 일봉 캔들차트 위에 관련 뉴스가 난 날짜를 마커로 표시 (실시간 틱이 아닌 일봉 기반)
- **SSE 스트리밍**: 답변을 글자 단위로 실시간 출력

---

## 🧰 기술 스택

- **Backend**: Python 3.11, FastAPI, LangGraph, Pydantic, uv
- **LLM / 임베딩**: Upstage Solar (solar-pro3) + Solar Embedding
- **데이터 소스**: 네이버 검색 API(뉴스) · OpenDART(공시) · pykrx(시세·재무)
- **RAG / DB**: Supabase (PostgreSQL + pgvector)
- **스트리밍**: SSE (FastAPI StreamingResponse)
- **Frontend**: React + Vite + React Bits + lightweight-charts(일봉 캔들차트)
- **배포 / CI**: Docker · GCP Compute Engine · GitHub Actions
- **품질**: ruff, pytest, loguru

---

## ✅ 사전 준비물

- **Python 3.11 이상**
- **[uv](https://docs.astral.sh/uv/)** (파이썬 패키지·가상환경 매니저)
- **API 키**
  - Upstage Solar — https://console.upstage.ai/
  - 네이버 검색 API (Client ID / Secret) — https://developers.naver.com/
  - OpenDART 인증키 — https://opendart.fss.or.kr/
  - Supabase 프로젝트 (URL / Key) — https://supabase.com/
  - ※ pykrx는 별도 키가 필요 없습니다.

---

## 🚀 빠른 시작

```bash
# 1) 의존성 설치
uv sync

# 2) 환경변수 설정 (.env.example 복사 후 값 채우기)
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux

# 3) Supabase SQL Editor에서 data/supabase_schema.sql 실행

# 4) 투자 용어 사전 임베딩 적재
uv run python data/scripts/ingest_rag.py

# 4-1) structured glossary exact lookup check
uv run python data/scripts/ingest_rag.py lookup-term --query PER

# 5) 사업보고서 파싱 결과만 먼저 확인(선택)
uv run python data/scripts/ingest_rag.py fetch-dart --company 삼성전자

# 6) 사업보고서를 Supabase에 적재(선택)
uv run python data/scripts/ingest_rag.py ingest-dart --company 삼성전자

# 7) 주요 종목 10개 사업보고서 배치 캐시(선택)
uv run python data/scripts/ingest_rag.py ingest-dart-batch

# 8) 개발 서버 실행
uv run uvicorn app.main:app --reload
```

접속: API 문서 http://localhost:8000/docs

---

## 📄 문서 처리 파이프라인

PDF·이미지는 Upstage Document Parse로 표와 제목 구조를 보존한 Markdown으로
변환한 뒤 RAG에 적재합니다. Document Parse가 실패하면 PDF는 기존 pypdf
파서로 대체할 수 있습니다. Information Extract를 함께 사용하면 주요 사업,
위험요인, 소송·제재, 감사의견을 JSON으로 추출해 `document_facts`에 저장합니다.

```bash
# 파싱·청킹 결과만 로컬에서 확인
uv run python data/scripts/ingest_rag.py prepare-file \
  --path report.pdf --parser upstage --business-report --extract-facts

# Supabase documents + document_facts에 적재
uv run python data/scripts/ingest_rag.py ingest-file \
  --path report.pdf --parser upstage --business-report --extract-facts \
  --source-id report:sample --title "샘플 사업보고서"
```

문서 적재 시에만 Document Parse·Information Extract를 호출하고, 사용자 질문
시에는 미리 저장한 pgvector 청크와 구조화 정보를 조회합니다.

---

## ⚙️ 환경변수

| 변수 | 설명 | 예시 / 기본값 |
| --- | --- | --- |
| `ENVIRONMENT` | 실행 환경 | `development` |
| `DEBUG` | 디버그 모드 | `true` |
| `UPSTAGE_API_KEY` | Upstage Solar API 키 | — |
| `LLM_MODEL` | 사용할 Solar 모델명 | `solar-pro3` |
| `EMBEDDING_MODEL` | 문서·질문 임베딩 모델 | `solar-embedding-1-large` |
| `EMBEDDING_DIMENSION` | pgvector와 맞출 임베딩 차원 | `4096` |
| `NAVER_CLIENT_ID` | 네이버 검색 API Client ID | — |
| `NAVER_CLIENT_SECRET` | 네이버 검색 API Client Secret | — |
| `DART_API_KEY` | OpenDART 인증키 | — |
| `SUPABASE_URL` | Supabase 프로젝트 URL | — |
| `SUPABASE_KEY` | 백엔드 전용 Supabase service-role 키 | — |
| `RAG_CHUNK_SIZE` | 공시 문서 청크 최대 문자 수 | `1600` |
| `RAG_CHUNK_OVERLAP` | 인접 청크 중복 문자 수 | `200` |

> `.env`는 절대 커밋하지 않습니다. (`.gitignore`에 등록)

---

## 📁 프로젝트 구조 (목표)

> 아래는 완성 목표 구조입니다. 킥오프(Day1) 시점에는 뼈대부터 만들고, 로드맵에 따라 하나씩 채워갑니다.

```
StockPilot/
├── app/
│   ├── main.py                # FastAPI 진입점 (앱 생성·미들웨어·라우터 등록)
│   ├── core/
│   │   ├── config.py          # 환경변수 설정 (pydantic-settings)
│   │   └── prompts.py         # 페르소나·분류·리즈닝 프롬프트
│   ├── schemas/
│   │   └── chat.py            # ChatRequest/Response, StreamEvent(SSE)
│   ├── graph/                 # LangGraph 에이전트
│   │   ├── state.py           # State 정의
│   │   ├── nodes.py           # router / rag / tool / response 노드
│   │   ├── edges.py           # 라우팅 로직
│   │   └── graph.py           # 그래프 조립 (싱글톤)
│   ├── tools/
│   │   └── executor.py        # get_stock_price / get_news / get_disclosure /
│   │                          # find_positive_news_stocks / add_watchlist
│   ├── repositories/          # 데이터 접근 계층
│   │   ├── price.py           # pykrx 시세·재무
│   │   ├── news.py            # 네이버 검색 API + 뉴스 선별 파이프라인
│   │   ├── disclosure.py      # OpenDART 공시
│   │   └── rag.py             # Supabase pgvector 검색
│   └── api/routes/
│       ├── chat.py            # /chat, /chat/stream (SSE)
│       └── health.py          # 헬스체크
├── data/
│   ├── glossary.json          # 투자 용어 사전 (RAG 원본)
│   ├── supabase_schema.sql    # documents·pgvector 검색 함수
│   └── scripts/
│       └── ingest_rag.py      # 용어·공시 문서 임베딩 적재
├── frontend/                  # React + React Bits (별도 프론트)
├── tests/                     # pytest
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 📂 파일별 역할

> 현재 전부 **스텁(뼈대)** 상태이며, 개발 단계(1~10단계)에서 순서대로 채웁니다.

**설정 · 공통**

- `pyproject.toml` — 의존성·도구(ruff/pytest) 설정
- `.env.example` — 필요한 환경변수 목록 (실제 키는 각자 `.env`에)
- `app/main.py` — FastAPI 앱 생성·미들웨어·라우터 등록 진입점
- `app/core/config.py` — 환경변수 로드(pydantic-settings), 설정 싱글톤
- `app/core/prompts.py` — 라우터·뉴스분류·리즈닝·페르소나 프롬프트

**스키마**

- `app/schemas/chat.py` — `ChatRequest`/`ChatResponse`, `StreamEvent`(SSE 이벤트 + `to_sse()`)

**에이전트 (LangGraph)**

- `app/graph/state.py` — 노드들이 공유하는 State 정의
- `app/graph/nodes.py` — `router`/`rag`/`tool`/`response` 노드
- `app/graph/edges.py` — 의도에 따른 분기(`route_by_intent`)
- `app/graph/graph.py` — 그래프 조립 + 싱글톤 컴파일

**도구 · 데이터 접근**

- `app/tools/executor.py` — 도구 실행(ReAct). 아래 도구 명세 참고
- `app/repositories/price.py` — pykrx 시세·일봉·재무
- `app/repositories/news.py` — 네이버 검색 API 뉴스 수집 + 룰 필터
- `app/repositories/disclosure.py` — OpenDART 공시 조회
- `app/repositories/rag.py` — Supabase pgvector 문서 검색

**API**

- `app/api/routes/chat.py` — `/chat`(단건), `/chat/stream`(SSE)
- `app/api/routes/health.py` — 헬스체크
- `app/api/routes/__init__.py` — 라우터 취합(`/api/v1`)

**데이터 · 테스트 · 프론트**

- `data/glossary.json` — 투자 용어 사전(RAG 원본)
- `data/scripts/ingest_rag.py` — 용어·공시 임베딩 적재 스크립트
- `tests/test_agent.py`, `tests/test_api.py` —
