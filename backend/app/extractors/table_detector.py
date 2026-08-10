from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TableCell:
    table_id: int
    row: int
    column: int
    x1: float
    y1: float
    x2: float
    y2: float

    def contains(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class TableDetector:
    """OpenCV 선 검출로 테두리가 있는 표의 셀 영역을 찾는다."""

    _MIN_CELL_SIZE = 12
    _MIN_CELLS_PER_TABLE = 4

    def detect(self, image: Image.Image) -> list[TableCell]:
        try:
            return self._detect(image)
        except cv2.error:
            # 표 검출 실패가 문서 전체 OCR 실패로 이어지지 않게 한다.
            return []

    def _detect(self, image: Image.Image) -> list[TableCell]:
        rgb = np.asarray(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        height, width = gray.shape
        if width < 40 or height < 40:
            return []

        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            15,
            10,
        )

        horizontal_length = max(width // 30, 20)
        vertical_length = max(height // 30, 20)

        horizontal = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (horizontal_length, 1),
            ),
        )
        vertical = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (1, vertical_length),
            ),
        )
        grid = cv2.bitwise_or(horizontal, vertical)

        contours, hierarchy = cv2.findContours(
            grid,
            cv2.RETR_TREE,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if hierarchy is None:
            return []

        candidates: dict[int, list[tuple[float, float, float, float]]] = {}
        hierarchy_rows = hierarchy[0]

        for index, contour in enumerate(contours):
            x, y, cell_width, cell_height = cv2.boundingRect(contour)
            parent = int(hierarchy_rows[index][3])

            # 표 외곽선이 아니라 그 안쪽 셀 contour만 사용한다.
            if parent < 0:
                continue
            if cell_width < self._MIN_CELL_SIZE or cell_height < self._MIN_CELL_SIZE:
                continue
            if cell_width >= width * 0.95 or cell_height >= height * 0.95:
                continue

            table_id = self._root_parent(index, hierarchy_rows)
            candidates.setdefault(table_id, []).append(
                (float(x), float(y), float(x + cell_width), float(y + cell_height))
            )

        cells: list[TableCell] = []
        next_table_id = 0

        for boxes in candidates.values():
            unique_boxes = self._remove_duplicate_boxes(boxes)
            if len(unique_boxes) < self._MIN_CELLS_PER_TABLE:
                continue

            rows = self._group_rows(unique_boxes)
            for row_index, row in enumerate(rows):
                for column_index, (x1, y1, x2, y2) in enumerate(
                    sorted(row, key=lambda box: box[0])
                ):
                    cells.append(
                        TableCell(
                            table_id=next_table_id,
                            row=row_index,
                            column=column_index,
                            x1=x1,
                            y1=y1,
                            x2=x2,
                            y2=y2,
                        )
                    )
            next_table_id += 1

        return cells

    @staticmethod
    def _root_parent(index: int, hierarchy: np.ndarray) -> int:
        current = index
        parent = int(hierarchy[current][3])
        while parent >= 0:
            current = parent
            parent = int(hierarchy[current][3])
        return current

    @classmethod
    def _remove_duplicate_boxes(
        cls,
        boxes: list[tuple[float, float, float, float]],
    ) -> list[tuple[float, float, float, float]]:
        unique: list[tuple[float, float, float, float]] = []
        for box in sorted(boxes, key=cls._box_area):
            if any(cls._intersection_over_union(box, saved) > 0.85 for saved in unique):
                continue
            unique.append(box)
        return unique

    @staticmethod
    def _box_area(box: tuple[float, float, float, float]) -> float:
        return max(box[2] - box[0], 0) * max(box[3] - box[1], 0)

    @classmethod
    def _intersection_over_union(
        cls,
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> float:
        x1 = max(first[0], second[0])
        y1 = max(first[1], second[1])
        x2 = min(first[2], second[2])
        y2 = min(first[3], second[3])
        intersection = max(x2 - x1, 0) * max(y2 - y1, 0)
        union = cls._box_area(first) + cls._box_area(second) - intersection
        return intersection / union if union else 0.0

    @staticmethod
    def _group_rows(
        boxes: list[tuple[float, float, float, float]],
    ) -> list[list[tuple[float, float, float, float]]]:
        rows: list[list[tuple[float, float, float, float]]] = []

        for box in sorted(boxes, key=lambda item: ((item[1] + item[3]) / 2, item[0])):
            center_y = (box[1] + box[3]) / 2
            matching_row = None

            for row in rows:
                row_center = sum((item[1] + item[3]) / 2 for item in row) / len(row)
                row_height = sum(item[3] - item[1] for item in row) / len(row)
                if abs(center_y - row_center) <= max(row_height * 0.5, 5.0):
                    matching_row = row
                    break

            if matching_row is None:
                rows.append([box])
            else:
                matching_row.append(box)

        return rows
