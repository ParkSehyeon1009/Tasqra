from dataclasses import dataclass

import numpy as np

from app.extractors.layout import LayoutElement


@dataclass(frozen=True)
class ReadingGroup:
    elements: list[LayoutElement]
    atomic: bool = False


@dataclass(frozen=True)
class _ReadingItem:
    element: LayoutElement
    atomic: bool = False


@dataclass(frozen=True)
class _Cut:
    axis: str
    position: float
    gap: float
    score: float


def build_reading_groups(
    elements: list[LayoutElement],
    atomic_elements: list[LayoutElement],
    *,
    page_width: float,
    page_left: float = 0,
) -> list[ReadingGroup] | None:
    """확실한 공백으로 나뉘는 영역만 재귀적으로 읽기 순서를 계산한다."""
    if len(elements) < 6 or page_width <= 0:
        return None

    items = [
        *(_ReadingItem(element) for element in elements),
        *(_ReadingItem(element, atomic=True) for element in atomic_elements),
    ]
    groups, did_split = _recursive_xy_cut(
        items,
        page_width=page_width,
        page_left=page_left,
        depth=0,
    )
    return groups if did_split else None


def _recursive_xy_cut(
    items: list[_ReadingItem],
    *,
    page_width: float,
    page_left: float,
    depth: int,
) -> tuple[list[ReadingGroup], bool]:
    if len(items) <= 1 or depth >= 32:
        return _leaf_groups(items), False

    if _is_single_line(items):
        return _leaf_groups(items), False

    cut = _choose_cut(items, page_width=page_width, page_left=page_left)
    if cut is None:
        return _leaf_groups(items), False

    first, second = _partition(items, cut)
    if not first or not second:
        return _leaf_groups(items), False

    first_groups, _ = _recursive_xy_cut(
        first,
        page_width=page_width,
        page_left=page_left,
        depth=depth + 1,
    )
    second_groups, _ = _recursive_xy_cut(
        second,
        page_width=page_width,
        page_left=page_left,
        depth=depth + 1,
    )
    return first_groups + second_groups, True


def _choose_cut(
    items: list[_ReadingItem],
    *,
    page_width: float,
    page_left: float,
) -> _Cut | None:
    median_height = float(
        np.median([max(_height(item.element), 1.0) for item in items])
    )
    horizontal = _best_horizontal_cut(items, median_height)
    vertical = _best_vertical_cut(
        items,
        median_height=median_height,
        page_width=page_width,
        page_left=page_left,
    )

    if horizontal is None:
        return vertical
    if vertical is None:
        return horizontal
    return vertical if vertical.score > horizontal.score else horizontal


def _best_horizontal_cut(
    items: list[_ReadingItem],
    median_height: float,
) -> _Cut | None:
    minimum_gap = max(median_height * 0.20, 2.0)
    candidates: list[_Cut] = []
    for gap_start, gap_end in _projection_gaps(items, axis="y"):
        gap = gap_end - gap_start
        if gap < minimum_gap:
            continue
        position = (gap_start + gap_end) / 2
        above = [item for item in items if _center_y(item.element) < position]
        below = [item for item in items if _center_y(item.element) > position]
        if not above or not below:
            continue
        candidates.append(
            _Cut(
                axis="y",
                position=position,
                gap=gap,
                score=gap / median_height,
            )
        )
    atomic_y = [
        _center_y(item.element)
        for item in items
        if item.atomic
    ]
    if atomic_y:
        before_table = [
            cut for cut in candidates if cut.position < min(atomic_y)
        ]
        if before_table:
            return max(before_table, key=lambda cut: cut.position)
    return min(candidates, key=lambda cut: cut.position, default=None)


def _best_vertical_cut(
    items: list[_ReadingItem],
    *,
    median_height: float,
    page_width: float,
    page_left: float,
) -> _Cut | None:
    minimum_gap = max(page_width * 0.018, median_height * 1.10)
    candidates: list[_Cut] = []
    for gap_start, gap_end in _projection_gaps(items, axis="x"):
        gap = gap_end - gap_start
        if gap < minimum_gap:
            continue
        position = (gap_start + gap_end) / 2
        center_ratio = (position - page_left) / page_width
        if not 0.20 <= center_ratio <= 0.80:
            continue

        left = [item for item in items if _center_x(item.element) < position]
        right = [item for item in items if _center_x(item.element) > position]
        if not _valid_column_children(left, right):
            continue

        candidates.append(
            _Cut(
                axis="x",
                position=position,
                gap=gap,
                score=gap / median_height,
            )
        )
    return max(candidates, key=lambda cut: cut.score, default=None)


def _valid_column_children(
    left: list[_ReadingItem],
    right: list[_ReadingItem],
) -> bool:
    if len(left) < 3 or len(right) < 3:
        return False
    if min(len(left), len(right)) / max(len(left), len(right)) < 0.20:
        return False
    if _line_count(left) < 3 or _line_count(right) < 3:
        return False

    left_width = _items_width(left)
    right_width = _items_width(right)
    combined_width = max(
        max(_x2(item.element) for item in right)
        - min(item.element.x for item in left),
        1.0,
    )
    if min(left_width, right_width) / combined_width < 0.15:
        return False

    overlap = max(
        0.0,
        min(_items_y2(left), _items_y2(right))
        - max(_items_y1(left), _items_y1(right)),
    )
    shorter_height = min(_items_height(left), _items_height(right))
    return overlap / max(shorter_height, 1.0) >= 0.35


def _projection_gaps(
    items: list[_ReadingItem],
    *,
    axis: str,
) -> list[tuple[float, float]]:
    if axis == "x":
        intervals = []
        for line in _group_item_lines(items):
            if _looks_like_spaced_heading(line):
                intervals.append(
                    (
                        min(item.element.x for item in line),
                        max(_x2(item.element) for item in line),
                    )
                )
            else:
                intervals.extend(
                    (item.element.x, _x2(item.element))
                    for item in line
                )
        intervals.sort()
    else:
        intervals = sorted(
            (item.element.y, _y2(item.element))
            for item in items
        )

    gaps: list[tuple[float, float]] = []
    current_end = intervals[0][1]
    for start, end in intervals[1:]:
        if start > current_end:
            gaps.append((current_end, start))
        current_end = max(current_end, end)
    return gaps


def _partition(
    items: list[_ReadingItem],
    cut: _Cut,
) -> tuple[list[_ReadingItem], list[_ReadingItem]]:
    if cut.axis == "x":
        first = [item for item in items if _center_x(item.element) < cut.position]
        second = [item for item in items if _center_x(item.element) > cut.position]
    else:
        first = [item for item in items if _center_y(item.element) < cut.position]
        second = [item for item in items if _center_y(item.element) > cut.position]
    return first, second


def _leaf_groups(items: list[_ReadingItem]) -> list[ReadingGroup]:
    if not items:
        return []

    ordered = sorted(
        items,
        key=lambda item: (_center_y(item.element), item.element.x),
    )
    groups: list[ReadingGroup] = []
    pending: list[LayoutElement] = []

    for item in ordered:
        if item.atomic:
            if pending:
                groups.append(ReadingGroup(pending))
                pending = []
            groups.append(ReadingGroup([item.element], atomic=True))
        else:
            pending.append(item.element)

    if pending:
        groups.append(ReadingGroup(pending))
    return groups


def _is_single_line(items: list[_ReadingItem]) -> bool:
    if any(item.atomic for item in items):
        return False
    y1 = max(item.element.y for item in items)
    y2 = min(_y2(item.element) for item in items)
    minimum_height = min(max(_height(item.element), 1.0) for item in items)
    return max(0.0, y2 - y1) / minimum_height >= 0.45


def _line_count(items: list[_ReadingItem]) -> int:
    return len(_group_item_lines(items))


def _group_item_lines(
    items: list[_ReadingItem],
) -> list[list[_ReadingItem]]:
    lines: list[list[_ReadingItem]] = []
    for item in sorted(items, key=lambda value: _center_y(value.element)):
        element = item.element
        matching = next(
            (
                line
                for line in lines
                if _vertical_overlap(
                    element,
                    [line_item.element for line_item in line],
                )
                >= 0.45
            ),
            None,
        )
        if matching is None:
            lines.append([item])
        else:
            matching.append(item)
    return lines


def _looks_like_spaced_heading(line: list[_ReadingItem]) -> bool:
    if len(line) < 3 or any(item.atomic for item in line):
        return False
    median_height = float(
        np.median([max(_height(item.element), 1.0) for item in line])
    )
    narrow_count = sum(
        max(_x2(item.element) - item.element.x, 1.0)
        <= median_height * 2.5
        for item in line
    )
    return narrow_count == len(line)


def _vertical_overlap(
    element: LayoutElement,
    line: list[LayoutElement],
) -> float:
    line_y1 = min(item.y for item in line)
    line_y2 = max(_y2(item) for item in line)
    overlap = max(0.0, min(_y2(element), line_y2) - max(element.y, line_y1))
    return overlap / min(max(_height(element), 1.0), max(line_y2 - line_y1, 1.0))


def _items_width(items: list[_ReadingItem]) -> float:
    return max(_x2(item.element) for item in items) - min(
        item.element.x for item in items
    )


def _items_height(items: list[_ReadingItem]) -> float:
    return _items_y2(items) - _items_y1(items)


def _items_y1(items: list[_ReadingItem]) -> float:
    return min(item.element.y for item in items)


def _items_y2(items: list[_ReadingItem]) -> float:
    return max(_y2(item.element) for item in items)


def _height(element: LayoutElement) -> float:
    return _y2(element) - element.y


def _x2(element: LayoutElement) -> float:
    return element.x2 if element.x2 is not None else element.x


def _y2(element: LayoutElement) -> float:
    return element.y2 if element.y2 is not None else element.y


def _center_x(element: LayoutElement) -> float:
    return (element.x + _x2(element)) / 2


def _center_y(element: LayoutElement) -> float:
    return (element.y + _y2(element)) / 2
