# ① 책임: AIResult.text 또는 원시 문자열의 금액 JSON을 정규화하고 typed DTO로 검증한다.
# ② 관계: amount_normalizer를 거쳐 AmountExtractionOut만 반환하며 DB·모델 호출은 하지 않는다.
# ③ Spring 비교: Jackson ObjectMapper와 Bean Validation 앞의 엄격한 역직렬화 경계에 해당한다.

import json
from collections.abc import Callable
from typing import Any, NoReturn

from pydantic import ValidationError

from app.ai.client_protocol import AIResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.amount import AmountExtractionOut
from app.services.amount_normalizer import (
    normalize_number,
    normalize_payload,
    normalize_quantity,
)


def _json_text(source: AIResult | str) -> str:
    return source if isinstance(source, str) else source.text


def _reject_json_constant(value: str) -> NoReturn:
    """표준 JSON이 아닌 NaN·Infinity를 Python 값으로 구제하지 않는다."""
    raise ValueError(f"허용되지 않은 JSON 숫자 상수: {value}")


def _require_valid_number(
    payload: dict[str, Any],
    field: str,
    normalizer: Callable[[Any], Any | None],
) -> None:
    """명시된 숫자를 null로 바꿔 숨기지 않고 형식 오류로 거부한다."""
    if field not in payload or payload[field] is None:
        return
    if normalizer(payload[field]) is None:
        raise ValueError(f"잘못된 숫자 형식: {field}")


def _reject_invalid_numbers(payload: dict[str, Any]) -> None:
    _require_valid_number(payload, "stated_total", normalize_number)

    items = payload.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        _require_valid_number(item, "amount", normalize_number)
        _require_valid_number(item, "unit_price", normalize_number)
        _require_valid_number(item, "quantity", normalize_quantity)


def parse_amount_extraction(source: AIResult | str) -> AmountExtractionOut:
    """순수 JSON 객체를 정규화한 뒤 금액 추출 DTO로 검증한다.

    코드펜스나 앞뒤 설명을 제거해 구제하지 않는다. 문서에 없는 선택 값은
    null로 보존하고, 명시됐지만 읽을 수 없는 숫자는 null로 바꾸지 않고 거부한다.
    """
    try:
        payload = json.loads(
            _json_text(source),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError("금액 추출 결과의 최상위 값은 JSON 객체여야 한다")
        _reject_invalid_numbers(payload)
        return AmountExtractionOut.model_validate(normalize_payload(payload))
    except (TypeError, ValueError, ValidationError) as exc:
        raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc
