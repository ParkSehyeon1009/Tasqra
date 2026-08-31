# Tasqra

문서를 업로드하면 OCR과 AI가 내용을 추출·분석하고, 프로젝트의 태스크와 일정으로 연결하는 문서 기반 협업 도구입니다.

## 개발 전 필독

- [개발·협업 가이드](./DEVELOPMENT_GUIDE.md)

모든 설계와 구현 판단은 **DocFlow 통합 기획안 v0.3**을 최우선 기준으로 합니다. 기존 OCR 미니프로젝트의 코드는 완성된 설계가 아니라 재사용 가능한 자산으로 취급합니다.

## Docker로 개발 환경 실행

Docker Desktop(Compose 포함)을 실행한 뒤 저장소 루트에서 실행합니다.

```bash
docker compose up
```

- 접속: http://localhost:5173 (처음에는 회원가입 후 로그인)
- 개인 `backend/.env` 없이도 예제 설정으로 실행됩니다. 기본은 Fake AI·Fake 임베딩이며 리랭커는 꺼져 있어 실제 AI 모델 서버가 필요하지 않습니다.
- 최초 실행은 이미지 빌드와 패키지 다운로드가 필요합니다. 첫 문서 업로드 때 OCR 모델 다운로드로 시간이 걸릴 수 있습니다.
- 백그라운드 실행은 `docker compose up -d`, 종료는 `docker compose stop`입니다. 기존 이미지가 있는 상태에서 의존성이나 Dockerfile이 바뀌었다면 `docker compose up --build`로 다시 빌드합니다.
- API 시작 시 DB 마이그레이션이 자동 실행됩니다. `docker compose down -v`는 DB 볼륨까지 삭제하므로 기존 데이터가 있으면 사용하지 마세요.

실제 모델이 준비되면 `docker-compose.yml` 맨 위의 `x-ai-environment`에서 `USE_FAKE_AI`를 `"false"`로 바꾸고 모델 주소·이름·컨텍스트를 맞춘 뒤 `docker compose up -d`로 적용합니다. 이 공통 설정은 API와 worker 양쪽에 적용되며 `backend/.env`보다 우선합니다. 임베딩·리랭커는 별도 준비가 필요하므로 AI 연결과 함께 무조건 켜지 않습니다.

이 구성은 로컬 개발용입니다. 외부 서버 배포에는 비밀키·DB 암호·포트 노출 등 별도 보안 설정이 필요합니다. 상세한 분석 설정은 [AI 분석 v2 적용 안내](./docs/ai-analysis-v2.md)를 참고하세요.
