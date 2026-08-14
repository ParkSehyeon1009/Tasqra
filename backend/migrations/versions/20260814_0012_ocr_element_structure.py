"""add OCR element structure metadata for paragraph-aware chunking"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0012"
down_revision = "20260814_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_elements", sa.Column("element_type_source", sa.String(20), nullable=False, server_default="AUTO"))
    op.add_column("ocr_elements", sa.Column("is_paragraph_start", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("ocr_elements", sa.Column("table_id", sa.Integer(), nullable=True))
    op.add_column("ocr_elements", sa.Column("table_row", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_ocr_element_type",
        "ocr_elements",
        "element_type IN ('TEXT_LINE', 'HEADING', 'TABLE_ROW', 'TABLE_HEADER', 'HEADER_FOOTER')",
    )
    op.create_check_constraint(
        "ck_ocr_element_type_source",
        "ocr_elements",
        "element_type_source IN ('AUTO', 'USER', 'USER_CORRECTED')",
    )
    op.create_check_constraint("ck_ocr_element_table_id", "ocr_elements", "table_id IS NULL OR table_id >= 0")
    op.create_check_constraint("ck_ocr_element_table_row", "ocr_elements", "table_row IS NULL OR table_row >= 0")


def downgrade():
    op.drop_constraint("ck_ocr_element_table_row", "ocr_elements", type_="check")
    op.drop_constraint("ck_ocr_element_table_id", "ocr_elements", type_="check")
    op.drop_constraint("ck_ocr_element_type_source", "ocr_elements", type_="check")
    op.drop_constraint("ck_ocr_element_type", "ocr_elements", type_="check")
    op.drop_column("ocr_elements", "table_row")
    op.drop_column("ocr_elements", "table_id")
    op.drop_column("ocr_elements", "is_paragraph_start")
    op.drop_column("ocr_elements", "element_type_source")
