from __future__ import annotations

import re
import unicodedata


def normalize_transcript(text: str) -> str:
    """Chuẩn hóa Unicode và khoảng trắng, không hard-code tên nhân vật."""

    normalized = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", normalized).strip()
