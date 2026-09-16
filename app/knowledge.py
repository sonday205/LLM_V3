from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domain import CharacterProfile


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    character_id: str
    title: str
    source_name: str | None
    source_url: str | None
    source_type: str | None
    confidence: str | None
    evidence_scope: str
    checksum: str
    chunks: tuple[KnowledgeChunk, ...]


class KnowledgeLoader:
    def load_profiles(self, data_dir: Path) -> tuple[CharacterProfile, ...]:
        profiles: list[CharacterProfile] = []
        for path in sorted(data_dir.glob("*/profile.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            profiles.append(
                CharacterProfile(
                    id=str(raw["id"]),
                    sort_order=int(raw.get("sort_order", 999)),
                    display_name=str(raw["display_name"]),
                    self_pronoun=str(raw.get("self_pronoun", "nhân vật")),
                    student_pronoun=str(raw.get("student_pronoun", "em")),
                    audience=str(raw.get("audience", "học sinh")),
                    tone=str(raw.get("tone", "gần gũi, điềm tĩnh")),
                    short_description=str(raw.get("short_description", "")).strip(),
                    core_values=self._string_tuple(raw.get("core_values")),
                    personality_traits=self._string_tuple(raw.get("personality_traits")),
                    conversation_style=str(raw.get("conversation_style", "")).strip(),
                    reflection_boundaries=self._string_tuple(raw.get("reflection_boundaries")),
                )
            )
        return tuple(
            sorted(profiles, key=lambda item: (item.sort_order, item.display_name.casefold()))
        )

    def load_documents(
        self, data_dir: Path, profile: CharacterProfile
    ) -> tuple[KnowledgeDocument, ...]:
        return tuple(
            self._load_document(path, profile.id)
            for path in sorted((data_dir / profile.id).glob("*.md"))
        )

    def _load_document(self, path: Path, character_id: str) -> KnowledgeDocument:
        raw = path.read_text(encoding="utf-8")
        metadata, body = self._split_frontmatter(raw)
        document_id = str(metadata.get("id") or f"{character_id}_{path.stem}")
        evidence_scope = str(metadata.get("evidence_scope", "character")).strip().lower()
        if evidence_scope not in {"character", "contextual"}:
            raise ValueError(f"Unsupported evidence_scope={evidence_scope!r} in {path}")
        title_match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ").title()
        chunks = tuple(
            KnowledgeChunk(
                id=f"{document_id}_chunk_{index:03d}",
                content=content,
                metadata={
                    "tags": list(metadata.get("tags") or []),
                    "entities": list(metadata.get("entities") or []),
                    "confidence": metadata.get("confidence"),
                },
            )
            for index, content in enumerate(self._chunk(body), 1)
        )
        return KnowledgeDocument(
            id=document_id,
            character_id=character_id,
            title=title,
            source_name=self._optional(metadata.get("source_name")),
            source_url=self._optional(metadata.get("source_url")),
            source_type=self._optional(metadata.get("source_type")),
            confidence=self._optional(metadata.get("confidence")),
            evidence_scope=evidence_scope,
            checksum=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            chunks=chunks,
        )

    @staticmethod
    def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
        if not raw.startswith("---"):
            return {}, raw
        parts = raw.split("---", 2)
        return (yaml.safe_load(parts[1]) or {}, parts[2].strip()) if len(parts) == 3 else ({}, raw)

    @staticmethod
    def _chunk(body: str, max_chars: int = 2800, overlap_chars: int = 320) -> list[str]:
        sections = [
            item.strip()
            for item in re.split(r"(?=^##\s+)", body, flags=re.MULTILINE)
            if item.strip()
        ]
        chunks: list[str] = []
        for section in sections:
            paragraphs = [item.strip() for item in section.split("\n\n") if item.strip()]
            current = ""
            for paragraph in paragraphs:
                candidate = f"{current}\n\n{paragraph}".strip()
                if current and len(candidate) > max_chars:
                    chunks.append(current)
                    overlap = current[-overlap_chars:].lstrip()
                    current = f"{overlap}\n\n{paragraph}".strip()
                else:
                    current = candidate
            if current:
                chunks.append(current)
        return chunks

    @staticmethod
    def _optional(value: object) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())
