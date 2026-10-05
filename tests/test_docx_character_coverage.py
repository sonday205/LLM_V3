from pathlib import Path

import pytest
import yaml

from app.knowledge import KnowledgeLoader

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "characters"
MANIFEST = yaml.safe_load((ROOT / "data" / "docx_character_manifest.yaml").read_text())


def test_catalog_covers_docx_without_duplicate_or_missing_identity() -> None:
    profiles = KnowledgeLoader().load_profiles(DATA)
    ids = [profile.id for profile in profiles]
    required = MANIFEST["required_character_ids"]
    assert len(required) == len(set(required)) == 44
    assert len(ids) == len(set(ids)) == 47
    assert set(ids) == set(required) | set(MANIFEST["existing_outside_document"])
    assert "quang_trung" not in ids
    assert "le_duc_thuy" not in ids
    assert next(p for p in profiles if p.id == "le_huu_thuy").display_name == "Lê Hữu Thúy"


def test_corpus_document_and_chunk_ids_are_globally_unique() -> None:
    loader = KnowledgeLoader()
    documents = [d for p in loader.load_profiles(DATA) for d in loader.load_documents(DATA, p)]
    assert len({d.id for d in documents}) == len(documents)
    chunks = [c for d in documents for c in d.chunks]
    assert len({c.id for c in chunks}) == len(chunks)
    new_profiles = [p for p in loader.load_profiles(DATA) if p.sort_order > 14]
    assert len(new_profiles) == 33
    for profile in new_profiles:
        evidence = loader.load_documents(DATA, profile)
        assert all(d.source_url and d.source_name and d.confidence for d in evidence)
        assert all(d.character_id == profile.id and d.chunks for d in evidence)


@pytest.mark.parametrize(
    "character_id,marker",
    [
        ("hung_vuong", "không phải tên riêng"),
        ("hai_ba_trung", "Trưng Trắc và Trưng Nhị"),
        ("an_duong_vuong", "truyền thuyết"),
        ("an_tu", "không khẳng định"),
        ("doan_thi_diem", "Phan Huy Ích"),
        ("le_huu_thuy", "Nhị Hồ"),
    ],
)
def test_uncertainty_and_identity_are_preserved_in_retrievable_data(
    character_id: str, marker: str
) -> None:
    loader = KnowledgeLoader()
    profile = next(p for p in loader.load_profiles(DATA) if p.id == character_id)
    content = "\n".join(c.content for d in loader.load_documents(DATA, profile) for c in d.chunks)
    assert marker in content


def test_new_character_evaluation_fixtures_cover_all_added_profiles() -> None:
    cases = yaml.safe_load((ROOT / "evaluation" / "docx_expansion_165.yaml").read_text())["cases"]
    new_ids = {p.id for p in KnowledgeLoader().load_profiles(DATA) if p.sort_order > 14}
    assert len(cases) == len({c["id"] for c in cases}) == 165
    assert {c["character_id"] for c in cases} == new_ids
    assert all(c["message"] and c["expected_behavior"] for c in cases)
