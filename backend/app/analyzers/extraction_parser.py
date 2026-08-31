# ① 책임: AIResult.text 또는 문자열 JSON을 결정사항·일정/기한 typed DTO 목록으로 변환한다.
# ② 관계: schemas/extraction.py의 DTO만 검증하며, 네트워크 호출·DB 저장·analyzer 등록은 하지 않는다.
# ③ Spring 비교: Jackson ObjectMapper와 Bean Validation 경계처럼 역직렬화·검증 오류를 공통 예외로 바꾼다.

from pydantic import ValidationError

from app.ai.client_protocol import AIResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.extraction import (
    DecisionExtraction,
    DecisionExtractionList,
    ScheduleItemExtraction,
    ScheduleItemExtractionList,
)


def _json_text(source: AIResult | str) -> str:
    return source if isinstance(source, str) else source.text


def parse_decision_extractions(
    source: AIResult | str,
) -> list[DecisionExtraction]:
    """순수 JSON 배열을 결정사항 DTO 목록으로 변환한다."""

    try:
        return DecisionExtractionList.model_validate_json(_json_text(source)).root
    except ValidationError as exc:
        raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc


def parse_schedule_item_extractions(
    source: AIResult | str,
) -> list[ScheduleItemExtraction]:
    """순수 JSON 배열을 일정/기한 DTO 목록으로 변환한다."""

    try:
        return ScheduleItemExtractionList.model_validate_json(_json_text(source)).root
    except ValidationError as exc:
        raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc
