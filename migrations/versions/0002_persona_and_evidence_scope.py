"""Add data-driven persona and evidence scope."""

from alembic import op

revision = "0002_persona_and_evidence_scope"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE characters ADD COLUMN persona jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE knowledge_documents ADD COLUMN evidence_scope text "
        "NOT NULL DEFAULT 'character'"
    )
    op.execute(
        "ALTER TABLE knowledge_documents ADD CONSTRAINT ck_documents_evidence_scope "
        "CHECK (evidence_scope IN ('character', 'contextual'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS "
        "ck_documents_evidence_scope"
    )
    op.execute("ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS evidence_scope")
    op.execute("ALTER TABLE characters DROP COLUMN IF EXISTS persona")
