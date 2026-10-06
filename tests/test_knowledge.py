from pathlib import Path

from app.embeddings import EMBEDDING_DIMENSION, HashEmbeddingProvider
from app.knowledge import KnowledgeLoader
from app.retrieval import RetrievalPolicy

ROOT = Path(__file__).resolve().parents[1]


def test_corpus_has_all_48_characters_and_sources() -> None:
    loader = KnowledgeLoader()
    profiles = loader.load_profiles(ROOT / "data" / "characters")
    assert len(profiles) == 48
    assert [profile.sort_order for profile in profiles] == list(range(1, 49))
    for profile in profiles:
        documents = loader.load_documents(ROOT / "data" / "characters", profile)
        assert documents
        assert all(document.chunks for document in documents)
        assert any(document.source_name for document in documents)


def test_hash_embedding_is_stable_and_1024_dimensions() -> None:
    provider = HashEmbeddingProvider()
    first, second = provider.encode(["Ngô Quyền", "Ngô Quyền"])
    assert len(first) == EMBEDDING_DIMENSION
    assert first == second


def test_chunks_overlap_only_when_section_is_large() -> None:
    body = "# Tiêu đề\n\n## Mục\n\n" + "A" * 3000 + "\n\n" + "B" * 100
    chunks = KnowledgeLoader._chunk(body, max_chars=1000, overlap_chars=100)
    assert len(chunks) >= 2


def test_retrieval_policy_keeps_memory_questions_out_of_history_rag() -> None:
    assert not RetrievalPolicy.should_retrieve_history("Anh nhớ tên gọi của em không?")
    assert not RetrievalPolicy.should_retrieve_history("Tóm tắt cuộc trò chuyện của mình.")
    assert not RetrievalPolicy.should_retrieve_history("Cháu học lớp 5 và thích lịch sử.")
    assert RetrievalPolicy.should_retrieve_history("Chiến thuật Bạch Đằng năm 938 là gì?")


def test_requested_characters_use_catalog_order() -> None:
    loader = KnowledgeLoader()
    profiles = loader.load_profiles(ROOT / "data" / "characters")
    assert [profile.id for profile in profiles if 15 <= profile.sort_order <= 19] == [
        "pham_ngoc_thao",
        "vu_ngoc_nha",
        "dang_tran_duc",
        "pham_xuan_an",
        "le_duc_thuy",
    ]
    profile = next(profile for profile in profiles if profile.id == "le_huu_thuy")
    documents = loader.load_documents(ROOT / "data" / "characters", profile)
    identity = next(
        document for document in documents if document.id.endswith("identity_and_sources")
    )
    assert identity.source_url
    assert "Đại tá" in "\n".join(chunk.content for chunk in identity.chunks)
