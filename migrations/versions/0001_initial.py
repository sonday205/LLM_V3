"""Create RAG and safe-memory tables."""

from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE characters (
            id text PRIMARY KEY,
            sort_order integer NOT NULL,
            display_name text NOT NULL,
            self_pronoun text NOT NULL,
            student_pronoun text NOT NULL,
            audience text NOT NULL,
            tone text NOT NULL,
            short_description text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_documents (
            id text PRIMARY KEY,
            character_id text NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            title text NOT NULL,
            source_name text,
            source_url text,
            source_type text,
            confidence text,
            checksum text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
            id text PRIMARY KEY,
            document_id text NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
            character_id text NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            content text NOT NULL,
            embedding vector(1024) NOT NULL,
            search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX ix_chunks_character ON knowledge_chunks(character_id)")
    op.execute("CREATE INDEX ix_chunks_search ON knowledge_chunks USING gin(search_vector)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        """
        CREATE TABLE chat_sessions (
            id uuid PRIMARY KEY,
            client_scope text NOT NULL,
            character_id text NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            session_id text NOT NULL,
            facts jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            UNIQUE(client_scope, character_id, session_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_expiry ON chat_sessions(expires_at)")
    op.execute(
        """
        CREATE TABLE conversation_messages (
            sequence bigserial UNIQUE,
            id uuid PRIMARY KEY,
            session_pk uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL,
            embedding vector(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_messages_session_sequence ON conversation_messages(session_pk, sequence DESC)")
    op.execute(
        "CREATE INDEX ix_messages_embedding_hnsw ON conversation_messages "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_messages")
    op.execute("DROP TABLE IF EXISTS chat_sessions")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS knowledge_documents")
    op.execute("DROP TABLE IF EXISTS characters")
