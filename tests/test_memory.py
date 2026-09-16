from app.memory import SafeMemoryService


def test_extracts_only_allowlisted_safe_facts() -> None:
    facts = SafeMemoryService._extract_safe_facts(
        "Em tên là Sơn và học lớp 3A. Em thích lập trình."
    )
    assert facts == {"nickname": "Sơn", "grade": "lớp 3", "learning_interest": "lập trình"}


def test_does_not_store_long_full_name_as_nickname() -> None:
    facts = SafeMemoryService._extract_safe_facts("Em tên là Nguyễn Huy Minh Anh và học lớp 5")
    assert "nickname" not in facts
    assert facts["grade"] == "lớp 5"
