from __future__ import annotations

from pathlib import Path

from app.domain import CharacterProfile, MemoryContext, RetrievalResult

PROMPT_PATH = Path(__file__).parent / "prompts" / "answer.md"


class PromptBuilder:
    def __init__(self, template_path: Path = PROMPT_PATH) -> None:
        self.template = template_path.read_text(encoding="utf-8")

    def build(
        self,
        profile: CharacterProfile,
        message: str,
        memory: MemoryContext,
        retrieval: RetrievalResult,
    ) -> str:
        description = profile.short_description.removeprefix("Một nhân vật AI giáo dục ")
        return self.template.format(
            display_name=profile.display_name,
            self_pronoun=profile.self_pronoun,
            student_pronoun=profile.student_pronoun,
            audience=profile.audience,
            tone=profile.tone,
            short_description=description,
            persona=profile.persona_prompt_text(),
            memory=memory.as_prompt_text(),
            context=retrieval.prompt_context(),
            message=message,
        )
