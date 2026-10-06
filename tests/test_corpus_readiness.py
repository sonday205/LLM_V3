from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database import Database


@pytest.mark.parametrize(
    ("rows", "expected", "ready"),
    [
        ([], [], False),
        ([{"id": "a", "chunk_count": 1}], ["a", "b"], False),
        ([{"id": "a", "chunk_count": 1}, {"id": "b", "chunk_count": 0}], ["a", "b"], False),
        ([{"id": "a", "chunk_count": 1}, {"id": "b", "chunk_count": 2}], ["a", "b"], True),
        ([{"id": "wrong", "chunk_count": 1}], ["a"], False),
    ],
)
async def test_readiness_requires_expected_ids_and_chunks(rows, expected, ready):
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    connection = SimpleNamespace(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def connect():
        yield connection

    database = object.__new__(Database)
    database.engine = SimpleNamespace(connect=connect)
    database.expected_character_ids = frozenset(expected)
    assert await database.ready() is ready


async def test_missing_only_preserves_existing_characters(monkeypatch):
    import scripts.ingest as module

    profiles = [SimpleNamespace(id="existing"), SimpleNamespace(id="new")]
    documents = [SimpleNamespace(chunks=[SimpleNamespace(id="chunk", content="history")])]
    database = SimpleNamespace(
        list_characters=AsyncMock(return_value=[{"id": "existing"}]),
        ingest_character=AsyncMock(return_value=(1, 1)),
        close=AsyncMock(),
    )
    loader = SimpleNamespace(
        load_profiles=lambda _: profiles,
        load_documents=lambda *_: documents,
    )
    monkeypatch.setattr(module, "Database", lambda _: database)
    monkeypatch.setattr(module, "KnowledgeLoader", lambda: loader)
    monkeypatch.setattr(
        module, "build_embedding_provider", lambda *_: SimpleNamespace(encode=lambda _: [[0.0]])
    )
    await module.ingest(missing_only=True)
    database.ingest_character.assert_awaited_once()
    assert database.ingest_character.call_args.args[0].id == "new"
    database.close.assert_awaited_once()
