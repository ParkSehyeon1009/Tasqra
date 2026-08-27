# =============================================================================
# 이 파일의 책임: 산출물 문서를 PDF 바이트로 만든다. 절을 고르는 규칙도, 표를
#   그리는 방법도 여기 없다 — HTML 한 장을 그대로 받아 PDF 로 굽기만 한다.
#   그래서 HTML 과 PDF 는 언제나 같은 짜임·같은 내용이다.
#
# 다른 파일과의 관계
#   services/deliverable_html.py     render_html 이 만든 완전한 HTML 문서를 입력으로 쓴다
#   services/deliverable_markdown.py 문서 구조(build_document) — 여기서 직접 부르지 않는다
#   services/deliverable_service.py  RENDERERS["PDF"] 로 이 함수를 고른다
#
# Spring 비교: 같은 모델을 다른 View 로 그리는 것이다. HTML 뷰가 이미 있고,
#   이 파일은 그 HTML 을 PDF 로 내보내는 export 뷰다(뷰 리졸버가 PDF 뷰를 고르는 것과
#   같다). MD·HTML·XLSX 형제 렌더러와 나란히 놓인다.
#
# ⚠ HTML 을 다시 그리지 않고 재사용한다 (2026-08-26 판단, A안)
#   deliverable_html.STYLE 에 이미 @media print · @page(여백 14mm) · page-break
#   규칙이 들어 있다. WeasyPrint 는 print 미디어로 렌더하므로 그 규칙이 그대로
#   먹는다. 표지·절 번호·흑백 짜임을 PDF 에서 새로 짤 이유가 없다 — HTML 이
#   바뀌면 PDF 도 저절로 따라간다.
#
# ⚠ weasyprint 는 함수 안에서 import 한다 — 모듈 import 를 깨지 않기 위해서다
#   weasyprint 는 시스템 라이브러리(libpango 등)에 의존한다. 그것이 없는 환경
#   (단위 테스트·라이브러리 미설치)에서 이 모듈을 import 하는 것만으로 죽으면
#   deliverable_service 전체가, 나아가 산출물 API 전체가 못 뜬다. 그래서 최상단에서
#   import 하지 않고 **실제로 PDF 를 만들 때** 부른다. XLSX 가 아니라 여기만 이렇게
#   하는 이유: openpyxl 은 순수 파이썬이라 import 만으로 죽지 않지만, weasyprint 는
#   네이티브 라이브러리가 없으면 import 시점에 OSError 를 낸다.
#
# ⚠ 한글 폰트는 이미지에 깔려 있어야 한다
#   WeasyPrint 는 시스템 폰트(fontconfig)로 글자를 그린다. Dockerfile 이 fonts-nanum
#   을 설치하고, deliverable_html.STYLE 의 font-family 마지막에 NanumGothic 을
#   넣어 뒀다. 폰트가 없으면 한글이 네모(□)로 나온다 — 코드가 아니라 이미지 문제다.
# =============================================================================

from __future__ import annotations

from typing import Any

from app.services.deliverable_html import render_html

__all__ = ["render_pdf"]


def render_pdf(**kwargs: Any) -> bytes:
    """산출물 본문을 PDF 바이트로. 인자는 build_document·render_html 과 같다.

    HTML 한 장을 만들어 WeasyPrint 로 굽는다. `_write_file` 이 bytes 를 그대로
    `"wb"` 로 저장하므로(XLSX 와 같은 경로) 돌려주는 타입이 bytes 여야 한다.
    """
    # 파일 머리말 참고: 시스템 라이브러리에 의존하므로 여기서 import 한다.
    from weasyprint import HTML

    html = render_html(**kwargs)
    # render_html 이 <!doctype> 부터 <style> 까지 담은 완전한 문서를 주므로
    # 외부 CSS·base_url 없이 문자열만으로 굽는다. @media print 규칙은 WeasyPrint 가
    # print 미디어로 렌더하며 자동 적용한다.
    return HTML(string=html).write_pdf()
