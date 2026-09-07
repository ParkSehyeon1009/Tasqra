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
    TokenCounter,
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
    project_id: int | None = None
    project_name: str | None = None
    page_number: int | None = None
    content_start: int | None = None
    content_end: int | None = None

    @classmethod
    def from_row(
        cls,
        chunk,
        filename: str,
        project_id: int | None = None,
        project_name: str | None = None,
    ) -> "ContextChunk":
        """리포지토리 행에서 전문과 출처 메타데이터를 옮긴다."""
        return cls(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            seq=chunk.seq,
            text=chunk.text,
            project_id=project_id,
            project_name=project_name,
            page_number=chunk.page_number,
            content_start=chunk.content_start,
            content_end=chunk.content_end,
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
    project_id: int | None = None
    project_name: str | None = None
    page_number: int | None = None
    content_start: int | None = None
    content_end: int | None = None


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
    counter: TokenCounter | None = None,
) -> AssembledContext:
    """검색 순서를 유지하며 청크 전문을 토큰 예산 안에서 조립한다.

    ``counter``가 있으면 실제 생성 모델에 맞는 구현을 주입할 수 있다. 현재 기본값은
    실제 tokenizer가 아니라 문자 비율 근사치다. 매 후보마다 **구분자를 포함한 최종
    문자열 전체**를 다시 세므로 ``counter.count(result.text) <= budget_tokens``가
    항상 성립한다.
    """
    counter = counter or CharRatioTokenCounter(chars_per_token)
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
        local = set(seen)
        for sentence in sentences:
            key = _normalize(sentence)
            if key in local:
                dropped += 1
                continue
            local.add(key)
            kept.append(sentence)
        if not kept:
            dropped_total += dropped
            continue

        header = SOURCE_HEADER.format(
            index=len(evidences) + 1,
            filename=item.filename,
            seq=item.seq + 1,
        )
        body = " ".join(kept)
        block = f"{header}\n{body}"
        candidate_text = "\n\n".join([*blocks, block])

        if counter.count(candidate_text) > budget_tokens:
            if evidences:
                # 구분자까지 넣은 전체 문자열이 넘으면 이 청크를 건너뛰고 다음의
                # 더 작은 청크를 시도한다.
                skipped += 1
                continue

            # 첫 근거만 문자 경계에서 줄인다. counter 구현이 바뀌어도 최종 후보를
            # 매번 다시 세므로 근사 비율을 역산하지 않는다.
            low, high = 0, len(body)
            while low < high:
                middle = (low + high + 1) // 2
                trial_body = body[:middle].rstrip()
                trial = f"{header}\n{trial_body}" if trial_body else header
                if trial_body and counter.count(trial) <= budget_tokens:
                    low = middle
                else:
                    high = middle - 1
            body = body[:low].rstrip()
            if not body:
                skipped += 1
                continue
            block = f"{header}\n{body}"
            candidate_text = block
            if counter.count(candidate_text) > budget_tokens:
                skipped += 1
                continue
            truncated = True

        # 잘려 실제로 들어간 부분만 중복 집합에 기록한다. 잘려 나간 후반부까지
        # 기록하면 뒤 청크에만 실제로 담길 수 있는 문장을 잘못 버리게 된다.
        for sentence in split_sentences(body):
            seen.add(_normalize(sentence))
        blocks.append(block)
        used = counter.count("\n\n".join(blocks))
        dropped_total += dropped
        evidences.append(
            Evidence(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                filename=item.filename,
                seq=item.seq,
                text=body,
                tokens=counter.count(block),
                dropped_sentences=dropped,
                project_id=item.project_id,
                project_name=item.project_name,
                page_number=item.page_number,
                content_start=item.content_start,
                content_end=item.content_end,
            )
        )

    text = "\n\n".join(blocks)
    used = counter.count(text)
    return AssembledContext(
        text=text,
        evidences=evidences,
        used_tokens=used,
        budget_tokens=budget_tokens,
        skipped_for_budget=skipped,
        dropped_sentences=dropped_total,
        truncated=truncated,
    )
