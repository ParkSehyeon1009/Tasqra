# =============================================================================
# 이 파일의 책임: 검색이 찾아온 청크들을 **토큰 예산 안에서** LLM 프롬프트의
#   근거로 조립한다 (RAG-002-1 프롬프트 컨텍스트 조립).
#
#   "프롬프트 문구를 쓰는 일" 이 아니다. 무엇을 시킬지는 분석기 쪽(박세현)이
#   정하고, 여기는 **근거 자료를 예산 안에 담는 것**까지다. 그래서 선행 기능이
#   RAG-001-2(임베딩 생성·벡터 인덱스 저장)이고 검색 사슬 안에 있다.
#
#   완료 판정: "긴 문서에서도 컨텍스트 한도를 넘지 않는다."
#
# 왜 그냥 이어 붙이면 안 되는가 — 겹침이 예산을 먹는다
#   청킹이 검색 정확도를 위해 **앞 청크의 끝부분을 다음 청크 앞에 겹쳐 넣는다**
#   (services/chunking.py 의 _apply_overlap · CHUNK_OVERLAP_TOKENS 기본 48).
#
#       청크 n     ... 준공 검사 완료 후 30일 이내에 지급한다.
#       청크 n+1   준공 검사 완료 후 30일 이내에 지급한다. 선금은 ...
#                  └── 겹침(48토큰) ──┘
#
#   인접한 두 청크를 나란히 담으면 **같은 문장이 두 번 들어간다.** 예산이
#   4,000토큰인데 겹침으로 수백 토큰을 버리면 근거 한두 조각이 덜 들어간다.
#
#   ⚠ 좌표로 겹침 길이를 계산하지 않는다
#     content_start·content_end 는 **겹침을 포함하지 않는다**(_apply_overlap 주석:
#     "겹친 부분은 앞 청크의 본문이므로 ... 그래서 char_count 와 구간 길이는
#     다르다"). 그래서 `char_count - (content_end - content_start)` 로 겹침
#     길이를 어림할 수는 있지만, 정규화·개행 삽입 때문에 정확하지 않다.
#     **문장 단위로 이미 담은 것을 건너뛰는 쪽**이 정확하고, 인접하지 않은
#     청크에 같은 문구가 있는 경우(청렴계약·담합금지 같은 정형 문구)까지 함께
#     걸러낸다.
#
# 다른 파일과의 관계
#   services/chunking.py    CharRatioTokenCounter · SENTENCE_BREAK 를 재사용한다.
#                           토큰을 세는 자가 청킹과 달라지면 예산이 어긋난다.
#   schemas/search.py       SearchResultItem 을 입력으로 받는다. 하이브리드
#                           검색(SRH-004)의 결과를 그대로 넣을 수 있다.
#   이 파일은 DB·HTTP·LLM 을 모르는 순수 로직이다. 그래서 모델 없이 테스트된다.
#
# Spring 비교: 도메인 서비스에 해당한다. 의존성이 없는 순수 계산이라
#   @SpringBootTest 없이 단위 테스트로 전부 덮인다.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.chunking import (
    CHARS_PER_TOKEN,
    SENTENCE_BREAK,
    CharRatioTokenCounter,
)

# 근거 하나에 붙이는 머리말의 모양. LLM 이 출처를 인용할 수 있어야 하고
# (CHAT-001 완료 판정: "답변마다 근거 문서와 원문 인용이 표시된다"),
# 사람이 원문에서 되찾을 수 있어야 한다.
#
# 조각 번호를 seq+1 로 쓰는 것은 화면과 같은 규칙이다(SearchView 의 "조각 N번").
SOURCE_HEADER = "[근거 {index}] {filename} · 조각 {seq}번"


@dataclass(frozen=True)
class ContextChunk:
    """조립의 입력 한 조각.

    **`SearchResultItem` 을 그대로 받지 않는다.** 그쪽의 `snippet` 은 220자(키워드는
    160자)로 잘린 값이어서 근거로 쓰면 문장이 중간에서 끊긴다. 조립에는 청크
    **전문**이 필요하다.

    다행히 리포지토리가 이미 전문을 들고 온다 — `search_by_vector` ·
    `search_by_keyword` 가 `(DocumentChunk, filename, ...)` 를 돌려주고
    `DocumentChunk.text` 가 전문이다. 서비스가 그것으로 이 객체를 만든다.

    ORM 을 직접 받지 않는 이유: 이 모듈이 SQLAlchemy 를 모르게 두려는 것이다.
    그래야 DB 없이 테스트된다(chunking.py 가 TextUnit 을 쓰는 것과 같은 방식).
    """

    chunk_id: int
    document_id: int
    filename: str
    seq: int
    text: str

    @classmethod
    def from_row(cls, chunk, filename: str) -> "ContextChunk":
        """리포지토리 행에서 만든다. 검색 결과 튜플의 앞 두 자리와 맞춘다."""
        return cls(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            seq=chunk.seq,
            text=chunk.text,
        )


@dataclass(frozen=True)
class Evidence:
    """프롬프트에 담긴 근거 하나."""

    chunk_id: int
    document_id: int
    filename: str
    seq: int
    text: str
    tokens: int
    # 이 청크에서 중복이라 버린 문장 수. 겹침이 실제로 얼마나 낭비되고 있었는지
    # 알 수 있다. OVERLAP_TOKENS 를 조정할 근거가 된다.
    dropped_sentences: int


@dataclass(frozen=True)
class AssembledContext:
    """조립 결과. 프롬프트에 넣을 본문과 그 근거를 함께 들고 있다."""

    text: str
    evidences: list[Evidence] = field(default_factory=list)
    used_tokens: int = 0
    budget_tokens: int = 0
    # 예산이 모자라 담지 못한 청크 수. 0 이 아니면 예산을 늘릴지 판단한다.
    skipped_for_budget: int = 0
    # 중복이라 버린 문장 수의 합.
    dropped_sentences: int = 0
    # 예산을 넘겨 **잘라 담은** 근거가 있는가. 첫 근거가 예산보다 클 때만 참이다.
    truncated: bool = False

    @property
    def remaining_tokens(self) -> int:
        return max(self.budget_tokens - self.used_tokens, 0)


def split_sentences(text: str) -> list[str]:
    """청크 본문을 문장으로 쪼갠다.

    청킹과 **같은 규칙**을 쓴다(`chunking.SENTENCE_BREAK`). 규칙이 다르면 겹침으로
    들어온 문장의 경계가 어긋나 같은 문장으로 인식되지 않는다.

    빈 조각은 버리고 양끝 공백을 떼어낸다 — 중복 판정을 글자 그대로 하기 때문에
    공백 차이로 다른 문장이 되면 안 된다.
    """
    return [s.strip() for s in SENTENCE_BREAK.split(text) if s and s.strip()]


def _normalize(sentence: str) -> str:
    """중복 판정용 열쇠. 공백만 눌러서 비교한다.

    겹침으로 들어온 문장은 앞 청크의 문장을 **그대로** 옮긴 것이라(문자열 슬라이스)
    내용이 같다. 다만 청크 경계에서 개행이 공백으로 바뀌는 경우가 있어 공백은
    누른다. 그 이상 고치지 않는다 — 조사를 떼거나 정규화를 더하면 **서로 다른
    문장을 같다고 판정할 위험**이 생긴다.
    """
    return " ".join(sentence.split())


def assemble_context(
    chunks: list[ContextChunk],
    *,
    budget_tokens: int,
    chars_per_token: float = CHARS_PER_TOKEN,
    max_evidences: int | None = None,
) -> AssembledContext:
    """청크들을 토큰 예산 안에서 근거로 조립한다.

    **검색이 정한 순서를 그대로 지킨다** — 관련도 높은 것이 앞에 와야 LLM 이
    그것을 더 크게 본다. 문서·조각 번호로 다시 정렬하지 않는다.

    규칙 넷

    1. **문장 단위 중복 제거.** 이미 담은 문장은 다시 담지 않는다. 겹침으로
       들어온 것과 정형 문구가 함께 걸러진다.
    2. **청크는 되도록 통째로 담는다.** 반만 담으면 근거가 잘려 LLM 이 인용한
       문장을 사용자가 원문에서 찾지 못한다. 예산에 안 들어가면 **건너뛰고**
       다음 것을 본다 — 뒤에 더 작은 청크가 들어갈 수 있다.
    3. **첫 근거만 예외로 자른다.** 첫 청크가 예산보다 크면 아무것도 못 담게
       되므로 그때는 잘라서라도 담는다. `truncated` 로 알린다.
    4. **예산은 근거 머리말까지 포함해 센다.** 머리말을 빼고 세면 근거가 많을 때
       실제 프롬프트가 예산을 넘는다.

    예산이 0 이하면 빈 결과를 돌려준다 — 예외를 던지지 않는다. 호출한 쪽이
    설정을 잘못 넣었다고 요청을 실패시킬 이유가 없다.
    """
    counter = CharRatioTokenCounter(chars_per_token)
    if budget_tokens <= 0 or not chunks:
        return AssembledContext(text="", budget_tokens=max(budget_tokens, 0))

    seen: set[str] = set()
    evidences: list[Evidence] = []
    blocks: list[str] = []
    used = 0
    skipped = 0
    dropped_total = 0
    truncated = False

    for item in chunks:
        if max_evidences is not None and len(evidences) >= max_evidences:
            skipped += 1
            continue

        sentences = split_sentences(item.text)
        kept: list[str] = []
        dropped = 0
        # 이 청크 안에서 이미 고른 문장도 함께 본다. seen 은 청크가 확정된 뒤에
        # 갱신되므로, 지역 집합을 두지 않으면 **한 청크 안의 반복이 그대로 담긴다**
        # (표의 같은 행이 여러 번 나오는 문서에서 실제로 예산을 먹는다).
        local = set(seen)
        for sentence in sentences:
            key = _normalize(sentence)
            if key in local:
                dropped += 1
                continue
            local.add(key)
            kept.append(sentence)
        if not kept:
            # 전부 중복이었다. 예산을 쓰지 않았으므로 건너뛴 것으로 세지 않는다.
            dropped_total += dropped
            continue

        header = SOURCE_HEADER.format(
            index=len(evidences) + 1,
            filename=item.filename,
            seq=item.seq + 1,
        )
        body = " ".join(kept)
        block = f"{header}\n{body}"
        need = counter.count(block)

        if used + need > budget_tokens:
            if evidences:
                # 이미 담은 것이 있으면 이 청크는 건너뛴다. 뒤에 더 작은 것이
                # 들어갈 수 있으므로 여기서 멈추지 않는다.
                skipped += 1
                continue
            # 첫 근거인데 예산을 넘는다 — 잘라서라도 담는다.
            room = budget_tokens - counter.count(header + "\n")
            if room <= 0:
                skipped += 1
                continue
            body = body[: int(room * chars_per_token)].rstrip()
            if not body:
                skipped += 1
                continue
            block = f"{header}\n{body}"
            need = counter.count(block)
            truncated = True

        for sentence in kept:
            seen.add(_normalize(sentence))
        blocks.append(block)
        used += need
        dropped_total += dropped
        evidences.append(
            Evidence(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                filename=item.filename,
                seq=item.seq,
                text=body,
                tokens=need,
                dropped_sentences=dropped,
            )
        )

    return AssembledContext(
        text="\n\n".join(blocks),
        evidences=evidences,
        used_tokens=used,
        budget_tokens=budget_tokens,
        skipped_for_budget=skipped,
        dropped_sentences=dropped_total,
        truncated=truncated,
    )
