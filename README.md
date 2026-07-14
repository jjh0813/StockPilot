# 스톡파일럿 (StockPilot)

> 종목을 검색하면 뉴스·공시를 AI가 분석해 **"지금 이 종목에 무슨 일이 있는지"** 를 근거·출처와 함께 설명해주는 국내 주식 리서치 어시스턴트

가천대 AI 부트캠프 · 생성형 AI 고급과정 프로젝트입니다. 초보 투자자를 위해 흩어진 정보(시세·뉴스·공시·재무·투자용어)를 한 번의 질문으로 모아, 종목의 최근 등락률을 크게 보여주고 그 등락의 원인을 뉴스·공시에서 찾아 설명합니다. LangGraph · Solar · FastAPI · SSE 스택으로 구현했습니다.

> ⚠️ 본 서비스는 투자 자문이 아니라 공개 데이터를 모아 이해를 돕는 참고용 도구입니다. 매수·매도 추천이나 주가 예측은 하지 않으며, 가격 변동의 원인도 '단정'이 아니라 관련 이슈로 제시합니다. 투자 판단과 책임은 사용자에게 있습니다.

📘 **사용 설명서(전체 기능 + 사용법 + 실행 가이드): [`docs/StockPilot_사용설명서.pdf`](docs/StockPilot_사용설명서.pdf)**

---

## ✨ 주요 기능

- **종목 분석**: 종목명을 물으면 시세·뉴스·공시를 모아 최근 등락률(▲빨강/▼파랑)을 크게 보여주고, 등락의 원인 이슈를 근거·출처와 함께 정리 (등락 폭과 무관하게 항상 동작)
- **가운데 인사이트 패널**: 일봉 차트 + 관련 뉴스 + 최근 공시 카드를 한 화면에 표시 (여러 종목이면 위→아래로 순서대로 쌓임)
- **상승률 상위 종목(스크리너)**: "요즘 오르는 종목" 질문 시 유니버스(대형주 22종목)의 실제 등락률을 조회해 상승률 상위 5개를 정리하고, 종목별 차트를 하나씩 순차 스트리밍
- **공시 조회**: 종목의 최근 전자공시(OpenDART) 목록 제공
- **투자 용어 설명(RAG)**: 용어·개념을 문서/사전에서 찾아 초보자 눈높이로 설명. 답변 속 등록 용어에 밑줄 + 클릭 시 정의 툴팁(나무위키식 각주)
- **로그인 & 사용자별 대화 저장**: 회원가입/로그인 시 대화를 서버(Supabase)에 사용자별 저장. 게스트 대화 이관, 다른 기기 동기화, 로그인 시 최신 대화로 진입
- **대화 목록 관리**: 새 대화·전환·삭제·즐겨찾기(★, 우클릭 메뉴)
- **LLM 모델 선택 + 자동 폴백**: Solar / GPT-4o mini / Gemini / Claude 선택. 실패 시 다른 모델 → 기본 템플릿으로 단계적 폴백, 사용 모델 표시
- **가드레일**: 매수·매도 추천, 목표주가·주가 예측, 프롬프트 인젝션 차단
- **SSE 스트리밍**: 답변을 글자 단위로 실시간 출력 (입력 시에만 하단 스크롤, 응답 중 화면 고정)
- **관측(LLMOps)**: Langfuse 트레이싱, 도구 타임아웃+재시도, 네이버 429 방어(동시성 제한+백오프)

---

## 🧰 기술 스택

- **Backend**: Python 3.11, FastAPI, LangGraph, Pydantic, uv
- **LLM / 라우팅**: Upstage Solar(solar-pro3) + Solar Embedding, LiteLLM(모델 라우팅/폴백)
- **데이터 소스**: 네이버 검색 API(뉴스) · OpenDART(공시) · pykrx(시세·재무)
- **RAG / DB / 인증**: Supabase(PostgreSQL + pgvector), JWT
- **관측**: Langfuse
- **스트리밍**: SSE (FastAPI StreamingResponse)
- **Frontend**: React + Vite + React Bits, 일봉 차트
- **배포 / CI**: Docker · GCP Compute Engine · GitHub Actions
- **품질**: ruff, pytest, loguru

---

## ✅ 사전 준비물

- **Python 3.11 이상**, **[uv](https://docs.astral.sh/uv/)**, **Node.js 18+**(프론트엔드)
- **필수 API 키**
  - Upstage Solar — https://console.upstage.ai/
  - 네이버 검색 API(Client ID/Secret) — https://developers.naver.com/
  - OpenDART 인증키 — https://opendart.fss.or.kr/
  - Supabase 프로젝트(URL/Key) — https://supabase.com/
- **선택**
  - OpenAI / Gemini / Anthropic 키 — 모델 라우팅·폴백용
  - Langfuse 키 — 트레이싱
  - KRX 계정(data.krx.co.kr) — 재무지표(PER/PBR 등). 없어도 시세·차트·분석은 정상 동작

---

## 🚀 빠른 시작

### 1) 백엔드
```bash
uv sync                                  # 의존성 설치
copy .env.example .env                   # (mac/Linux: cp) 후 키 채우기
# Supabase SQL Editor에서 data/supabase_schema.sql 실행 (테이블·검색함수·conversations 생성)
uv run python data/scripts/ingest_rag.py # 투자용어 사전 임베딩 적재
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
```

### 2) 프론트엔드
```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

### 3) (선택) Docker로 한번에
```bash
docker compose up --build                # 백엔드 + 프론트(nginx) 컨테이너
```

> `.env`는 절대 커밋되지 않습니다(`.gitignore` 등록). API 키·KRX 자격증명은 각자 `.env`에만 둡니다.

---

## 🧠 아키텍처 (LangGraph)

```
사용자 질문
   └─ router (규칙 + Solar LLM 라우터)  →  intent = chat / rag / tool  (+ screen, tool_mode)
        ├─ rag      : 용어·공시 문서 pgvector 검색
        ├─ tool     : 시세(get_stock_price) · 뉴스(get_news) · 공시(get_disclosure)
        │             · 상승률 스크리너(find_positive_news_stocks) · 관심종목(add_watchlist)
        └─ response : 근거 데이터로만 답변 생성(Solar/LiteLLM 폴백) → SSE 스트리밍
```

- 스크리너는 유니버스의 **실제 등락률을 조회해 상승률 순 상위**를 뽑고, 종목별 상세 패널은 라우트에서 하나씩 순차 조회·전송(선조회 지연 방지).
- 뉴스 매칭은 우선주(예: 삼성전자우) 오매칭을 차단하고, 상승 목록은 실제 주가 상승분만 포함.

---

## 🔌 API 요약 (`/api/v1`)

| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| POST | `/auth/register`, `/auth/login` | 회원가입 / 로그인 → JWT 발급 |
| POST | `/chat/stream` | 질문 → SSE로 분석·답변 스트리밍 |
| POST | `/chat/` | 단건(비스트리밍) 응답 |
| GET/PUT/POST/DELETE | `/conversations` | 사용자별 대화 조회·저장·일괄저장·삭제 |
| GET/POST/DELETE | `/watchlist` | 관심종목 조회·추가·삭제 |
| GET | `/health` | 헬스체크 |

전체 스펙은 실행 후 `http://localhost:8000/docs` 참고.

---

## ⚙️ 환경변수 (요약)

| 변수 | 설명 |
| --- | --- |
| `UPSTAGE_API_KEY`, `LLM_MODEL` | Solar API 키 / 모델명(solar-pro3) |
| `NAVER_CLIENT_ID/SECRET` | 네이버 검색 API(뉴스) |
| `DART_API_KEY` | OpenDART 공시 |
| `SUPABASE_URL/KEY` | Supabase(RAG·인증·대화 저장) |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES` | 인증 토큰 |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | (선택) 모델 폴백 |
| `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` | (선택) 트레이싱 |
| `KRX_ID`, `KRX_PW` | (선택) 재무지표(PER/PBR) |
| `LLM_GUARDRAILS_ENABLED` | 가드레일 on/off |

전체 목록은 `.env.example` 참고.

---

## 🚢 배포

- **Docker Multi-stage**: 프론트(빌드→nginx) + 백엔드 컨테이너, `docker-compose`로 실행
- **GCP Compute Engine**: docker compose 배포, 외부 HTTP 접속
- **GitHub Actions**: CI(pytest·프론트 빌드) + CD(GCE 자동 배포). 시크릿/API 키는 GitHub Secrets·`.env`로 분리

---

## 🧪 테스트

```bash
uv run pytest          # 백엔드 유닛/통합 테스트
```

---

## 📁 프로젝트 구조

```
StockPilot/
├── app/
│   ├── main.py                # FastAPI 진입점
│   ├── core/                  # config · prompts · llm(라우팅/폴백) · guardrails · observability
│   ├── graph/                 # LangGraph: state · nodes(router/rag/tool/response) · edges · graph
│   ├── tools/executor.py      # 도구 실행(시세/뉴스/공시/스크리너/관심종목) + 타임아웃·재시도
│   ├── repositories/          # price(pykrx) · news(네이버) · disclosure(DART) · rag · glossary · conversations · users · watchlist
│   ├── schemas/               # chat(SSE) · tool_results · auth 등
│   └── api/routes/            # auth · chat · conversations · watchlist · health
├── data/
│   ├── glossary.json          # 투자 용어 사전(RAG 원본)
│   ├── supabase_schema.sql    # 테이블 · pgvector 검색함수 · conversations
│   └── scripts/ingest_rag.py  # 용어·공시 임베딩 적재
├── docs/StockPilot_사용설명서.pdf  # 사용 설명서 + 실행 가이드
├── frontend/                  # React + Vite UI
├── tests/                     # pytest
├── Dockerfile · docker-compose.yml · deploy/
├── .env.example · pyproject.toml · README.md
```
