from __future__ import annotations

import asyncio
import re

from app.database import Database
from app.domain import MemoryContext
from app.embeddings import EmbeddingProvider


class SafeMemoryService:
    def __init__(
        self,
        database: Database,
        embeddings: EmbeddingProvider,
        ttl_seconds: int,
        recent_turns: int,
        relevant_turns: int,
    ) -> None:
        self.database = database
        self.embeddings = embeddings
        self.ttl_seconds = ttl_seconds
        self.recent_turns = recent_turns
        self.relevant_turns = relevant_turns

    async def context(
        self,
        client_scope: str,
        character_id: str,
        session_id: str,
        query: str,
    ) -> tuple[str, MemoryContext]:
        session = await self.database.touch_session(client_scope, character_id, session_id, self.ttl_seconds)
        recent_rows = await self.database.recent_messages(str(session["id"]), self.recent_turns * 2)
        recent_rows.reverse()
        turns: list[tuple[str, str]] = []
        for index in range(0, len(recent_rows) - 1, 2):
            first, second = recent_rows[index], recent_rows[index + 1]
            if first["role"] == "user" and second["role"] == "assistant":
                turns.append((first["content"], second["content"]))

        query_embedding = (await asyncio.to_thread(self.embeddings.encode, [query]))[0]
        relevant = await self.database.relevant_messages(
            str(session["id"]),
            query_embedding,
            [str(row["id"]) for row in recent_rows],
            self.relevant_turns,
        )
        memory = MemoryContext(
            facts=dict(session.get("facts") or {}),
            recent_turns=tuple(turns),
            relevant_messages=tuple((row["role"], row["content"]) for row in relevant),
        )
        return str(session["id"]), memory

    async def store(self, session_pk: str, user_message: str, answer: str) -> None:
        user_embedding, answer_embedding = await asyncio.to_thread(
            self.embeddings.encode,
            [user_message, answer],
        )
        await self.database.store_turn(
            session_pk,
            user_message,
            answer,
            user_embedding,
            answer_embedding,
            self._extract_safe_facts(user_message),
        )

    @staticmethod
    def _extract_safe_facts(message: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        nickname = re.search(
            r"(?:gọi (?:em|cháu) là|(?:em|cháu) tên là)\s+([A-Za-zÀ-ỹĐđ][A-Za-zÀ-ỹĐđ '\u2019-]{0,24})",
            message,
            flags=re.IGNORECASE,
        )
        if nickname:
            value = re.split(r"\s+(?:và|học|lớp)\s+", nickname.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
            # Chỉ giữ nickname/tên gọi ngắn, không lưu họ tên đầy đủ.
            if len(value.split()) <= 2:
                facts["nickname"] = value.strip(" .,!?\n")
        grade = re.search(r"\b(?:học\s+)?lớp\s+([1-9]|1[0-2])(?:[A-Za-z])?\b", message, flags=re.IGNORECASE)
        if grade:
            facts["grade"] = f"lớp {grade.group(1)}"
        interest = re.search(r"(?:em|cháu) (?:thích|quan tâm)\s+(.{2,50}?)(?:[.!?]|$)", message, flags=re.IGNORECASE)
        if interest:
            facts["learning_interest"] = " ".join(interest.group(1).split())
        return facts
