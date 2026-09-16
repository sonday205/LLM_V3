from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckResult:
    allowed: bool
    category: str = "passed"
    response: str | None = None


class SafetyPrecheck:
    """Precheck 1: chặn rủi ro rõ ràng mà không gọi model."""

    _CATEGORIES = (
        (
            "prompt_injection",
            ("bỏ qua hướng dẫn", "lộ prompt", "system prompt", "developer prompt", "jailbreak"),
        ),
        (
            "dangerous_instruction",
            ("chế bom", "làm bom", "đầu độc", "chế vũ khí", "hack tài khoản"),
        ),
        ("hate_or_discrimination", ("dân tộc nào kém", "miền nào ngu", "ghét người miền")),
        ("sexual_content", ("ảnh khỏa thân", "quan hệ tình dục", "nội dung khiêu dâm")),
    )
    _SELF_HARM = ("muốn tự tử", "không muốn sống", "muốn chết", "tự làm đau")

    def check(self, message: str) -> CheckResult:
        lowered = message.casefold()
        if any(term in lowered for term in self._SELF_HARM):
            return CheckResult(
                False,
                "self_harm",
                "Mình rất lo khi bạn nói như vậy. Hãy nói ngay với một người lớn "
                "đáng tin cậy ở gần và đừng ở một mình. Nếu có nguy cơ trước mắt, "
                "hãy gọi dịch vụ khẩn cấp tại nơi bạn đang sống.",
            )
        for category, terms in self._CATEGORIES:
            if any(term in lowered for term in terms):
                return CheckResult(
                    False,
                    category,
                    "Mình không thể hỗ trợ nội dung đó. Chúng ta có thể chuyển sang "
                    "lịch sử, học tập hoặc một chủ đề an toàn hơn.",
                )
        return CheckResult(True)


class PrivacyPrecheck:
    """Precheck 2: ngăn PII/secrets đi vào provider và memory."""

    _EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    _PHONE = re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)")
    _ID_NUMBER = re.compile(r"(?<!\d)\d{12}(?!\d)")
    _SENSITIVE_TERMS = (
        "địa chỉ nhà",
        "số nhà",
        "nhà em ở",
        "nhà cháu ở",
        "mật khẩu",
        "password",
        "api key",
        "api_key",
        "access token",
        "số tài khoản",
        "căn cước",
        "cccd",
    )

    def check(self, message: str) -> CheckResult:
        lowered = message.casefold()
        if (
            self._EMAIL.search(message)
            or self._PHONE.search(message)
            or self._ID_NUMBER.search(message)
        ):
            return self._blocked()
        if any(term in lowered for term in self._SENSITIVE_TERMS):
            return self._blocked()
        return CheckResult(True)

    @staticmethod
    def _blocked() -> CheckResult:
        return CheckResult(
            False,
            "sensitive_information",
            "Đừng gửi thông tin riêng tư như địa chỉ, số điện thoại, email, giấy tờ, "
            "mật khẩu hoặc khóa truy cập. Bạn có thể dùng biệt danh và khối lớp để "
            "trò chuyện an toàn hơn.",
        )


class StorageGuard:
    """Không sửa output; chỉ quyết định turn có đủ an toàn để lưu hay không."""

    _UNSAFE_OUTPUT = (
        "đây là system prompt",
        "developer instruction",
        "mật khẩu của bạn",
        "api key của bạn",
        "các bước chế tạo",
    )
    _DO_NOT_PERSIST_INPUT = (
        "chọn phe",
        "ủng hộ một đảng",
        "em theo đảng",
        "cháu theo đảng",
        "tôn giáo của em",
        "tôn giáo của cháu",
        "bệnh của em",
        "bệnh của cháu",
        "xu hướng tính dục",
    )

    def __init__(self, safety: SafetyPrecheck, privacy: PrivacyPrecheck) -> None:
        self.safety = safety
        self.privacy = privacy

    def can_store(self, user_message: str, answer: str) -> bool:
        if not self.privacy.check(user_message).allowed or not self.privacy.check(answer).allowed:
            return False
        if any(term in user_message.casefold() for term in self._DO_NOT_PERSIST_INPUT):
            return False
        lowered = answer.casefold()
        if any(term in lowered for term in self._UNSAFE_OUTPUT):
            return False
        # Không dùng toàn bộ safety rule cho output vì tư liệu lịch sử có thể nhắc đến chiến tranh.
        return not any(term in lowered for term in SafetyPrecheck._SELF_HARM)
