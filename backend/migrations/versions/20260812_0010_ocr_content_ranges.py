"""track OCR element ranges in extracted content"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0010"
down_revision = "20260812_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_elements", sa.Column("content_start", sa.Integer(), nullable=True))
    op.add_column("ocr_elements", sa.Column("content_end", sa.Integer(), nullable=True))
    op.add_column("ocr_elements", sa.Column("is_in_content", sa.Boolean(), nullable=False, server_default=sa.true()))

    connection = op.get_bind()
    documents = connection.execute(sa.text("SELECT document_id, content FROM extracted_texts")).mappings().all()
    for document in documents:
        elements = connection.execute(sa.text("""
            SELECT oe.id, oe.text, oe.is_excluded, d.review_status
            FROM ocr_elements oe
            JOIN document_pages dp ON dp.id = oe.page_id
            JOIN documents d ON d.id = dp.document_id
            WHERE dp.document_id = :document_id AND oe.is_deleted = false
            ORDER BY dp.page_number, oe.reading_order, oe.id
        """), {"document_id": document["document_id"]}).mappings().all()
        cursor = 0
        for index, element in enumerate(elements):
            is_in_content = not (element["is_excluded"] and element["review_status"] == "COMPLETED")
            occurrences = []
            search_cursor = cursor
            while is_in_content:
                occurrence = document["content"].find(element["text"], search_cursor)
                if occurrence < 0:
                    break
                occurrences.append(occurrence)
                search_cursor = occurrence + max(len(element["text"]), 1)
            remaining_matches = sum(
                1
                for candidate in elements[index:]
                if candidate["text"] == element["text"]
                and not (candidate["is_excluded"] and candidate["review_status"] == "COMPLETED")
            )
            start = occurrences[0] if len(occurrences) == remaining_matches and occurrences else -1
            end = start + len(element["text"]) if start >= 0 else None
            if end is not None:
                cursor = end
            connection.execute(sa.text("""
                UPDATE ocr_elements
                SET content_start = :content_start,
                    content_end = :content_end,
                    is_in_content = :is_in_content
                WHERE id = :element_id
            """), {"content_start": start if start >= 0 else None, "content_end": end, "is_in_content": is_in_content, "element_id": element["id"]})

    op.create_check_constraint("ck_ocr_element_content_start", "ocr_elements", "content_start IS NULL OR content_start >= 0")
    op.create_check_constraint("ck_ocr_element_content_end", "ocr_elements", "content_end IS NULL OR content_end >= content_start")


def downgrade():
    op.drop_constraint("ck_ocr_element_content_end", "ocr_elements", type_="check")
    op.drop_constraint("ck_ocr_element_content_start", "ocr_elements", type_="check")
    op.drop_column("ocr_elements", "is_in_content")
    op.drop_column("ocr_elements", "content_end")
    op.drop_column("ocr_elements", "content_start")
