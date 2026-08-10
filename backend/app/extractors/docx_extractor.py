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

from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractResult, TextExtractor
from app.models.enums import ExtractMethod


class DocxExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(self, file_path: str) -> ExtractResult:
        doc = Document(file_path)

        contents: list[str] = []

        for block in self._iter_block_items(doc):

            if isinstance(block, Paragraph):
                self._extract_paragraph(block, contents)

            elif isinstance(block, Table):
                self._extract_table(block, contents)

        content = "\n".join(contents)

        return ExtractResult(
            content=content,
            page_count=self._count_pages(doc),
            char_count=len(content),
            extract_method=ExtractMethod.DOCX.value,
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
    ) -> None:
        text = paragraph.text.strip()

        if text:
            contents.append(text)

        self._extract_images(paragraph, contents)

    def _extract_table(
        self,
        table: Table,
        contents: list[str],
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

                    # 셀 안 이미지 OCR
                    self._extract_images(paragraph, cell_text)

                if cell_text:
                    row_contents.append("\n".join(cell_text))

            if row_contents:
                contents.append(" | ".join(row_contents))

    def _extract_images(
        self,
        paragraph: Paragraph,
        contents: list[str],
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

                text = self._ocr_image(image_part.blob)

                if text:
                    contents.append(text)

    def _ocr_image(self, image_bytes: bytes) -> str:
        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                image = source_image.copy()
                elements = self._ocr.extract(image)

            return "\n".join(
                element.content
                for element in elements
                if element.content.strip()
            )
        except (UnidentifiedImageError, OSError):
            # Word 내부에는 python-docx/Pillow가 해석하지 못하는 이미지 형식도
            # 있을 수 있으므로 해당 이미지만 건너뛴다.
            return ""

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
