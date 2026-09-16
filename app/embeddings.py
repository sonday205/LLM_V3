from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

EMBEDDING_DIMENSION = 1024


class EmbeddingProvider(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Embedding nhẹ, xác định được để test/offline; không dùng làm mặc định production."""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    @staticmethod
    def _encode_one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        tokens = re.findall(r"[\wÀ-ỹĐđ]+", text.casefold(), flags=re.UNICODE)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class BGEM3EmbeddingProvider:
    def __init__(self, model_name: str, device: str = "auto") -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self._device = "cuda" if device == "auto" and torch.cuda.is_available() else device
        if self._device == "auto":
            self._device = "cpu"
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        # BGE-M3 dùng CLS pooling rồi L2-normalize. Dùng trực tiếp transformers
        # giúp chỉ tải một định dạng trọng số thay vì hai bản giống nhau.
        self._model = AutoModel.from_pretrained(model_name, use_safetensors=True)
        self._model.to(self._device)
        self._model.eval()

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), 16):
            batch = list(texts[offset : offset + 16])
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {name: value.to(self._device) for name, value in encoded.items()}
            with self._torch.inference_mode():
                outputs = self._model(**encoded)
                dense = outputs.last_hidden_state[:, 0]
                dense = self._torch.nn.functional.normalize(dense, p=2, dim=1)
            vectors.extend(dense.cpu().tolist())
        return vectors


def build_embedding_provider(provider: str, model_name: str, device: str) -> EmbeddingProvider:
    if provider == "hash":
        return HashEmbeddingProvider()
    if provider == "bge_m3":
        return BGEM3EmbeddingProvider(model_name, device)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


def vector_literal(vector: Sequence[float]) -> str:
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError(f"Expected {EMBEDDING_DIMENSION} dimensions, got {len(vector)}")
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
