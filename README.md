# Tasqra

공공 SI 문서를 업로드해 OCR과 AI로 구조화하고, 검토 가능한 근거를 검색·금액 관리·업무 관리·산출물 작성으로 연결하는 문서 기반 협업 도구입니다.

## 해결하려는 문제

공공 SI 프로젝트에서는 제안요청서, 과업지시서, 계약서처럼 형식이 다른 문서를 반복해서 읽고 핵심 정보와 근거를 찾아야 합니다. Tasqra는 문서 입력부터 OCR 검수, 분석 결과 검토, 검색과 후속 업무까지 한 프로젝트 안에서 이어지도록 구성했습니다.

- 문서 형식과 스캔 품질이 달라도 검수 가능한 텍스트로 정리합니다.
- 요약만 보여주는 데 그치지 않고 원문 근거를 검색하고 다시 확인할 수 있게 합니다.
- AI가 추출한 금액·결정사항·일정은 사람의 검토를 거쳐 활용합니다.
- 문서에서 확인한 정보를 대시보드, 보드, 산출물 흐름과 연결합니다.

## 핵심 기능

| 영역 | 현재 구현 범위 |
|---|---|
| 프로젝트 협업 | 회원가입·로그인, 프로젝트 생성, 구성원 초대, OWNER·EDITOR·VIEWER 권한 관리 |
| 문서 처리 | PDF·DOCX·HWPX·PNG·JPG/JPEG 업로드, Celery 기반 비동기 추출, 처리 상태와 실패 재시도 |
| OCR 검수 | OCR 박스 텍스트·좌표 수정, 생성·삭제·제외, 선택 재OCR, 병합·되돌리기, 최종 본문 재구성 |
| AI 문서 분석 | 요약, 문서 분류, 결정사항, 일정, 계약 계열 문서의 기한 있는 액션아이템 추출 |
| 검색과 질의응답 | 의미·키워드·하이브리드 검색, 선택적 리랭킹, 프로젝트 문서 근거 기반 질의응답 |
| 업무 현황 | 대시보드, 사용자가 직접 관리하는 액션 태스크 칸반 보드와 활동 기록 |
| 금액 관리 | 문서 금액 별도 추출, 검토·수정·승인·거절·취소, 승인된 값의 검산과 집계 |
| 산출물 | 승인된 분석 결과를 반영한 산출물 생성, 목록·다운로드·생성 이력 관리 |

> 액션아이템 **추출**과 액션 태스크 **자동 생성**은 다릅니다. 현재 기본 분석은 계약·계약변경 문서에서 원문 근거가 있는 이행 의무 후보를 추출하며, 이를 AI가 자동으로 보드 태스크로 생성한다고 설명하지 않습니다.

## 주요 사용자 흐름

1. 회원가입·로그인 후 프로젝트를 만들고 구성원을 초대합니다.
2. 문서를 업로드하면 API가 작업을 등록하고 worker가 텍스트 추출과 OCR을 수행합니다.
3. 사용자는 OCR 박스와 재구성된 본문을 검수합니다.
4. 문서 분석으로 요약·분류·결정사항·일정·액션아이템 또는 금액을 추출합니다.
5. 분석 결과와 원문 근거를 확인하고 필요한 항목을 승인·수정·거절합니다.
6. 프로젝트 검색·질의응답, 대시보드, 보드, 금액 집계와 산출물에서 검토된 정보를 활용합니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Frontend | React 19, Vite 8, React Router 7, TanStack React Query 5, Axios |
| Backend | Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, pgvector, Redis 7 |
| Async | Celery, Redis broker |
| Document/OCR | PyMuPDF, python-docx, PaddleOCR, OpenCV, Pillow |
| AI/Search | OpenAI-compatible API, Ollama, sentence-transformers, PEFT LoRA, 임베딩·리랭커 |
| Output | openpyxl, WeasyPrint |
| Infra | Docker Compose |

## 시스템 구조

```text
Browser (React/Vite)
  └─ frontend/src/api
       └─ FastAPI router
            └─ Service
                 └─ Repository (SQLAlchemy)
                      └─ PostgreSQL + pgvector

Document upload / analysis
  └─ FastAPI ── Redis ── Celery worker
                         ├─ document extraction / PaddleOCR
                         ├─ AI analysis
                         └─ chunking / embedding / indexing
```

Docker Compose는 `frontend`, `api`, `worker`, `db`, `redis` 서비스를 구성합니다. API 시작 시 Alembic 마이그레이션이 적용되고, 문서 처리와 분석은 worker가 비동기로 수행합니다.

## Docker로 개발 환경 실행

Docker Desktop(Compose 포함)을 실행한 뒤 저장소 루트에서 준비합니다.

```bash
cp backend/.env.example backend/.env
docker compose up
```

- 접속: http://localhost:5173 (처음에는 회원가입 후 로그인)
- 기본은 Fake AI·Fake 임베딩이며 리랭커는 꺼져 있어 실제 AI 모델 서버 없이 화면과 기본 흐름을 확인할 수 있습니다.
- 최초 실행은 이미지 빌드와 패키지 다운로드가 필요합니다. 첫 문서 업로드 때 OCR 모델을, 실제 로컬 임베딩을 켰을 때 베이스 모델을 내려받아 시간이 걸릴 수 있습니다.
- 백그라운드 실행은 `docker compose up -d`, 종료는 `docker compose stop`입니다. 의존성이나 Dockerfile이 바뀌었다면 `docker compose up --build`로 다시 빌드합니다.
- API 시작 시 DB 마이그레이션이 자동 실행됩니다. `docker compose down -v`는 DB 볼륨까지 삭제하므로 기존 데이터가 있으면 사용하지 마세요.

실제 파인튜닝 LLM은 저장소에 포함하지 않습니다. [파인튜닝 LLM 모델 설치](./docs/llm-model-setup.md)에 따라 Ollama에 모델을 등록하고, 저장소 루트 `.env`에서 Compose가 참조하는 AI 설정을 변경한 뒤 `docker compose up -d --build`로 적용합니다. 임베딩과 리랭커는 별도 설정이므로 AI 연결과 함께 무조건 켜지 않습니다.

### 공개 환경변수

공개 저장소에는 **환경변수 이름과 안전한 예시만** 두고 실제 API 키, 운영 DB 암호, JWT 비밀값은 커밋하지 않습니다. 전체 항목과 기본값은 [`backend/.env.example`](./backend/.env.example)을 기준으로 합니다.

| 목적 | 주요 환경변수 |
|---|---|
| DB·인증 | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `JWT_SECRET_KEY` |
| AI 실행 | `USE_FAKE_AI`, `AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_MODEL_SUMMARY`, `AI_MODEL_CATEGORY`, `AI_MODEL_DECISION`, `AI_MODEL_SCHEDULE` |
| 임베딩 | `USE_FAKE_EMBEDDING`, `EMBEDDING_PROVIDER`, `EMBEDDING_BASE_MODEL`, `EMBEDDING_ADAPTER_PATH`, `EMBEDDING_MAX_SEQ_LENGTH` |
| 리랭킹 | `RERANK_ENABLED`, `RERANK_BASE_MODEL`, `RERANK_ADAPTER_PATH`, `RERANK_CANDIDATE_POOL` |
| 문서·OCR | `UPLOAD_DIR`, `MAX_FILE_SIZE_MB`, `MAX_PAGES`, `MAX_EXTRACTED_CHARS`, `OCR_TEXT_DET_MAX_SIDE_LEN` |
| 실행 장치 | `MODEL_DEVICE` |

- `backend/.env`: 애플리케이션·문서 처리·임베딩·리랭커 설정을 둡니다.
- 루트 `.env`: `docker-compose.yml`의 `${...}`로 주입하는 DB·AI 설정을 둡니다. Compose의 `environment` 항목은 `backend/.env`보다 우선합니다.
- 실제 모델을 켤 때는 API와 worker가 같은 AI·임베딩 설정을 사용해야 합니다.

이 구성은 로컬 개발용입니다. 외부 서버 배포에는 비밀키·DB 암호·CORS·포트 노출을 별도로 설정해야 합니다.

## 테스트와 평가

### 코드 검증 명령

백엔드 테스트는 `backend/requirements-dev.txt`의 pytest를 사용합니다.

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

프론트엔드에는 별도 자동화 테스트 스크립트가 없으며 lint와 production build를 검증합니다.

```bash
cd frontend
npm install
npm run lint
npm run build
```

### 검색 평가 결과

여기서 `R@k`는 **첫 정답의 순위가 `k` 이하이면 성공으로 계산하는 `accuracy@k`/`HitRate@k`**입니다. 정답 전체 중 검색된 비율을 계산하는 표준 `recall@k`와 항상 같은 지표는 아닙니다.

| 평가 | 입력 규모 | 환경·후보 범위 | 실제 결과 | 근거 |
|---|---:|---|---:|---|
| 김보현 5차 임베딩 모델 비교 | 문서 10개, 청크 649개, 질의 133개 | CPU, float32, 전체 청크 검색 | BGE-m3-ko `R@1 56.4%`, `R@5 76.7%` | [`RAG_임베딩모델_비교분석표.md`](https://github.com/bobohyeon/deliver/blob/docs/design-artifacts-0805/관리/RAG_임베딩모델_비교분석표.md) |
| 박세현 하드네거티브 임베딩 평가 | 질의 214개, 후보 평균 50개 | 같은 문서의 후보로 제한 | `R@1 63.6%`, `R@5 92.1%` | [`hard negertive.png`](https://github.com/bobohyeon/deliver/blob/docs/design-artifacts-0805/참고/세현님_테스트결과/hard%20negertive.png) |
| 박세현 하드네거티브 임베딩 평가 | 질의 214개, 청크 1,339개 | 전체 코퍼스 검색 | `R@1 36.9%`, `R@5 74.3%` | 같은 원본 |

평가셋과 후보 범위가 다르므로 각 행의 수치를 직접적인 전후 개선율로 해석하지 않습니다. 프로젝트의 검색 품질 목표는 **전체 검색 `R@1 90%`**이며, 위 표의 실제 측정값과 분리해 관리합니다.

## 프로젝트 구조

```text
Tasqra/
├─ backend/
│  ├─ app/
│  │  ├─ api/routes/       # FastAPI 엔드포인트
│  │  ├─ services/         # 업무 규칙과 트랜잭션
│  │  ├─ repositories/     # SQLAlchemy 데이터 접근
│  │  ├─ models/           # DB 모델
│  │  ├─ schemas/          # 요청·응답 계약
│  │  ├─ extractors/       # PDF·DOCX·HWPX·이미지 추출
│  │  ├─ analyzers/        # 문서 분석기
│  │  └─ worker.py         # Celery 비동기 작업
│  ├─ migrations/          # Alembic 마이그레이션
│  ├─ tests/               # pytest 테스트
│  └─ adapters/            # 임베딩·리랭커 LoRA 어댑터
├─ frontend/
│  ├─ src/api/             # HTTP API 클라이언트
│  ├─ src/pages/           # 라우트 단위 화면
│  ├─ src/features/        # 기능별 UI
│  └─ src/components/      # 공통 컴포넌트
├─ docs/                   # AI·모델·권한 관련 문서
├─ docker-compose.yml
└─ README.md
```

## 팀 Tasqra

| 팀원 | 담당 영역 |
|---|---|
| 최재정 | 계정·권한, 프로젝트, 문서 입력·처리, OCR 검수, 일괄 처리 |
| 김보현 | 검색·근거, 금액, 가시성, 산출물 |
| 박세현 | LLM,임베딩,리랭커 모델 파인튜닝, 분석, AI 추천 |

## 개발 문서

- [개발·협업 가이드](./DEVELOPMENT_GUIDE.md)
- [파인튜닝 LLM 모델 설치](./docs/llm-model-setup.md)
- [AI 분석 v2 적용 안내](./docs/ai-analysis-v2.md)

현재 동작과 설정은 최신 `main`의 코드와 `docker-compose.yml`을 기준으로 판단합니다. 이전 OCR 프로젝트의 코드는 완성된 설계가 아니라 재사용 가능한 참고 자산으로 취급합니다.
