from __future__ import annotations

import asyncio
import re
from collections import defaultdict

from app.database import Database
from app.domain import RetrievalResult, RetrievedChunk
from app.embeddings import EmbeddingProvider


class RetrievalPolicy:
    """Không để tư liệu lịch sử lấn át các lượt thuần hội thoại/memory."""

    _MEMORY_QUERY = re.compile(
        r"\b(?:nhớ|tóm tắt.{0,20}(?:trò chuyện|hội thoại)|vừa (?:hỏi|nói)|"
        r"tên gọi|học lớp mấy|sở thích|điều gì về (?:em|cháu|con))\b",
        flags=re.IGNORECASE,
    )
    _SAFE_FACT_DECLARATION = re.compile(
        r"\b(?:em|cháu|con)\s+(?:đang\s+)?(?:tên là|học lớp|thích|quan tâm)\b|"
        r"\bgọi (?:em|cháu|con) là\b",
        flags=re.IGNORECASE,
    )

    @classmethod
    def should_retrieve_history(cls, query: str) -> bool:
        return not (cls._MEMORY_QUERY.search(query) or cls._SAFE_FACT_DECLARATION.search(query))


class HybridRetriever:
    def __init__(self, database: Database, embeddings: EmbeddingProvider, limit: int = 6) -> None:
        self.database = database
        self.embeddings = embeddings
        self.limit = limit

    async def retrieve(self, character_id: str, query: str) -> RetrievalResult:
        query_embedding = (await asyncio.to_thread(self.embeddings.encode, [query]))[0]
        candidate_limit = max(self.limit * 3, 12)
        semantic, lexical = await asyncio.gather(
            self.database.semantic_chunks(character_id, query_embedding, candidate_limit),
            self.database.lexical_chunks(character_id, query, candidate_limit),
        )
        if not lexical and (not semantic or float(semantic[0]["score"]) < 0.28):
            return RetrievalResult(status="not_found")

        fused_scores: dict[str, float] = defaultdict(float)
        rows: dict[str, dict] = {}
        for ranking in (semantic, lexical):
            for rank, row in enumerate(ranking, 1):
                rows[row["id"]] = row
                fused_scores[row["id"]] += 1.0 / (60 + rank)

        selected: list[RetrievedChunk] = []
        per_document: dict[str, int] = defaultdict(int)
        for chunk_id in sorted(fused_scores, key=fused_scores.get, reverse=True):
            row = rows[chunk_id]
            if per_document[row["document_id"]] >= 2:
                continue
            selected.append(
                RetrievedChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    title=row["title"],
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    score=fused_scores[chunk_id],
                    evidence_scope=row["evidence_scope"],
                )
            )
            per_document[row["document_id"]] += 1
            if len(selected) >= self.limit:
                break
        return RetrievalResult(
            status="grounded" if selected else "not_found", chunks=tuple(selected)
        )
