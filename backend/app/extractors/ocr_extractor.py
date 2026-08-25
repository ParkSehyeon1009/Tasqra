from dataclasses import asdict
from logging import getLogger
from threading import Lock

import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

from app.core.config import settings
from app.extractors.layout import LayoutElement
from app.extractors.reading_order import build_reading_groups
from app.extractors.table_detector import TableCell, TableDetector

from app.extractors.preprocessing import (
    build_preprocess_plan,
    normalize_input_image,
    preprocess_for_layout,
)

logger = getLogger(__name__)



class OcrExtractor:
    # 두 OCR 박스가 같은 줄인지 판단할 때 필요한 최소 세로 겹침 비율.
    _LINE_OVERLAP_RATIO = 0.45
    # 한 글자씩 분리된 박스 사이의 간격이 글자 높이의 이 비율 이하면 붙인다.
    _CHAR_JOIN_GAP_RATIO = 0.60

    def __init__(self) -> None:
        self._ocr = PaddleOCR(
            lang="korean",
            # 선택 모듈을 한 번만 로드하고 이미지 분석 결과에 따라 요청별로 사용한다.
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
        )

        # 여러 요청이 같은 OCR 모델을 동시에 사용하지 못하도록 제어한다.
        self._inference_lock = Lock()
        self._table_detector = TableDetector()

    def extract(
        self,
        image: Image.Image,
        offset_x: float = 0,
        offset_y: float = 0,
        normalize_orientation: bool = True,
    ) -> list[LayoutElement]:
        source_image = normalize_input_image(
            image,
            apply_exif_orientation=normalize_orientation,
        )
        quality, plan = build_preprocess_plan(source_image)
        prepared = preprocess_for_layout(source_image, plan.steps)
        rgb_image = prepared.image
        inverse_scale = 1.0 / prepared.scale if prepared.scale else 1.0
        logger.info(
            "OCR 전처리 선택: steps=%s paddle=(orientation=%s, unwarping=%s, "
            "textline=%s) reasons=%s quality=%s",
            prepared.applied,
            plan.use_doc_orientation_classify,
            plan.use_doc_unwarping,
            plan.use_textline_orientation,
            plan.reasons,
            asdict(quality) if quality is not None else None,
        )

        # 동시에 여러 요청이 들어와도 OCR은 한 번에 하나씩 실행한다.
        with self._inference_lock:
            results = list(
                self._ocr.predict(
                    np.asarray(rgb_image),
                    text_det_limit_side_len=settings.OCR_TEXT_DET_MAX_SIDE_LEN,
                    text_det_limit_type="max",
                    use_doc_orientation_classify=(
                        plan.use_doc_orientation_classify
                    ),
                    use_doc_unwarping=plan.use_doc_unwarping,
                    use_textline_orientation=plan.use_textline_orientation,
                )
            )

        if not results:
            return []

        page = results[0]

        if page is None:
            return []

        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])

        boxes = page.get("rec_boxes")

        # rec_boxes가 없으면 다각형 좌표인 rec_polys를 사용한다.
        if boxes is None or len(boxes) == 0:
            boxes = page.get("rec_polys", [])

        elements: list[LayoutElement] = []

        for text, score, box in zip(texts, scores, boxes):
            normalized_text = str(text).strip()

            if not normalized_text:
                continue

            box_array = np.asarray(box)

            if box_array.ndim == 1:
                # rec_boxes 형식: [x1, y1, x2, y2]
                x = float(box_array[0])
                y = float(box_array[1])
                x2 = float(box_array[2])
                y2 = float(box_array[3])
            else:
                # rec_polys 형식: [[x1, y1], [x2, y2], ...]
                x = float(box_array[:, 0].min())
                y = float(box_array[:, 1].min())
                x2 = float(box_array[:, 0].max())
                y2 = float(box_array[:, 1].max())

            # 전처리에서 확대됐다면 원본 이미지 좌표계로 되돌린다.
            # (호출자 pdf_extractor 는 원본 크기를 기준으로 배율을 계산한다)
            x *= inverse_scale
            y *= inverse_scale
            x2 *= inverse_scale
            y2 *= inverse_scale
            
            elements.append(
                LayoutElement(
                    x=x + offset_x,
                    y=y + offset_y,
                    content=normalized_text,
                    source="ocr",
                    confidence=float(score),
                    x2=x2 + offset_x,
                    y2=y2 + offset_y,
                )
            )

        # 표 셀 좌표와 element 좌표를 같은 기준(원본 이미지)으로 맞춘다.
        table_cells = self._table_detector.detect(source_image)
        return self._merge_document_elements(
            elements,
            table_cells,
            page_width=float(source_image.width),
            offset_x=offset_x,
            offset_y=offset_y,
        )

    @classmethod
    def _merge_document_elements(
        cls,
        elements: list[LayoutElement],
        table_cells: list[TableCell],
        *,
        page_width: float,
        offset_x: float,
        offset_y: float,
    ) -> list[LayoutElement]:
        if not table_cells:
            return cls._merge_in_reading_order(
                elements,
                [],
                page_width,
                page_left=offset_x,
            )

        cell_elements: dict[TableCell, list[LayoutElement]] = {
            cell: [] for cell in table_cells
        }
        outside_elements: list[LayoutElement] = []

        for element in elements:
            element_x2 = element.x2 if element.x2 is not None else element.x
            element_y2 = element.y2 if element.y2 is not None else element.y
            center_x = (element.x + element_x2) / 2 - offset_x
            center_y = (element.y + element_y2) / 2 - offset_y
            containing_cell = next(
                (cell for cell in table_cells if cell.contains(center_x, center_y)),
                None,
            )

            if containing_cell is None:
                outside_elements.append(element)
            else:
                cell_elements[containing_cell].append(element)

        table_rows = cls._build_table_rows(
            table_cells,
            cell_elements,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        return cls._merge_in_reading_order(
            outside_elements,
            table_rows,
            page_width,
            page_left=offset_x,
        )

    @classmethod
    def _merge_in_reading_order(
        cls,
        elements: list[LayoutElement],
        atomic_elements: list[LayoutElement],
        page_width: float,
        *,
        page_left: float = 0,
    ) -> list[LayoutElement]:
        groups = build_reading_groups(
            elements,
            atomic_elements,
            page_width=page_width,
            page_left=page_left,
        )
        if groups is None:
            merged = cls._merge_same_line_elements(elements)
            merged.extend(atomic_elements)
            merged.sort(key=lambda element: (element.y, element.x))
            return merged

        ordered: list[LayoutElement] = []
        for group in groups:
            if group.atomic:
                ordered.extend(group.elements)
            else:
                ordered.extend(cls._merge_same_line_elements(group.elements))
        return ordered

    @classmethod
    def _build_table_rows(
        cls,
        cells: list[TableCell],
        cell_elements: dict[TableCell, list[LayoutElement]],
        *,
        offset_x: float,
        offset_y: float,
    ) -> list[LayoutElement]:
        rows: dict[tuple[int, int], list[TableCell]] = {}
        for cell in cells:
            rows.setdefault((cell.table_id, cell.row), []).append(cell)

        table_rows: list[LayoutElement] = []
        for (table_id, table_row), row_cells in rows.items():
            ordered_cells = sorted(row_cells, key=lambda cell: cell.column)
            contents = [
                cls._format_cell_content(cell_elements[cell])
                for cell in ordered_cells
            ]
            if not any(contents):
                continue

            row_ocr_elements = [
                element
                for cell in ordered_cells
                for element in cell_elements[cell]
            ]
            confidences = [
                element.confidence
                for element in row_ocr_elements
                if element.confidence is not None
            ]

            table_rows.append(
                LayoutElement(
                    x=min(cell.x1 for cell in ordered_cells) + offset_x,
                    y=min(cell.y1 for cell in ordered_cells) + offset_y,
                    x2=max(cell.x2 for cell in ordered_cells) + offset_x,
                    y2=max(cell.y2 for cell in ordered_cells) + offset_y,
                    content=" | ".join(contents),
                    source="ocr",
                    confidence=(
                        sum(confidences) / len(confidences)
                        if confidences
                        else None
                    ),
                    element_type="TABLE_HEADER" if table_row == 0 else "TABLE_ROW",
                    element_type_source="AUTO",
                    table_id=table_id,
                    table_row=table_row,
                )
            )

        return table_rows

    @classmethod
    def _format_cell_content(cls, elements: list[LayoutElement]) -> str:
        if not elements:
            return ""

        lines = cls._merge_same_line_elements(elements)
        contents = [line.content.strip() for line in lines if line.content.strip()]

        # 좁은 표 셀에서 한 글자씩 세로로 검출된 경우 단어로 복원한다.
        if contents and all(len(content) == 1 for content in contents):
            return "".join(contents)

        return " ".join(contents)

    @classmethod
    def _merge_same_line_elements(
        cls,
        elements: list[LayoutElement],
    ) -> list[LayoutElement]:
        """세로 위치가 겹치는 OCR 박스를 한 줄로 병합한다."""
        if len(elements) < 2:
            return elements

        lines: list[list[LayoutElement]] = []

        for element in sorted(elements, key=cls._vertical_sort_key):
            matching_line = next(
                (line for line in lines if cls._belongs_to_line(element, line)),
                None,
            )

            if matching_line is None:
                lines.append([element])
            else:
                matching_line.append(element)

        merged = [
            cls._merge_line(part)
            for line in lines
            for part in cls._split_distant_line_elements(line)
        ]
        merged.sort(key=lambda element: (element.y, element.x))
        return merged

    @staticmethod
    def _split_distant_line_elements(
        line: list[LayoutElement],
    ) -> list[list[LayoutElement]]:
        """세로 위치만 겹치는 서로 다른 좌우 단락을 한 줄로 합치지 않는다."""
        ordered = sorted(line, key=lambda element: element.x)
        if len(ordered) < 2:
            return [ordered]

        groups: list[list[LayoutElement]] = [[ordered[0]]]
        for previous, current in zip(ordered, ordered[1:]):
            previous_x2 = previous.x2 if previous.x2 is not None else previous.x
            previous_y2 = previous.y2 if previous.y2 is not None else previous.y
            current_y2 = current.y2 if current.y2 is not None else current.y
            gap = current.x - previous_x2
            average_height = (
                max(previous_y2 - previous.y, 1.0)
                + max(current_y2 - current.y, 1.0)
            ) / 2

            if gap > average_height * 6.0:
                groups.append([current])
            else:
                groups[-1].append(current)
        return groups

    @staticmethod
    def _vertical_sort_key(element: LayoutElement) -> tuple[float, float]:
        y2 = element.y2 if element.y2 is not None else element.y
        return ((element.y + y2) / 2, element.x)

    @classmethod
    def _belongs_to_line(
        cls,
        element: LayoutElement,
        line: list[LayoutElement],
    ) -> bool:
        element_y2 = element.y2 if element.y2 is not None else element.y
        line_y1 = min(item.y for item in line)
        line_y2 = max(item.y2 if item.y2 is not None else item.y for item in line)

        element_height = max(element_y2 - element.y, 1.0)
        line_height = max(line_y2 - line_y1, 1.0)
        overlap = max(0.0, min(element_y2, line_y2) - max(element.y, line_y1))
        overlap_ratio = overlap / min(element_height, line_height)

        return overlap_ratio >= cls._LINE_OVERLAP_RATIO

    @classmethod
    def _merge_line(cls, line: list[LayoutElement]) -> LayoutElement:
        ordered = sorted(line, key=lambda element: element.x)
        parts = [ordered[0].content]

        for previous, current in zip(ordered, ordered[1:]):
            parts.append(cls._separator_between(previous, current))
            parts.append(current.content)

        confidences = [
            element.confidence
            for element in ordered
            if element.confidence is not None
        ]

        return LayoutElement(
            x=min(element.x for element in ordered),
            y=min(element.y for element in ordered),
            x2=max(
                element.x2 if element.x2 is not None else element.x
                for element in ordered
            ),
            y2=max(
                element.y2 if element.y2 is not None else element.y
                for element in ordered
            ),
            content="".join(parts),
            source="ocr",
            confidence=(
                sum(confidences) / len(confidences)
                if confidences
                else None
            ),
        )

    @classmethod
    def _separator_between(
        cls,
        previous: LayoutElement,
        current: LayoutElement,
    ) -> str:
        previous_x2 = previous.x2 if previous.x2 is not None else previous.x
        gap = current.x - previous_x2

        previous_y2 = previous.y2 if previous.y2 is not None else previous.y
        current_y2 = current.y2 if current.y2 is not None else current.y
        average_height = (
            max(previous_y2 - previous.y, 1.0)
            + max(current_y2 - current.y, 1.0)
        ) / 2

        # PaddleOCR가 한글 한 단어를 한 글자 박스로 잘게 나눈 경우에는
        # 박스 사이가 가까울 때 공백 없이 원래 단어로 복원한다.
        if (
            len(previous.content) == 1
            and len(current.content) == 1
            and gap <= average_height * cls._CHAR_JOIN_GAP_RATIO
        ):
            return ""

        # 겹치거나 거의 붙은 박스는 하나의 문자열 조각으로 본다.
        if gap <= average_height * 0.15:
            return ""

        return " "
