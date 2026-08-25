from collections.abc import Iterator
from io import BytesIO

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image, UnidentifiedImageError

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractedPage, ExtractResult, TextExtractor
from app.extractors.review_page import build_image_review_page, mark_review_text, resolve_review_content_ranges
from app.models.enums import ExtractMethod


class DocxExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(
        self,
        file_path: str,
        *,
        include_image_ocr: bool = True,
        max_text_chars: int | None = None,
    ) -> ExtractResult:
        doc = Document(file_path)

        if max_text_chars is not None:
            self._validate_native_text_size(doc, max_text_chars)

        contents: list[str] = []
        review_pages: list[ExtractedPage] = []
        counts = {"text": 0, "ocr": 0}

        for block in self._iter_block_items(doc):

            if isinstance(block, Paragraph):
                self._extract_paragraph(block, contents, include_image_ocr, review_pages, counts)

            elif isinstance(block, Table):
                self._extract_table(block, contents, include_image_ocr, review_pages, counts)

        content, review_pages = resolve_review_content_ranges("\n".join(contents), review_pages)

        return ExtractResult(
            content=content,
            page_count=self._count_pages(doc),
            char_count=len(content),
            text_char_count=counts["text"],
            ocr_char_count=counts["ocr"],
            extract_method=ExtractMethod.DOCX.value,
            review_pages=tuple(review_pages),
        )

    def _validate_native_text_size(
        self,
        doc: DocxDocument,
        max_text_chars: int,
    ) -> None:
        """이미지 OCR 전에 Word 원문 텍스트만 빠르게 제한 검사한다."""
        counts = {"text": 0, "ocr": 0}
        contents: list[str] = []
        review_pages: list[ExtractedPage] = []

        for block in self._iter_block_items(doc):
            if isinstance(block, Paragraph):
                self._extract_paragraph(
                    block, contents, False, review_pages, counts
                )
            elif isinstance(block, Table):
                self._extract_table(
                    block, contents, False, review_pages, counts
                )

            if counts["text"] > max_text_chars:
                raise BusinessError(
                    ErrorCode.CONTENT_TOO_LARGE,
                    detail=(
                        "DOCX와 HWPX는 문서 본문 텍스트를 최대 "
                        f"{max_text_chars:,}자까지 허용합니다."
                    ),
                )

    def _iter_block_items(
        self,
        doc: DocxDocument,
    ) -> Iterator[Paragraph | Table]:
        parent = doc.element.body

        for child in parent.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield Table(child, doc)

    def _extract_paragraph(
        self,
        paragraph: Paragraph,
        contents: list[str],
        include_image_ocr: bool,
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> None:
        text = paragraph.text.strip()

        if text:
            contents.append(text)
            counts["text"] += len(text)

        if include_image_ocr:
            self._extract_images(paragraph, contents, review_pages, counts)

    def _extract_table(
        self,
        table: Table,
        contents: list[str],
        include_image_ocr: bool,
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> None:
        for row in table.rows:

            row_contents: list[str] = []

            for cell in row.cells:

                cell_text = []

                # 셀 안 문단 순회
                for paragraph in cell.paragraphs:

                    text = paragraph.text.strip()

                    if text:
                        cell_text.append(text)
                        counts["text"] += len(text)

                    # 셀 안 이미지 OCR
                    if include_image_ocr:
                        self._extract_images(paragraph, cell_text, review_pages, counts)

                if cell_text:
                    row_contents.append("\n".join(cell_text))

            if row_contents:
                contents.append(" | ".join(row_contents))

    def _extract_images(
        self,
        paragraph: Paragraph,
        contents: list[str],
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> None:
        # paragraph 안의 drawing 태그 찾기
        drawings = paragraph._element.xpath(".//w:drawing")

        for drawing in drawings:

            # drawing 안의 이미지(blip) 찾기
            blips = drawing.xpath(".//a:blip")

            for blip in blips:

                embed = blip.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )

                if embed is None:
                    continue

                try:
                    image_part = paragraph.part.related_parts[embed]

                except KeyError:
                    continue

                text, page, ocr_char_count = self._ocr_image(image_part.blob, len(review_pages) + 1)

                if text:
                    review_pages.append(page)
                    contents.append(mark_review_text(text, page.page_number))
                    counts["ocr"] += ocr_char_count

    def _ocr_image(self, image_bytes: bytes, page_number: int) -> tuple[str, ExtractedPage | None, int]:
        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                image = source_image.copy()
                elements = self._ocr.extract(image)

            text = "\n".join(
                element.content
                for element in elements
                if element.content.strip()
            )
            return text, build_image_review_page(image, elements, page_number), sum(
                len(element.content) for element in elements if element.content.strip()
            )
        except (UnidentifiedImageError, OSError):
            # Word 내부에는 python-docx/Pillow가 해석하지 못하는 이미지 형식도
            # 있을 수 있으므로 해당 이미지만 건너뛴다.
            return "", None, 0

    @staticmethod
    def _count_pages(document: DocxDocument) -> int:
        # python-docx는 렌더링 페이지 수를 제공하지 않으므로, 저자가 넣은
        # 명시적 페이지 나눔(w:br type="page") 개수 + 1로 근사한다.
        page_breaks = sum(
            1
            for br in document.element.body.iter(qn("w:br"))
            if br.get(qn("w:type")) == "page"
        )
        return page_breaks + 1
