from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.database import Database
from app.embeddings import build_embedding_provider
from app.knowledge import KnowledgeLoader


async def ingest(character_id: str | None = None, missing_only: bool = False) -> None:
    settings = get_settings()
    loader = KnowledgeLoader()
    database = Database(settings.database_url)
    totals = {"characters": 0, "documents": 0, "chunks": 0}
    try:
        existing_ids = (
            {row["id"] for row in await database.list_characters()} if missing_only else set()
        )
        profiles = [
            profile
            for profile in loader.load_profiles(settings.data_dir)
            if (not character_id or profile.id == character_id) and profile.id not in existing_ids
        ]
        if not profiles:
            print("No characters to ingest.")
            return
        provider = build_embedding_provider(
            settings.embedding_provider,
            settings.embedding_model,
            settings.embedding_device,
        )
        for profile in profiles:
            documents = loader.load_documents(settings.data_dir, profile)
            chunks = [chunk for document in documents for chunk in document.chunks]
            vectors = await asyncio.to_thread(provider.encode, [chunk.content for chunk in chunks])
            embeddings = {chunk.id: vector for chunk, vector in zip(chunks, vectors, strict=True)}
            document_count, chunk_count = await database.ingest_character(
                profile, documents, embeddings
            )
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
    parser.add_argument(
        "--missing-only", action="store_true", help="Skip characters already present in database."
    )
    args = parser.parse_args()
    asyncio.run(ingest(args.character_id, args.missing_only))


if __name__ == "__main__":
    main()
