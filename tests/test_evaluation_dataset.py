from pathlib import Path

import yaml


def test_evaluation_dataset_has_50_unique_cases_and_all_characters() -> None:
    path = Path(__file__).resolve().parents[1] / "evaluation" / "quality_50.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    factual_characters = {case["character_id"] for case in cases if case["category"] == "factual"}
    assert len(factual_characters) == 14
    assert sum(case["category"] == "memory" for case in cases) == 8


def test_safety_redteam_dataset_has_24_unique_cases() -> None:
    path = Path(__file__).resolve().parents[1] / "evaluation" / "safety_redteam_24.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]

    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24
    assert all(case["character_id"] for case in cases)
    assert all("expected_calls" in case for case in cases)
    assert {case["category"] for case in cases} >= {
        "secret",
        "injection",
        "dangerous",
        "violence",
        "politics",
        "privacy",
        "child_safety",
    }
