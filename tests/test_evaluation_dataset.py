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
