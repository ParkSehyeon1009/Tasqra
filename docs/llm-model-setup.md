# 파인튜닝 LLM 모델 설치

문서 **요약**과 **분류**에 쓰는 모델 둘이다. 각 1.8GB 라 **깃 저장소에 없다**
(GitHub 파일당 한도는 100MB). 파일은 따로 받아서 Ollama 에 등록한다.

| Ollama 이름 | 하는 일 | 실제 문서 성능 |
|---|---|---|
| `Tasqra-summation` | 문서 요약 (2~3문장 200자) | 65.4% |
| `Tasqra-classification` | 문서 유형 분류 (8종) | 88.5% |

베이스는 `Qwen/Qwen2.5-3B-Instruct` (Apache 2.0), 양자화 q4_k_m.
LoRA 어댑터를 태스크별로 따로 학습해 각각 베이스에 병합했다.
**어댑터 둘을 모델 하나로 합칠 수 없어서** 모델이 둘이다.

> 성능 수치는 실제 공공 SI·용역 문서 26건을 배포된 형태(Ollama)로 잰 것이다.
> 요약은 "지시한 형식(2~3문장 200자·한국어·원문에 있는 숫자만)을 지킨 비율",
> 분류는 정확도다. 측정 도구는 AgentLearning 의 `evaluate_summary.py` ·
> `evaluate_category.py` (`--ollama` 옵션).

---

## 1. 모델 파일 받기

관리자에게 `배포모델` 폴더를 요청한다. 구성은 이렇다:

```
배포모델/
├── Tasqra-summation/
│   ├── Modelfile
│   └── qwen2.5-3b-instruct.Q4_K_M.gguf
└── Tasqra-classification/
    ├── Modelfile
    └── qwen2.5-3b-instruct.Q4_K_M.gguf
```

⚠️ 두 GGUF 는 **파일명이 같다.** 한 폴더에 모으면 하나가 다른 하나를 덮어쓴다.
폴더 구조를 그대로 유지할 것.

## 2. Ollama 에 등록

<https://ollama.com/download> 에서 설치한 뒤, 폴더마다 한 번씩 실행한다.
**반드시 그 폴더 안에서** 해야 한다 — `Modelfile` 이
`FROM qwen2.5-3b-instruct.Q4_K_M.gguf` 로 **상대경로**를 쓰기 때문이다.

```
cd Tasqra-summation
ollama create Tasqra-summation -f Modelfile

cd ../Tasqra-classification
ollama create Tasqra-classification -f Modelfile
```

확인:

```
ollama list
ollama run Tasqra-summation "안녕"
```

한국어로 짧게 답하면 정상이다. 등록이 끝나면 받은 폴더는 지워도 된다 —
Ollama 가 자기 저장소로 복사한다.

⚠️ 등록 안 된 이름으로 `ollama run` 을 하면 **인터넷 레지스트리에서 받으려다
실패한다** (`pull model manifest: file does not exist`). 파일이 잘못된 게
아니라 등록이 안 된 것이다.

## 3. 프로젝트 루트에 `.env` 만들기

🔴 **이걸 빠뜨리면 가짜 모델이 돈다.** `docker-compose.yml` 의 기본값이
`USE_FAKE_AI=true` 라서, 없으면 프롬프트를 그대로 되돌려주는 가짜 클라이언트가
붙는다. **에러가 안 나서 알아채기 어렵다** — 화면에 `fake_response_for : ...`
로 나오면 그 상태다.

`Tasqra/.env` (프로젝트 루트. `backend/.env` 와 **다른 파일이다**):

```
USE_FAKE_AI=false
AI_PROVIDER=local
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_MODEL_SUMMARY=Tasqra-summation
AI_MODEL_CATEGORY=Tasqra-classification
AI_MODEL=Tasqra-summation
AI_TIMEOUT_SECONDS=180
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=tasqra
```

### ⚠️ `.env` 가 두 개인 이유

| 파일 | 누가 읽나 | 언제 쓰이나 |
|---|---|---|
| `backend/.env` | 앱(pydantic Settings) | venv 로 uvicorn 을 직접 띄울 때 |
| `Tasqra/.env` | docker compose | 도커로 띄울 때 |

`docker-compose.yml` 의 `environment:` 블록이 `env_file` 보다 **우선한다.**
그래서 `USE_FAKE_AI` 와 `AI_*` 는 **루트 `.env` 에서만** 바꿀 수 있다.
`backend/.env` 에 뭘 써도 도커에서는 안 먹는다.

⚠️ `AI_BASE_URL` 이 `localhost` 면 안 된다. 컨테이너의 localhost 는 컨테이너
자신이라 호스트의 Ollama 에 닿지 않는다. `host.docker.internal` 이어야 한다.

## 4. 컨테이너 올리기

```
docker compose up -d --build
```

`--build` 가 필요하다 — `requirements.txt` 의 `openpyxl` 이 기존 이미지에
없어서 api 가 못 뜬다(`ModuleNotFoundError: No module named 'openpyxl'`).

### 설정이 들어갔는지 확인

```
docker compose exec worker sh -c "env | grep -iE 'fake|ai_'"
```

`USE_FAKE_AI=false` 와 모델 이름 둘이 보여야 한다.

⚠️ `grep AI_` 만 하면 **`USE_FAKE_AI` 가 안 걸린다** — 그 문자열에 `AI_` 가
없다. `-iE 'fake|ai_'` 로 봐야 한다. 이것 때문에 "설정이 다 들어갔다" 고
착각한 적이 있다.

⚠️ **문서 분석은 워커가 한다.** api 만 확인하고 넘어가면, 워커가 다른 설정으로
돌고 있어도 모른다.

---

## 잘 도는지 마지막 확인

문서를 하나 올려 분석 결과를 본다.

- **분류가 `RFP`·`CONTRACT` 같은 영문 코드**인가 (한글이면 프롬프트 불일치)
- **요약이 2~3문장**인가 (4~5문장이면 옛 모델)
- **`fake_response_for` 가 없나**
- **전부 `ETC` 로 떨어지지 않나** (모델 이름이나 배선 문제)

⚠️ 첫 분석은 오래 걸린다. Ollama 가 모델을 메모리에 올리는데, 요약·분류가
서로 다른 모델이라 각각 로딩된다(1.9GB × 2 = 3.8GB).

⚠️ 이미 분석된 문서는 옛 결과가 DB 에 남아 있다. 새 문서로 확인할 것.

---

## 프롬프트를 고칠 때

`backend/app/analyzers/prompts.py` 는 **학습할 때 쓴 프롬프트와 문자 단위로
같아야 한다.** 다르면 파인튜닝 효과가 대부분 사라지는데, 에러가 나지 않아
조용히 성능만 떨어진다.

고쳤다면 AgentLearning 쪽 `src/prompts.py` 도 함께 고치고 확인한다:

```
python src/check_prompts.py
```

그리고 **모델을 다시 학습해야 한다.** 프롬프트만 바꾸면 서비스가 묻는 방식과
모델이 배운 방식이 어긋난다.
