from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.database import Database
from app.embeddings import build_embedding_provider
from app.knowledge import KnowledgeLoader


async def ingest(character_id: str | None = None) -> None:
    settings = get_settings()
    loader = KnowledgeLoader()
    provider = build_embedding_provider(
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_device,
    )
    database = Database(settings.database_url)
    totals = {"characters": 0, "documents": 0, "chunks": 0}
    try:
        for profile in loader.load_profiles(settings.data_dir):
            if character_id and profile.id != character_id:
                continue
            documents = loader.load_documents(settings.data_dir, profile)
            chunks = [chunk for document in documents for chunk in document.chunks]
            vectors = await asyncio.to_thread(provider.encode, [chunk.content for chunk in chunks])
            embeddings = {chunk.id: vector for chunk, vector in zip(chunks, vectors, strict=True)}
            document_count, chunk_count = await database.ingest_character(profile, documents, embeddings)
            totals["characters"] += 1
            totals["documents"] += document_count
            totals["chunks"] += chunk_count
            print(f"{profile.id}: {document_count} documents, {chunk_count} chunks")
    finally:
        await database.close()
    print(
        f"Ingested {totals['characters']} characters, {totals['documents']} documents, "
        f"{totals['chunks']} chunks"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--character-id")
    args = parser.parse_args()
    asyncio.run(ingest(args.character_id))


if __name__ == "__main__":
    main()
