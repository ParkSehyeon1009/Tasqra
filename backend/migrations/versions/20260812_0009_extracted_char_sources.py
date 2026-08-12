"""store native text and OCR character counts separately"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0009"
down_revision = "20260812_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extracted_texts",
        sa.Column("text_char_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "extracted_texts",
        sa.Column("ocr_char_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE extracted_texts
        SET text_char_count = CASE
                WHEN extract_method = 'OCR' THEN 0
                ELSE COALESCE(char_count, 0)
            END,
            ocr_char_count = CASE
                WHEN extract_method = 'OCR' THEN COALESCE(char_count, 0)
                ELSE 0
            END
        """
    )
    op.create_check_constraint(
        "ck_extracted_text_char_count",
        "extracted_texts",
        "text_char_count >= 0",
    )
    op.create_check_constraint(
        "ck_extracted_ocr_char_count",
        "extracted_texts",
        "ocr_char_count >= 0",
    )


def downgrade():
    op.drop_constraint(
        "ck_extracted_ocr_char_count", "extracted_texts", type_="check"
    )
    op.drop_constraint(
        "ck_extracted_text_char_count", "extracted_texts", type_="check"
    )
    op.drop_column("extracted_texts", "ocr_char_count")
    op.drop_column("extracted_texts", "text_char_count")
