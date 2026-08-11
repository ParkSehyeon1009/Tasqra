"""core users, projects and documents"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260810_0001"
down_revision = None
branch_labels = None
depends_on = None

def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]

def upgrade():
    op.create_table("users", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("email", sa.String(255), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("name", sa.String(100), nullable=False), sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False), *timestamps())
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")
    op.create_table("projects", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.Text()), sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False), sa.Column("started_on", sa.Date()), sa.Column("due_on", sa.Date()), *timestamps(), sa.CheckConstraint("started_on IS NULL OR due_on IS NULL OR started_on <= due_on", name="ck_project_dates"))
    op.create_table("project_members", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"), sa.CheckConstraint("role IN ('OWNER', 'EDITOR', 'VIEWER')", name="ck_project_member_role"))
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.create_table("documents", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("uploaded_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("filename", sa.String(500), nullable=False), sa.Column("storage_path", sa.String(1000), nullable=False), sa.Column("file_type", sa.String(20), nullable=False), sa.Column("file_size", sa.BigInteger(), nullable=False), sa.Column("content_hash", sa.String(64)), sa.Column("document_type", sa.String(30)), sa.Column("document_type_source", sa.String(20)), sa.Column("status", sa.String(20), server_default="PENDING", nullable=False), sa.Column("processing_mode", sa.String(20), server_default="NORMAL", nullable=False), sa.Column("review_status", sa.String(20), server_default="NOT_REQUIRED", nullable=False), sa.Column("reviewed_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("ocr_revision", sa.Integer(), server_default="1", nullable=False), sa.Column("category_cache", sa.String(30)), sa.Column("summary_preview", sa.String(300)), *timestamps(), sa.CheckConstraint("file_size >= 0", name="ck_document_file_size"), sa.CheckConstraint("ocr_revision >= 1", name="ck_document_ocr_revision"))
    op.create_index("ix_doc_list", "documents", ["project_id", "created_at"])
    op.create_index("ix_doc_type", "documents", ["project_id", "document_type"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_table("extracted_texts", sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True), sa.Column("content", sa.Text(), nullable=False), sa.Column("page_count", sa.Integer()), sa.Column("char_count", sa.Integer()), sa.Column("extract_method", sa.String(20)), sa.Column("text_version", sa.Integer(), server_default="1", nullable=False), sa.Column("is_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False), sa.Column("confirmed_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("confirmed_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_extracted_page_count"), sa.CheckConstraint("char_count IS NULL OR char_count >= 0", name="ck_extracted_char_count"), sa.CheckConstraint("text_version >= 1", name="ck_extracted_text_version"))
    op.create_table("analyses", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("analyzer_type", sa.String(30), nullable=False), sa.Column("result_json", postgresql.JSONB(), nullable=False), sa.Column("provider", sa.String(30), nullable=False), sa.Column("model_name", sa.String(100), nullable=False), sa.Column("prompt_version", sa.String(20)), sa.Column("tokens_in", sa.Integer()), sa.Column("tokens_out", sa.Integer()), sa.Column("latency_ms", sa.Integer()), sa.Column("source_text_revision", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_analysis_doc_type", "analyses", ["document_id", "analyzer_type"])

def downgrade():
    op.drop_table("analyses")
    op.drop_table("extracted_texts")
    op.drop_table("documents")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("users")
