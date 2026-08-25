import posixpath
import re
import zipfile
from io import BytesIO
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from PIL import Image, UnidentifiedImageError

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.preprocessing import normalize_input_image
from app.extractors.protocol import ExtractedPage, ExtractResult, TextExtractor
from app.extractors.review_page import build_image_review_page, mark_review_text, resolve_review_content_ranges
from app.models.enums import ExtractMethod

_SECTION_PATTERN = re.compile(r"Contents/section(\d+)\.xml")
_TRUE_VALUES = {"1", "true"}


class HwpxExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(
        self,
        file_path: str,
        *,
        include_image_ocr: bool = True,
        max_text_chars: int | None = None,
    ) -> ExtractResult:
        with zipfile.ZipFile(file_path) as archive:
            section_names = self._find_section_names(archive)
            image_paths = self._read_manifest(archive)

            if max_text_chars is not None:
                self._validate_native_text_size(
                    archive,
                    section_names,
                    image_paths,
                    max_text_chars,
                )

            contents: list[str] = []
            review_pages: list[ExtractedPage] = []
            counts = {"text": 0, "ocr": 0}
            page_break_count = 0

            for section_name in section_names:
                root = ET.fromstring(archive.read(section_name))

                # 표 내부 문단까지 root.iter()로 다시 순회하면 같은 텍스트가
                # 중복되므로 section의 최상위 문단만 여기서 처리한다.
                for paragraph in self._children(root, "p"):
                    paragraph_contents = self._extract_paragraph(
                        paragraph,
                        archive,
                        image_paths,
                        include_image_ocr,
                        review_pages,
                        counts,
                    )
                    contents.extend(paragraph_contents)

                    if self._has_page_break(paragraph):
                        page_break_count += 1

        content, review_pages = resolve_review_content_ranges("\n".join(contents), review_pages)

        return ExtractResult(
            content=content,
            page_count=page_break_count + 1,
            char_count=len(content),
            text_char_count=counts["text"],
            ocr_char_count=counts["ocr"],
            extract_method=ExtractMethod.HWPX.value,
            review_pages=tuple(review_pages),
        )

    def _validate_native_text_size(
        self,
        archive: zipfile.ZipFile,
        section_names: list[str],
        image_paths: dict[str, str],
        max_text_chars: int,
    ) -> None:
        """이미지 데이터를 읽거나 OCR하기 전에 HWPX 원문만 제한 검사한다."""
        counts = {"text": 0, "ocr": 0}
        review_pages: list[ExtractedPage] = []

        for section_name in section_names:
            root = ET.fromstring(archive.read(section_name))
            for paragraph in self._children(root, "p"):
                self._extract_paragraph(
                    paragraph,
                    archive,
                    image_paths,
                    False,
                    review_pages,
                    counts,
                )
                if counts["text"] > max_text_chars:
                    raise BusinessError(
                        ErrorCode.CONTENT_TOO_LARGE,
                        detail=(
                            "DOCX와 HWPX는 문서 본문 텍스트를 최대 "
                            f"{max_text_chars:,}자까지 허용합니다."
                        ),
                    )

    def _extract_paragraph(
        self,
        paragraph: ET.Element,
        archive: zipfile.ZipFile,
        image_paths: dict[str, str],
        include_image_ocr: bool,
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> list[str]:
        contents: list[str] = []

        # 한 문단 안에서도 텍스트, 표, 그림이 섞일 수 있으므로 run과 그
        # 자식들의 XML 등장 순서를 그대로 읽기 순서로 사용한다.
        for run in self._children(paragraph, "run"):
            for element in run:
                element_name = self._local_name(element.tag)

                if element_name == "t":
                    text = self._extract_text(element).strip()
                    if text:
                        contents.append(text)
                        counts["text"] += len(text)

                elif element_name == "tbl":
                    table_text = self._extract_table(
                        element,
                        archive,
                        image_paths,
                        include_image_ocr,
                        review_pages,
                        counts,
                    )
                    if table_text:
                        contents.append(table_text)

                elif element_name == "pic" and include_image_ocr:
                    image_text = self._extract_picture(
                        element,
                        archive,
                        image_paths,
                        review_pages,
                        counts,
                    )
                    if image_text:
                        contents.append(image_text)

        return contents

    def _extract_table(
        self,
        table: ET.Element,
        archive: zipfile.ZipFile,
        image_paths: dict[str, str],
        include_image_ocr: bool,
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> str:
        rows: list[str] = []

        for row in self._children(table, "tr"):
            cells: list[str] = []

            for cell in self._children(row, "tc"):
                cell_contents: list[str] = []

                for sub_list in self._children(cell, "subList"):
                    for paragraph in self._children(sub_list, "p"):
                        cell_contents.extend(
                            self._extract_paragraph(
                                paragraph,
                                archive,
                                image_paths,
                                include_image_ocr,
                                review_pages,
                                counts,
                            )
                        )

                cells.append(" / ".join(cell_contents))

            if cells:
                rows.append(" | ".join(cells))

        return "\n".join(rows)

    def _extract_picture(
        self,
        picture: ET.Element,
        archive: zipfile.ZipFile,
        image_paths: dict[str, str],
        review_pages: list[ExtractedPage],
        counts: dict[str, int],
    ) -> str:
        image_id = self._find_image_id(picture)
        if image_id is None:
            return ""

        image_path = image_paths.get(image_id)
        if image_path is None or image_path not in archive.namelist():
            return ""

        image_bytes = archive.read(image_path)

        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                image = normalize_input_image(source_image)
                elements = self._ocr.extract(
                    image,
                    normalize_orientation=False,
                )
        except (UnidentifiedImageError, OSError):
            # HWPX 내부에 Pillow가 해석하지 못하는 이미지가 있어도
            # 문서 전체 추출은 중단하지 않고 해당 이미지만 건너뛴다.
            return ""

        text = "\n".join(
            element.content
            for element in elements
            if element.content.strip()
        )
        if text:
            page = build_image_review_page(image, elements, len(review_pages) + 1)
            review_pages.append(page)
            counts["ocr"] += sum(
                len(element.content) for element in elements if element.content.strip()
            )
            return mark_review_text(text, page.page_number)
        return text

    @classmethod
    def _find_section_names(cls, archive: zipfile.ZipFile) -> list[str]:
        section_names = sorted(
            (
                name
                for name in archive.namelist()
                if _SECTION_PATTERN.fullmatch(name)
            ),
            key=cls._section_number,
        )

        if not section_names:
            raise ValueError("HWPX 본문 section을 찾을 수 없습니다.")

        return section_names

    @classmethod
    def _read_manifest(cls, archive: zipfile.ZipFile) -> dict[str, str]:
        manifest_name = "Contents/content.hpf"
        if manifest_name not in archive.namelist():
            return {}

        root = ET.fromstring(archive.read(manifest_name))
        image_paths: dict[str, str] = {}

        for element in root.iter():
            if cls._local_name(element.tag) != "item":
                continue

            item_id = element.get("id")
            href = element.get("href")
            media_type = element.get("media-type", "")

            if not item_id or not href or not media_type.startswith("image/"):
                continue

            normalized_path = posixpath.normpath(unquote(href)).lstrip("/")

            # ZIP 밖을 가리키는 상대 경로는 허용하지 않는다.
            if normalized_path == ".." or normalized_path.startswith("../"):
                continue

            image_paths[item_id] = normalized_path

        return image_paths

    @classmethod
    def _find_image_id(cls, picture: ET.Element) -> str | None:
        for element in picture.iter():
            if cls._local_name(element.tag) != "img":
                continue

            image_id = element.get("binaryItemIDRef")
            if image_id:
                return image_id

        return None

    @classmethod
    def _extract_text(cls, text_element: ET.Element) -> str:
        parts: list[str] = []

        if text_element.text:
            parts.append(text_element.text)

        for child in text_element:
            child_name = cls._local_name(child.tag)

            if child_name == "tab":
                parts.append("\t")
            elif child_name in {"lineBreak", "br"}:
                parts.append("\n")
            elif child.text:
                parts.append(child.text)

            if child.tail:
                parts.append(child.tail)

        return "".join(parts)

    @classmethod
    def _children(
        cls,
        element: ET.Element,
        name: str,
    ) -> list[ET.Element]:
        return [
            child
            for child in element
            if cls._local_name(child.tag) == name
        ]

    @staticmethod
    def _section_number(section_name: str) -> int:
        match = _SECTION_PATTERN.fullmatch(section_name)
        if match is None:
            raise ValueError(f"올바르지 않은 HWPX section 경로입니다: {section_name}")
        return int(match.group(1))

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @classmethod
    def _has_page_break(cls, element: ET.Element) -> bool:
        return any(
            cls._local_name(attribute_name) == "pageBreak"
            and attribute_value.lower() in _TRUE_VALUES
            for attribute_name, attribute_value in element.attrib.items()
        )
