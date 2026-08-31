"""OCR 추출 -> 분류/요약 통합 테스트 스크립트 (DB 불필요).

사용법 (backend 폴더에서 실행):
    python test_analyze.py <문서경로>
    예) python test_analyze.py sample.png
        python test_analyze.py sample.pdf

실제 서비스와 같은 배선(dependencies.py)을 그대로 써서
  1) 확장자에 맞는 추출기로 텍스트를 뽑고
  2) summary / category 분석기를 로컬 LLM으로 돌린 뒤
  3) provider·모델명·토큰·지연시간을 함께 출력한다.
FastAPI 서버나 PostgreSQL 없이 동작한다.
"""

import asyncio
import sys
from pathlib import Path

from app.analyzers.protocol import AnalyzeResult
from app.core.config import settings
from app.dependencies import (
    get_ai_client,
    get_analyzer_registry,
    get_extractor_registry,
)


def print_analysis(title: str, result: AnalyzeResult) -> None:
    print(f"\n=== {title} ===")
    print(f"provider    : {result.provider}")
    print(f"model       : {result.model_name}")
    print(f"tokens      : in={result.tokens_in} out={result.tokens_out}")
    print(f"latency     : {result.latency_ms} ms")
    print("---- result ----")
    for key, value in result.result.items():
        print(f"{key}: {value}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python test_analyze.py <문서경로>")
        raise SystemExit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        raise SystemExit(1)

    print("--- 설정 ---")
    print(f"USE_FAKE_AI       : {settings.USE_FAKE_AI}")
    print(f"AI_PROVIDER       : {settings.AI_PROVIDER}")
    print(f"AI_BASE_URL       : {settings.AI_BASE_URL}")
    print(f"AI_MODEL          : {settings.AI_MODEL}")
    print(f"AI_MAX_INPUT_CHARS: {settings.AI_MAX_INPUT_CHARS}")
    print(f"주입된 AI 클라이언트: {type(get_ai_client()).__name__}")

    # --- 1) 텍스트 추출 -----------------------------------------------------
    file_type = file_path.suffix.lstrip(".").lower()
    extractor = get_extractor_registry().get(file_type)

    print(f"\n추출 중... (file_type={file_type})")
    extracted = extractor.extract(str(file_path))

    print("\n=== 추출 결과 ===")
    print(f"extract_method : {extracted.extract_method}")
    print(f"page_count     : {extracted.page_count}")
    print(f"char_count     : {extracted.char_count}")
    if extracted.char_count > settings.AI_MAX_INPUT_CHARS:
        print(
            f"주의: 추출 텍스트가 AI_MAX_INPUT_CHARS"
            f"({settings.AI_MAX_INPUT_CHARS}자)를 넘어 요약은 구간별 처리하고 분류는 앞·중간·뒤를 표본으로 분석합니다."
        )
    print("---- content (앞 500자) ----")
    print(extracted.content[:500])

    if not extracted.content.strip():
        print("\n추출된 텍스트가 없어 분석을 건너뜁니다.")
        return

    # --- 2) 분석 (분류 + 요약) ----------------------------------------------
    analyzers = get_analyzer_registry()

    print("\n분석 중... (로컬 LLM은 CPU에서 수십 초 걸릴 수 있습니다)")
    category_result = await analyzers["category"].analyze(extracted.content)
    print_analysis("카테고리 분류", category_result)

    summary_result = await analyzers["summary"].analyze(extracted.content)
    print_analysis("요약", summary_result)


if __name__ == "__main__":
    asyncio.run(main())
