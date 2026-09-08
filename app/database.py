from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.domain import CharacterProfile
from app.embeddings import vector_literal
from app.knowledge import KnowledgeDocument


EXPECTED_CHARACTER_COUNT = 14


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)

    async def close(self) -> None:
        await self.engine.dispose()

    async def health(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                return bool((await connection.execute(text("SELECT 1"))).scalar_one())
        except Exception:
            return False

    async def ready(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            """SELECT count(DISTINCT character_id) AS character_count,
                                      count(*) AS chunk_count
                               FROM knowledge_chunks"""
                        )
                    )
                ).mappings().one()
                return (
                    int(row["character_count"]) == EXPECTED_CHARACTER_COUNT
                    and int(row["chunk_count"]) > 0
                )
        except Exception:
            return False

    async def list_characters(self) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """SELECT id, sort_order, display_name, self_pronoun, student_pronoun,
                              short_description FROM characters ORDER BY sort_order, display_name"""
                )
            )
            return [dict(row) for row in rows.mappings()]

    async def get_character(self, character_id: str) -> CharacterProfile | None:
        async with self.engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT * FROM characters WHERE id=:character_id"),
                    {"character_id": character_id},
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        return CharacterProfile(
            id=row["id"],
            sort_order=row["sort_order"],
            display_name=row["display_name"],
            self_pronoun=row["self_pronoun"],
            student_pronoun=row["student_pronoun"],
            audience=row["audience"],
            tone=row["tone"],
            short_description=row["short_description"],
        )

    async def ingest_character(
        self,
        profile: CharacterProfile,
        documents: Sequence[KnowledgeDocument],
        embeddings: dict[str, list[float]],
    ) -> tuple[int, int]:
        document_count = 0
        chunk_count = 0
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO characters
                      (id, sort_order, display_name, self_pronoun, student_pronoun, audience, tone, short_description)
                    VALUES
                      (:id, :sort_order, :display_name, :self_pronoun, :student_pronoun, :audience, :tone, :short_description)
                    ON CONFLICT (id) DO UPDATE SET
                      sort_order=EXCLUDED.sort_order, display_name=EXCLUDED.display_name,
                      self_pronoun=EXCLUDED.self_pronoun, student_pronoun=EXCLUDED.student_pronoun,
                      audience=EXCLUDED.audience, tone=EXCLUDED.tone,
                      short_description=EXCLUDED.short_description, updated_at=now()
                    """
                ),
                profile.__dict__ if hasattr(profile, "__dict__") else {
                    name: getattr(profile, name) for name in profile.__slots__
                },
            )
            await connection.execute(
                text("DELETE FROM knowledge_documents WHERE character_id=:character_id"),
                {"character_id": profile.id},
            )
            for document in documents:
                await connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_documents
                          (id, character_id, title, source_name, source_url, source_type, confidence, checksum)
                        VALUES (:id, :character_id, :title, :source_name, :source_url,
                                :source_type, :confidence, :checksum)
                        """
                    ),
                    {
                        "id": document.id,
                        "character_id": document.character_id,
                        "title": document.title,
                        "source_name": document.source_name,
                        "source_url": document.source_url,
                        "source_type": document.source_type,
                        "confidence": document.confidence,
                        "checksum": document.checksum,
                    },
                )
                document_count += 1
                for chunk in document.chunks:
                    await connection.execute(
                        text(
                            """
                            INSERT INTO knowledge_chunks
                              (id, document_id, character_id, content, embedding, metadata)
                            VALUES (:id, :document_id, :character_id, :content,
                                    CAST(:embedding AS vector), CAST(:metadata AS jsonb))
                            """
                        ),
                        {
                            "id": chunk.id,
                            "document_id": document.id,
                            "character_id": profile.id,
                            "content": chunk.content,
                            "embedding": vector_literal(embeddings[chunk.id]),
                            "metadata": json.dumps(chunk.metadata, ensure_ascii=False),
                        },
                    )
                    chunk_count += 1
        return document_count, chunk_count

    async def semantic_chunks(self, character_id: str, embedding: Sequence[float], limit: int) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    SELECT c.id, c.document_id, c.content, d.title, d.source_name, d.source_url,
                           1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
                    FROM knowledge_chunks c
                    JOIN knowledge_documents d ON d.id=c.document_id
                    WHERE c.character_id=:character_id
                    ORDER BY c.embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ),
                {"character_id": character_id, "embedding": vector_literal(embedding), "limit": limit},
            )
            return [dict(row) for row in rows.mappings()]

    async def lexical_chunks(self, character_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    SELECT c.id, c.document_id, c.content, d.title, d.source_name, d.source_url,
                           ts_rank_cd(c.search_vector, plainto_tsquery('simple', :query)) AS score
                    FROM knowledge_chunks c
                    JOIN knowledge_documents d ON d.id=c.document_id
                    WHERE c.character_id=:character_id
                      AND c.search_vector @@ plainto_tsquery('simple', :query)
                    ORDER BY score DESC
                    LIMIT :limit
                    """
                ),
                {"character_id": character_id, "query": query, "limit": limit},
            )
            return [dict(row) for row in rows.mappings()]

    async def purge_expired_sessions(self) -> int:
        async with self.engine.begin() as connection:
            result = await connection.execute(text("DELETE FROM chat_sessions WHERE expires_at <= now()"))
            return int(result.rowcount or 0)

    async def touch_session(
        self,
        client_scope: str,
        character_id: str,
        session_id: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        await self.purge_expired_sessions()
        session_pk = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        async with self.engine.begin() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO chat_sessions
                          (id, client_scope, character_id, session_id, expires_at)
                        VALUES (CAST(:id AS uuid), :client_scope, :character_id, :session_id, :expires_at)
                        ON CONFLICT (client_scope, character_id, session_id) DO UPDATE SET
                          updated_at=now(), expires_at=EXCLUDED.expires_at
                        RETURNING id, facts
                        """
                    ),
                    {
                        "id": session_pk,
                        "client_scope": client_scope,
                        "character_id": character_id,
                        "session_id": session_id,
                        "expires_at": expires_at,
                    },
                )
            ).mappings().one()
            return dict(row)

    async def recent_messages(self, session_pk: str, limit: int) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """SELECT id, role, content, sequence FROM conversation_messages
                       WHERE session_pk=CAST(:session_pk AS uuid)
                       ORDER BY sequence DESC LIMIT :limit"""
                ),
                {"session_pk": session_pk, "limit": limit},
            )
            return [dict(row) for row in rows.mappings()]

    async def relevant_messages(
        self,
        session_pk: str,
        embedding: Sequence[float],
        excluded_ids: Sequence[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    SELECT id, role, content,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM conversation_messages
                    WHERE session_pk=CAST(:session_pk AS uuid)
                      AND NOT (id = ANY(CAST(:excluded_ids AS uuid[])))
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ),
                {
                    "session_pk": session_pk,
                    "embedding": vector_literal(embedding),
                    "excluded_ids": list(excluded_ids),
                    "limit": limit,
                },
            )
            return [dict(row) for row in rows.mappings()]

    async def store_turn(
        self,
        session_pk: str,
        user_message: str,
        answer: str,
        user_embedding: Sequence[float],
        answer_embedding: Sequence[float],
        facts: dict[str, str],
    ) -> None:
        async with self.engine.begin() as connection:
            if facts:
                await connection.execute(
                    text(
                        """UPDATE chat_sessions SET facts=facts || CAST(:facts AS jsonb), updated_at=now()
                           WHERE id=CAST(:session_pk AS uuid)"""
                    ),
                    {"session_pk": session_pk, "facts": json.dumps(facts, ensure_ascii=False)},
                )
            for role, content, embedding in (
                ("user", user_message, user_embedding),
                ("assistant", answer, answer_embedding),
            ):
                await connection.execute(
                    text(
                        """INSERT INTO conversation_messages (id, session_pk, role, content, embedding)
                           VALUES (CAST(:id AS uuid), CAST(:session_pk AS uuid), :role, :content,
                                   CAST(:embedding AS vector))"""
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "session_pk": session_pk,
                        "role": role,
                        "content": content,
                        "embedding": vector_literal(embedding),
                    },
                )

    async def delete_session(self, client_scope: str, character_id: str, session_id: str) -> bool:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """DELETE FROM chat_sessions
                       WHERE client_scope=:client_scope AND character_id=:character_id AND session_id=:session_id"""
                ),
                {"client_scope": client_scope, "character_id": character_id, "session_id": session_id},
            )
            return bool(result.rowcount)
