#프롬프트 버전 확인용 문자열 변수
PROMPT_VERSION = "v1"

#카테고리 후보 문자열 리스트
CATEGORY_CANDIDATES = [
    "계약서",
    "보고서",
    "회의록",
    "공지사항",
    "메뉴얼",
    "기타",
]

#AI에게 요약 질문 프롬프트
SUMMARY_SYSTEM_PROMPT = """문서를 핵심만 간결하게 요약하고 아래 규칙을 지켜주세요
1. 반드시 한국어로 작성합니다.
2. 3~5문장, 300자 이내로 요약합니다
3. 불필요한 수식어 없이 사실 위주로 작성합니다.
4. 아래 JSON 형식으로 응답하고, 다른 텍스트는 추가하지 않습니다.

{
    "summary" : "요약 내용"
}
"""

#지시문 + 실제 문서 텍스트를 합쳐서 완성된 최종 프롬프트 문자열 리턴
def build_summary_prompt(text: str) -> str:
    return f"{SUMMARY_SYSTEM_PROMPT}\n\n다음은 요약한 문서 내용입니다:\n\n---\n{text}\n---"

#AI 분류 질문 프롬프트
CATEGORY_SYSTEM_PROMPT = """문서를 정해진 카테고리 중 하나로 분류하고 아래 규칙을 지켜주세요. 

카테고리 목록 : {categories}

1. 반드시 카테고리 목록에 있는 값 중 하나만 선택합니다. 목록에 없는 값은 절대 만들지 않습니다.
2. 판단이 애매하면 "기타"를 선택합니다.
3. 아래 JSON 형식으로 응답하고, 다른 텍스트는 추가하지 않습니다.

{{
    "category" : "선택한 카테고리",
    "reason" : "이 카테고리를 선택한 1문장 이유"
}}
""".format(categories=",".join(CATEGORY_CANDIDATES))
#, 를 구분자로 삼아 하나로 이어붙임, {catregories} 에 상황마다 리스트를 만들어서 넘김

#카테고리 분류용 지시문 + 실제 텍스트를 합쳐 최종 프롬프트 리턴
def build_category_prompt(text: str) -> str:
    return f"{CATEGORY_SYSTEM_PROMPT}\n\n다음은 분류할 문서 내용입니다:\n---\n{text}\n---"

