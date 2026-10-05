from pathlib import Path

import yaml

from app.domain import MemoryContext, RetrievalResult, RetrievedChunk
from app.knowledge import KnowledgeLoader
from app.prompt import PROMPT_PATH, PromptBuilder

ROOT = Path(__file__).resolve().parents[1]


def test_every_character_has_data_driven_persona() -> None:
    profiles = KnowledgeLoader().load_profiles(ROOT / "data" / "characters")
    assert len(profiles) == 47
    for profile in profiles:
        assert profile.core_values
        assert profile.personality_traits
        assert profile.conversation_style
        assert profile.reflection_boundaries


def test_shared_prompt_contains_no_character_name_or_id() -> None:
    template = PROMPT_PATH.read_text(encoding="utf-8").casefold()
    profiles = KnowledgeLoader().load_profiles(ROOT / "data" / "characters")
    for profile in profiles:
        assert profile.id.casefold() not in template
        assert profile.display_name.casefold() not in template


def test_prompt_includes_persona_and_generic_answer_modes() -> None:
    profile = KnowledgeLoader().load_profiles(ROOT / "data" / "characters")[0]
    prompt = PromptBuilder().build(
        profile,
        "Nhân vật có nhớ gia đình không?",
        MemoryContext(),
        RetrievalResult(status="not_found"),
    )
    assert profile.core_values[0] in prompt
    assert "SUY NGẪM CÓ GIỚI HẠN" in prompt
    assert "BỐI CẢNH THỜI ĐẠI" in prompt
    assert "không in tên kiểu ra ngoài" in prompt


def test_contextual_evidence_is_explicitly_bounded() -> None:
    result = RetrievalResult(
        status="grounded",
        chunks=(
            RetrievedChunk(
                id="context-1",
                document_id="doc-1",
                content="Bộ đội được bảo đảm lương thực từ hậu phương.",
                title="Bối cảnh hậu cần",
                source_name="Nguồn thử nghiệm",
                source_url=None,
                score=1.0,
                evidence_scope="contextual",
            ),
        ),
    )
    context = result.prompt_context()
    assert "BỐI CẢNH CHUNG" in context
    assert "không dùng để khẳng định sở thích" in context


def test_persona_reflection_evaluation_has_20_cases_and_all_characters() -> None:
    path = ROOT / "evaluation" / "persona_reflection_20.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == 20
    assert len({case["character_id"] for case in cases}) == 14
    assert all(case["expected_behavior"] for case in cases)
    assert all(case["must_avoid"] for case in cases)
