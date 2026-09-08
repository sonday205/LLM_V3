from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    id: str
    sort_order: int
    display_name: str
    self_pronoun: str
    student_pronoun: str
    audience: str
    tone: str
    short_description: str


@dataclass(frozen=True, slots=True)
class SourceReference:
    chunk_id: str
    document_id: str
    title: str
    source_name: str | None
    source_url: str | None
    score: float


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    document_id: str
    content: str
    title: str
    source_name: str | None
    source_url: str | None
    score: float


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    status: str
    chunks: tuple[RetrievedChunk, ...] = ()

    @property
    def grounded(self) -> bool:
        return bool(self.chunks)

    def prompt_context(self) -> str:
        if self.status == "not_used":
            return "Không dùng tư liệu lịch sử cho lượt hội thoại này."
        if not self.chunks:
            return "Không tìm thấy tư liệu liên quan đủ mạnh. Không được tự đoán dữ kiện lịch sử."
        return "\n\n".join(
            f"[S{index}] {chunk.content}\nNguồn: {chunk.source_name or chunk.title}"
            for index, chunk in enumerate(self.chunks, 1)
        )

    def sources(self) -> list[SourceReference]:
        return [
            SourceReference(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=chunk.title,
                source_name=chunk.source_name,
                source_url=chunk.source_url,
                score=round(chunk.score, 6),
            )
            for chunk in self.chunks
        ]


@dataclass(frozen=True, slots=True)
class MemoryContext:
    facts: dict[str, str] = field(default_factory=dict)
    recent_turns: tuple[tuple[str, str], ...] = ()
    relevant_messages: tuple[tuple[str, str], ...] = ()

    @property
    def used(self) -> bool:
        return bool(self.facts or self.recent_turns or self.relevant_messages)

    def as_prompt_text(self) -> str:
        parts: list[str] = []
        if self.facts:
            parts.append("Thông tin an toàn đã nhớ: " + "; ".join(f"{k}: {v}" for k, v in self.facts.items()))
        if self.recent_turns:
            turns = "\n".join(f"- Học sinh: {user}\n  Nhân vật: {answer}" for user, answer in self.recent_turns)
            parts.append("Hội thoại gần đây:\n" + turns)
        if self.relevant_messages:
            related = "\n".join(f"- {role}: {content}" for role, content in self.relevant_messages)
            parts.append("Lượt cũ liên quan:\n" + related)
        return "\n".join(parts) if parts else "Chưa có memory an toàn cho phiên này."
