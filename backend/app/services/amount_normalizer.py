# =============================================================================
# 이 파일의 책임: AI가 문자열로 준 숫자를 계산 가능한 값으로 바꾼다.
#   "9,500,000원" -> 9500000, "3인월" -> Decimal("3") 처럼 정규화한다.
#   schemas/amount.py로 검증하기 전에 이 단계를 거친다.
# 다른 파일과의 관계: 회의에서 "AI 결과를 초기에는 String으로 받고 필요하면
#   JSON 필드로 나눈다"고 정했다. 그래서 쉼표·단위·통화기호가 섞여 들어올 것을
#   전제한다. 여기를 통과한 dict를 schemas/amount.py의
#   AmountExtractionOut.model_validate()에 넘긴다.
# Spring 비교: Jackson의 커스텀 Deserializer 또는 Spring의 Converter/Formatter에
#   해당한다. Spring은 타입 변환을 프레임워크가 가로채지만, 여기서는 검증 전에
#   명시적으로 호출하는 함수로 둔다. 어디서 값이 바뀌는지 눈에 보이게 하려는
#   의도다.
#
# 이 모듈의 원칙 — 못 읽으면 None을 반환하고 예외를 던지지 않는다.
#   숫자 하나를 못 읽었다고 문서 전체를 실패시키지 않는다. None으로 두면
#   schemas 단계에서 필수 필드인지 아닌지에 따라 판단된다. amount는 필수라
#   거기서 걸리고, unit_price는 선택이라 통과한다.
# =============================================================================

import re
from decimal import Decimal, InvalidOperation

# 금액에서 걷어낼 것들. 통화기호·단위·공백.
# 원 단위 정수만 남긴다.
_CURRENCY_NOISE = re.compile(r"[,\s원₩$¥€]|KRW|USD|JPY|EUR", re.IGNORECASE)

# 값이 없음을 뜻하는 표기. 문서에 실제로 이렇게 적혀 있는 경우가 있다.
_EMPTY_MARKS = {"", "-", "—", "–", "n/a", "na", "없음", "미정", "해당없음", "null", "none"}

# 수량에서 숫자 부분만 뽑는다. "3인월" -> "3", "1.5 M/M" -> "1.5"
_LEADING_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

def _is_empty(raw) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str) and raw.strip().lower() in _EMPTY_MARKS:
        return True
    return False

def normalize_number(raw: str | int | float | None) -> int | None:
    """금액을 원 단위 정수로 바꾼다. 못 읽으면 None.

    "9,500,000원" -> 9500000
    "  9500000  " -> 9500000
    9500000.0     -> 9500000
    "" · None · "-" · "미정" -> None
    "약 1억"      -> None  (해석하지 않는다. 추측이 되기 때문이다)
    음수          -> None  (금액에 음수를 허용하지 않는다)
    """
    if _is_empty(raw):
        return None

    if isinstance(raw, bool):
        # bool은 int의 하위 타입이라 먼저 걸러야 True가 1로 들어가지 않는다.
        return None

    if isinstance(raw, int):
        return raw if raw >= 0 else None

    if isinstance(raw, float):
        # 소수점이 있는 금액은 원 단위가 아니다. 반올림하지 않고 버린다.
        # 반올림하면 어디서 값이 바뀌었는지 추적이 안 된다.
        return int(raw) if raw >= 0 and raw == int(raw) else None

    cleaned = _CURRENCY_NOISE.sub("", str(raw)).strip()
    if not cleaned:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None

    if value < 0 or value != value.to_integral_value():
        return None

    return int(value)

def normalize_quantity(raw: str | int | float | Decimal | None) -> Decimal | None:
    """수량을 Decimal로 바꾼다. 단위 문자가 섞여 있으면 숫자만 취한다.

    "3"     -> Decimal("3")
    "1.5"   -> Decimal("1.5")
    "3인월"  -> Decimal("3")
    "1.5 M/M" -> Decimal("1.5")
    음수 · 빈 값 -> None

    float 대신 Decimal을 쓰는 이유 — 1.5인월 같은 값을 float로 두면
    수량 x 단가 검산(amount_calculator.verify_line)에서 오차가 생긴다.
    """
    if _is_empty(raw):
        return None

    if isinstance(raw, bool):
        return None

    if isinstance(raw, Decimal):
        return raw if raw >= 0 else None

    if isinstance(raw, (int, float)):
        value = Decimal(str(raw))
        return value if value >= 0 else None

    match = _LEADING_NUMBER.search(str(raw).replace(",", ""))
    if not match:
        return None

    try:
        value = Decimal(match.group())
    except InvalidOperation:
        return None

    return value if value >= 0 else None

def normalize_payload(raw: dict) -> dict:
    """AI 응답 dict 전체를 정규화한다. 원본을 바꾸지 않고 새 dict를 돌려준다.

    schemas/amount.py로 검증하기 직전에 호출한다.
    items가 배열이 아니거나 항목이 dict가 아니면 그대로 통과시킨다.
    형식 오류는 여기서 판단하지 않고 Pydantic이 잡게 한다. 두 곳에서
    검증하면 어느 쪽 규칙이 맞는지 알 수 없게 된다.
    """
    out = dict(raw)
    out["stated_total"] = normalize_number(raw.get("stated_total"))

    items = raw.get("items")
    if not isinstance(items, list):
        return out

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue

        fixed = dict(item)
        fixed["amount"] = normalize_number(item.get("amount"))
        fixed["unit_price"] = normalize_number(item.get("unit_price"))
        fixed["quantity"] = normalize_quantity(item.get("quantity"))

        # 빈 문자열로 온 단위·기간은 None으로 통일한다.
        # Pydantic에서 max_length는 통과하지만 빈 문자열이 저장되면
        # "값이 없음"과 "빈 값"이 DB에서 구분되지 않는다.
        for key in ("unit", "period_from", "period_to", "category", "notes"):
            if key in fixed and _is_empty(fixed.get(key)):
                fixed[key] = None

        normalized_items.append(fixed)

    out["items"] = normalized_items
    return out
