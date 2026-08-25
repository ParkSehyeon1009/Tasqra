import hashlib
from dataclasses import replace
from io import BytesIO

from PIL import Image

from app.extractors.layout import LayoutElement
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.preprocessing import normalize_input_image


class EmbeddedImageOcrCache:
    """한 문서 안에서 동일한 내부 이미지의 OCR 추론 결과를 재사용한다."""

    def __init__(self) -> None:
        self._results: dict[
            str,
            tuple[Image.Image, tuple[LayoutElement, ...]],
        ] = {}
        self.hit_count = 0

    def extract(
        self,
        image_bytes: bytes,
        ocr: OcrExtractor,
    ) -> tuple[Image.Image, list[LayoutElement]]:
        cache_key = hashlib.sha256(image_bytes).hexdigest()
        cached = self._results.get(cache_key)
        if cached is not None:
            self.hit_count += 1
            image, elements = cached
            return image, [replace(element) for element in elements]

        with Image.open(BytesIO(image_bytes)) as source_image:
            image = normalize_input_image(source_image)
        elements = ocr.extract(image, normalize_orientation=False)
        snapshots = tuple(replace(element) for element in elements)
        self._results[cache_key] = (image, snapshots)
        return image, [replace(element) for element in snapshots]
