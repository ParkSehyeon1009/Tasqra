import posixpath
import re
import zipfile
from io import BytesIO
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from PIL import Image, UnidentifiedImageError

from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractResult, TextExtractor
from app.models.enums import ExtractMethod

_SECTION_PATTERN = re.compile(r"Contents/section(\d+)\.xml")
_TRUE_VALUES = {"1", "true"}


class HwpxExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(self, file_path: str, *, include_image_ocr: bool = True) -> ExtractResult:
        with zipfile.ZipFile(file_path) as archive:
            section_names = self._find_section_names(archive)
            image_paths = self._read_manifest(archive)

            contents: list[str] = []
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
                    )
                    contents.extend(paragraph_contents)

                    if self._has_page_break(paragraph):
                        page_break_count += 1

        content = "\n".join(contents)

        return ExtractResult(
            content=content,
            page_count=page_break_count + 1,
            char_count=len(content),
            extract_method=ExtractMethod.HWPX.value,
        )

    def _extract_paragraph(
        self,
        paragraph: ET.Element,
        archive: zipfile.ZipFile,
        image_paths: dict[str, str],
        include_image_ocr: bool,
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

                elif element_name == "tbl":
                    table_text = self._extract_table(
                        element,
                        archive,
                        image_paths,
                        include_image_ocr,
                    )
                    if table_text:
                        contents.append(table_text)

                elif element_name == "pic" and include_image_ocr:
                    image_text = self._extract_picture(
                        element,
                        archive,
                        image_paths,
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
                image = source_image.copy()
                elements = self._ocr.extract(image)
        except (UnidentifiedImageError, OSError):
            # HWPX 내부에 Pillow가 해석하지 못하는 이미지가 있어도
            # 문서 전체 추출은 중단하지 않고 해당 이미지만 건너뛴다.
            return ""

        return "\n".join(
            element.content
            for element in elements
            if element.content.strip()
        )

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
