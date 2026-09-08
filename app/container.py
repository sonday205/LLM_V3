from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.database import Database
from app.embeddings import build_embedding_provider
from app.llm import build_gateway
from app.memory import SafeMemoryService
from app.prompt import PromptBuilder
from app.retrieval import HybridRetriever
from app.safety import PrivacyPrecheck, SafetyPrecheck, StorageGuard
from app.service import ChatService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    database: Database
    gateway: object
    chat_service: ChatService

    async def close(self) -> None:
        await self.gateway.close()
        await self.database.close()


def build_container(settings: Settings) -> AppContainer:
    database = Database(settings.database_url)
    embeddings = build_embedding_provider(
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_device,
    )
    gateway = build_gateway(settings)
    retriever = HybridRetriever(database, embeddings, settings.retrieval_limit)
    memory = SafeMemoryService(
        database,
        embeddings,
        settings.memory_ttl_seconds,
        settings.memory_recent_turns,
        settings.memory_relevant_turns,
    )
    safety = SafetyPrecheck()
    privacy = PrivacyPrecheck()
    guard = StorageGuard(safety, privacy)
    service = ChatService(
        settings,
        database,
        retriever,
        memory,
        PromptBuilder(),
        gateway,
        safety,
        privacy,
        guard,
    )
    return AppContainer(settings, database, gateway, service)
