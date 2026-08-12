"""OCR 단독 테스트 스크립트 (DB/.env 불필요).

사용법:
    python test_ocr.py <이미지경로>
    예) python test_ocr.py sample.png

이미지 한 장을 PaddleOCR로 읽어서, 인식된 각 줄의 신뢰도와
최종 병합 텍스트를 출력한다. FastAPI 서버나 PostgreSQL 없이 동작한다.
"""

import sys
from pathlib import Path

from PIL import Image

from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.image_extractor import ImageExtractor


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python test_ocr.py <이미지경로>")
        raise SystemExit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"파일을 찾을 수 없습니다: {image_path}")
        raise SystemExit(1)

    print("PaddleOCR 모델 로딩 중... (최초 1회는 모델 다운로드로 시간이 걸립니다)")
    ocr = OcrExtractor()

    # 1) 저수준: 박스별 신뢰도 확인
    with Image.open(image_path) as source:
        image = source.copy()
        elements = ocr.extract(image)

    print("\n=== 인식된 줄(신뢰도) ===")
    for i, el in enumerate(elements, start=1):
        conf = f"{el.confidence:.2f}" if el.confidence is not None else "  -  "
        print(f"[{i:02d}] ({conf}) {el.content}")

    # 2) 고수준: ImageExtractor가 만드는 최종 ExtractResult
    result = ImageExtractor(ocr).extract(str(image_path))
    print("\n=== 최종 추출 결과 ===")
    print(f"extract_method : {result.extract_method}")
    print(f"page_count     : {result.page_count}")
    print(f"char_count     : {result.char_count}")
    print("---- content ----")
    print(result.content)


if __name__ == "__main__":
    main()
