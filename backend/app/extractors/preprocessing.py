# =============================================================================
# 이 파일의 책임: OCR 정확도를 높이기 위한 이미지 전처리 단계들을 정의하고,
#   여러 단계를 순서대로 실행하는 파이프라인 함수 preprocess() 를 제공한다.
#   각 단계는 Image -> Image 순수 함수이며 상태를 갖지 않는다.
# 다른 파일과의 관계: ocr_extractor.py 가 OCR 실행 직전에 preprocess() 를 호출한다.
#   전처리 강도는 엔진마다 다르게 적용해야 하므로 프리셋으로 분리한다 —
#   PaddleOCR(딥러닝)은 과한 이진화가 손해일 수 있고, Tesseract(전통 알고리즘)는
#   이진화·노이즈 제거의 이득이 크다.
# Spring 비교: 여러 전처리기를 순서대로 통과시키는 FilterChain 과 같은 구조.
#   각 단계가 독립 함수라서 순서 변경·추가·제거가 자유롭다.
# =============================================================================

from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageOps


# OCR은 해상도에 민감하다. 이 폭보다 작으면 확대한다.
MIN_WIDTH = 1000
# 확대 배율 상한. 작은 로고·도장 이미지가 과도하게 커져 OCR 시간이
# 폭증하는 것을 막는다. 면적은 배율의 제곱으로 늘어난다(2배 확대 = 4배 면적).
MAX_UPSCALE = 2.0

# 이 각도보다 작은 기울기는 보정하지 않는다 (불필요한 재보간 방지).
MIN_DESKEW_ANGLE = 0.5

PreprocessStep = Callable[[Image.Image], Image.Image]


@dataclass(frozen=True)
class ImageQuality:
    contrast: float
    blur_score: float
    noise_score: float
    illumination_score: float
    color_ratio: float
    text_height: float | None
    dark_background: bool
    rotation_suspected: bool
    perspective_score: float


@dataclass(frozen=True)
class OcrPreprocessPlan:
    steps: list[PreprocessStep]
    reasons: list[str]
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False


@dataclass(frozen=True)
class PreprocessResult:
    """전처리 결과와 좌표 역변환에 필요한 정보.

    OCR은 전처리된 이미지 기준으로 좌표를 돌려주므로, 호출자가 원본
    좌표계로 되돌릴 수 있도록 배율을 함께 전달한다. 회전이 포함되면
    단순 배율로는 되돌릴 수 없어 rotated 로 표시한다.
    """

    image: Image.Image
    applied: list[str] = field(default_factory=list)
    scale: float = 1.0
    rotated: bool = False


# ----------------------------------------------------------------- 단계 함수

def to_grayscale(image: Image.Image) -> Image.Image:
    """색 정보를 제거한다. 글자 인식에 색상은 쓰이지 않는다."""
    return image if image.mode == "L" else image.convert("L")


def normalize_input_image(
    image: Image.Image,
    *,
    apply_exif_orientation: bool = True,
) -> Image.Image:
    """EXIF 방향을 반영하고 투명 영역을 흰 배경으로 합성한다."""
    normalized = (
        ImageOps.exif_transpose(image)
        if apply_exif_orientation
        else image.copy()
    )

    if normalized.mode in {"RGBA", "LA"} or "transparency" in normalized.info:
        rgba = normalized.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        normalized = Image.alpha_composite(background, rgba)

    return normalized.convert("RGB")


def upscale(image: Image.Image) -> Image.Image:
    """폭이 MIN_WIDTH 미만이면 비율을 유지해 확대한다."""
    if image.width >= MIN_WIDTH:
        return image

    scale = min(MIN_WIDTH / image.width, MAX_UPSCALE)
    if scale <= 1.0:
        return image

    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.LANCZOS)

def denoise(image: Image.Image) -> Image.Image:
    """점 형태의 노이즈를 제거한다. 스캔·촬영본에서 효과가 크다."""
    array = np.asarray(to_grayscale(image))
    return Image.fromarray(cv2.medianBlur(array, 3))

def binarize(image: Image.Image) -> Image.Image:
    """Otsu 임계값으로 글자와 배경을 흑백으로 분리한다."""
    array = np.asarray(to_grayscale(image))
    _, binary = cv2.threshold(
        array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return Image.fromarray(binary)


def adaptive_binarize(image: Image.Image) -> Image.Image:
    """조명이 고르지 않은 흑백 문서를 영역별 임계값으로 이진화한다."""
    array = np.asarray(to_grayscale(image))
    block_size = _adaptive_block_size(array)
    if block_size is None:
        return binarize(image)
    binary = cv2.adaptiveThreshold(
        array,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        15,
    )
    return Image.fromarray(binary)


def _adaptive_block_size(array: np.ndarray, preferred: int = 31) -> int | None:
    size = min(preferred, int(min(array.shape[:2])))
    if size % 2 == 0:
        size -= 1
    return size if size >= 3 else None


def invert(image: Image.Image) -> Image.Image:
    """어두운 배경과 밝은 글자를 일반 문서 명암으로 반전한다."""
    return ImageOps.invert(to_grayscale(image))


def sharpen(image: Image.Image) -> Image.Image:
    """약하게 흐린 문서의 글자 경계만 보수적으로 강조한다."""
    array = np.asarray(to_grayscale(image))
    blurred = cv2.GaussianBlur(array, (0, 0), 1.0)
    return Image.fromarray(cv2.addWeighted(array, 1.35, blurred, -0.35, 0))

def deskew(image: Image.Image) -> Image.Image:
    """글자 영역의 최소 외접 사각형으로 기울기를 추정해 회전 보정한다."""
    array = np.asarray(to_grayscale(image))

    # 글자를 흰색(255)으로 만들어야 findNonZero 가 글자 좌표를 찾는다.
    _, binary = cv2.threshold(
        array, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    coordinates = cv2.findNonZero(binary)

    if coordinates is None:
        return image

    angle = cv2.minAreaRect(coordinates)[-1]

    # minAreaRect 각도는 0~90 범위로 나온다. -45~45 로 정규화한다.
    if angle > 45:
        angle -= 90

    if abs(angle) < MIN_DESKEW_ANGLE:
        return image

    # 빈 영역은 흰색으로 채워 글자로 오인되지 않게 한다.
    return image.rotate(
        angle, resample=Image.BICUBIC, expand=True, fillcolor=255
    )
    
def adjust_contrast(image: Image.Image) -> Image.Image:
    """국소 영역별로 대비를 높인다 (CLAHE).

    사진 촬영본은 조명이 고르지 않아 한쪽이 어둡다. 이미지 전체에 같은
    보정을 하면 밝은 쪽이 날아가므로, 작은 격자로 나눠 각각 보정한다.
    clipLimit 은 대비 증폭 한계로, 너무 크면 노이즈까지 증폭된다.
    """
    array = np.asarray(to_grayscale(image))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return Image.fromarray(clahe.apply(array))


def analyze_image(image: Image.Image, max_width: int = 800) -> ImageQuality:
    """축소 복사본으로 OCR 전처리에 필요한 품질 지표를 계산한다."""
    sample = image.convert("RGB")
    analysis_scale = min(
        1.0,
        max_width / max(sample.width, sample.height, 1),
    )
    if analysis_scale < 1.0:
        sample = sample.resize(
            (
                max(1, round(sample.width * analysis_scale)),
                max(1, round(sample.height * analysis_scale)),
            ),
            Image.Resampling.BILINEAR,
        )

    rgb = np.asarray(sample)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    contrast = float(np.percentile(gray, 95) - np.percentile(gray, 5))
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    median = cv2.medianBlur(gray, 3)
    noise_score = float(cv2.absdiff(gray, median).mean())

    background = cv2.GaussianBlur(gray, (0, 0), 15.0)
    illumination_score = float(background.std())

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    color_ratio = float((hsv[:, :, 1] > 40).mean())
    dark_background = _looks_like_dark_text_background(gray, color_ratio)

    block_size = _adaptive_block_size(gray)
    if block_size is None:
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
    else:
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            15,
        )
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    heights = [
        int(stats[index, cv2.CC_STAT_HEIGHT])
        for index in range(1, count)
        if 3 <= stats[index, cv2.CC_STAT_WIDTH] <= 80
        and 4 <= stats[index, cv2.CC_STAT_HEIGHT] <= 80
        and stats[index, cv2.CC_STAT_AREA] >= 8
    ]
    text_height = (
        float(np.median(heights)) / analysis_scale
        if heights and analysis_scale > 0
        else None
    )

    ink = binary.astype(np.float32) / 255.0
    row_variation = float(ink.mean(axis=1).std())
    column_variation = float(ink.mean(axis=0).std())
    rotation_suspected = column_variation > row_variation * 1.5
    perspective_score = _measure_perspective_score(gray)

    return ImageQuality(
        contrast=contrast,
        blur_score=blur_score,
        noise_score=noise_score,
        illumination_score=illumination_score,
        color_ratio=color_ratio,
        text_height=text_height,
        dark_background=dark_background,
        rotation_suspected=rotation_suspected,
        perspective_score=perspective_score,
    )


def _looks_like_dark_text_background(
    gray: np.ndarray,
    color_ratio: float,
) -> bool:
    """사진 배경이 아니라 실제 어두운 문서 바탕인지 보수적으로 판정한다.

    어두운 책상 위의 흰 종이는 테두리와 전체 평균만 보면 검은 바탕·흰 글씨로
    오인된다. 실제 밝은 글자는 작은 연결요소들로 흩어져 있지만 흰 종이는 큰
    밝은 덩어리를 만들므로, 색상 비율과 밝은 영역의 크기를 함께 확인한다.
    """
    if gray.size == 0 or color_ratio >= 0.02:
        return False

    border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    if np.median(border) >= 100 or gray.mean() >= 135:
        return False

    bright_mask = (gray >= 180).astype(np.uint8)
    bright_ratio = float(bright_mask.mean())
    if not 0.002 <= bright_ratio <= 0.35:
        return False

    count, _, stats, _ = cv2.connectedComponentsWithStats(
        bright_mask,
        connectivity=8,
    )
    if count <= 1:
        return False

    image_area = float(gray.shape[0] * gray.shape[1])
    largest_bright_component = max(
        int(stats[index, cv2.CC_STAT_AREA])
        for index in range(1, count)
    )
    return largest_bright_component / max(image_area, 1.0) < 0.12


def _measure_perspective_score(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(gray.shape[0] * gray.shape[1])
    if not contours or image_area <= 0:
        return 0.0

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < image_area * 0.30:
        return 0.0

    perimeter = cv2.arcLength(contour, True)
    polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    if len(polygon) != 4:
        return 0.0

    points = polygon.reshape(4, 2).astype(np.float32)
    ordered = points[np.argsort(points[:, 1])]
    top = ordered[:2][np.argsort(ordered[:2, 0])]
    bottom = ordered[2:][np.argsort(ordered[2:, 0])]
    top_width = float(np.linalg.norm(top[1] - top[0]))
    bottom_width = float(np.linalg.norm(bottom[1] - bottom[0]))
    left_height = float(np.linalg.norm(bottom[0] - top[0]))
    right_height = float(np.linalg.norm(bottom[1] - top[1]))

    width_score = abs(top_width - bottom_width) / max(top_width, bottom_width, 1.0)
    height_score = abs(left_height - right_height) / max(
        left_height, right_height, 1.0
    )
    return max(width_score, height_score)


def select_preprocess_plan(image: Image.Image, quality: ImageQuality) -> OcrPreprocessPlan:
    """측정 결과에 따라 좌표 안전한 전처리와 Paddle 선택 모듈을 고른다."""
    selected: set[PreprocessStep] = set()
    reasons: list[str] = []
    low_color = quality.color_ratio < 0.02

    if quality.text_height is not None:
        should_upscale = image.width < MIN_WIDTH and quality.text_height < 18
    else:
        should_upscale = image.width < 700
    if should_upscale:
        selected.add(upscale)
        reasons.append("글자 또는 이미지 크기가 작아 확대")

    if quality.dark_background and low_color:
        selected.update({to_grayscale, invert})
        reasons.append("어두운 배경과 밝은 글자가 감지되어 반전")
    elif low_color and quality.contrast < 70:
        selected.update({to_grayscale, adjust_contrast})
        reasons.append("흑백 문서의 대비가 낮아 CLAHE 적용")

    if low_color and quality.noise_score > 10:
        selected.update({to_grayscale, denoise})
        reasons.append("점 형태의 노이즈가 많아 제거")

    if low_color and quality.contrast < 55:
        selected.add(to_grayscale)
        if quality.illumination_score >= 18:
            selected.add(adaptive_binarize)
            reasons.append("조명이 불균일해 적응형 이진화")
        else:
            selected.add(binarize)
            reasons.append("조명이 균일한 저대비 문서라 Otsu 이진화")

    has_binarization = binarize in selected or adaptive_binarize in selected
    if (
        quality.text_height is not None
        and quality.blur_score < 45
        and quality.noise_score < 6
        and not has_binarization
    ):
        selected.update({to_grayscale, sharpen})
        reasons.append("약한 흐림이 감지되어 글자 경계 강조")

    order = [
        to_grayscale,
        upscale,
        adjust_contrast,
        denoise,
        invert,
        binarize,
        adaptive_binarize,
        sharpen,
    ]
    steps = [step for step in order if step in selected]
    return OcrPreprocessPlan(
        steps=steps,
        reasons=reasons or ["품질이 충분해 원본 RGB 사용"],
        use_doc_orientation_classify=quality.rotation_suspected,
        use_doc_unwarping=quality.perspective_score >= 0.12,
        use_textline_orientation=quality.rotation_suspected,
    )


def build_preprocess_plan(
    image: Image.Image,
) -> tuple[ImageQuality | None, OcrPreprocessPlan]:
    """분석 실패 시 원본을 쓰는 안전한 자동 전처리 진입점."""
    try:
        quality = analyze_image(image)
        return quality, select_preprocess_plan(image, quality)
    except (cv2.error, ValueError, TypeError):
        return None, OcrPreprocessPlan(
            steps=[],
            reasons=["이미지 분석 실패로 원본 RGB 사용"],
        )


# --- 좌표를 바꾸지 않거나 배율로 되돌릴 수 있는 단계들 --------------------
# 전처리 없음 — 비교 측정의 기준선
PRESET_NONE: list[PreprocessStep] = []

# 문서 추출 기본 — PaddleOCR은 방향·왜곡을 내부에서 처리하므로 해상도만 보정
PRESET_LIGHT: list[PreprocessStep] = [to_grayscale, upscale]

# 스캔·촬영본 — 조명 보정과 노이즈 제거까지. 좌표는 배율로 되돌릴 수 있다
PRESET_SCAN: list[PreprocessStep] = [
    to_grayscale,
    upscale,
    adjust_contrast,
    denoise,
    binarize,
]


# --- 회전을 포함해 좌표 역변환이 불가한 단계 조합 ------------------------
# 엔진 비교 전용. 좌표를 쓰지 않는 경로에서만 사용한다
PRESET_FULL: list[PreprocessStep] = PRESET_SCAN + [deskew]

PRESETS: dict[str, list[PreprocessStep]] = {
    "none": PRESET_NONE,
    "light": PRESET_LIGHT,
    "scan": PRESET_SCAN,
    "full": PRESET_FULL,
}

# 좌표를 변형해 역변환이 불가한 단계 이름
GEOMETRY_STEPS = {"deskew"}


# ------------------------------------------------------------- 파이프라인

def preprocess(
    image: Image.Image,
    steps: list[PreprocessStep] | None = None,
) -> PreprocessResult:
    """전처리 단계를 순서대로 적용하고, 좌표 역변환 정보를 함께 반환한다.

    scale 은 원본 폭 대비 결과 폭의 비율이다. OCR이 돌려준 좌표를
    scale 로 나누면 원본 이미지 좌표계로 되돌아간다.
    회전이 포함되면 배율만으로는 되돌릴 수 없으므로 rotated=True 로 알린다.
    """
    original_width = max(image.width, 1)
    applied: list[str] = []
    result = image

    for step in steps if steps is not None else PRESET_LIGHT:
        next_result = step(result)
        if next_result is not result:
            applied.append(step.__name__)
        result = next_result

    # OCR 엔진은 3채널 이미지를 기대한다.
    if result.mode != "RGB":
        result = result.convert("RGB")

    rotated = any(name in GEOMETRY_STEPS for name in applied)

    return PreprocessResult(
        image=result,
        applied=applied,
        # 회전 시에는 캔버스가 커져 폭 비율이 배율과 다르므로 1.0 으로 둔다.
        scale=1.0 if rotated else result.width / original_width,
        rotated=rotated,
    )


def preprocess_by_name(
    image: Image.Image,
    preset: str = "light",
) -> PreprocessResult:
    """문자열로 프리셋을 선택한다. 알 수 없는 이름은 light 로 처리한다."""
    return preprocess(image, PRESETS.get(preset, PRESET_LIGHT))

def preprocess_for_layout(
    image: Image.Image,
    steps: list[PreprocessStep] | None = None,
) -> PreprocessResult:
    """좌표를 사용하는 경로(문서 추출)용 전처리.

    기하 변형(회전) 단계가 포함되면 OCR 좌표를 원본 좌표계로 되돌릴 수
    없으므로 즉시 예외를 던진다. 잘못된 프리셋이 조용히 좌표를 어긋나게
    만드는 것을 막기 위한 안전장치다.
    """
    result = preprocess(image, steps)

    if result.rotated:
        raise ValueError(
            "좌표를 사용하는 경로에서는 기하 변형 전처리를 사용할 수 없습니다. "
            f"적용된 단계: {result.applied}"
        )

    return result
