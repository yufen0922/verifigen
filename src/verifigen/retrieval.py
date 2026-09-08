"""Small dependency-free BM25 retriever for local, inspectable RAG examples."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .jsonutil import json_copy

_TOKEN = re.compile(r"[a-zA-Z0-9_]+|[\u3400-\u9fff]")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize Latin words plus Chinese characters and adjacent bigrams."""
    raw = [token.lower() for token in _TOKEN.findall(text)]
    chinese = [token for token in raw if len(token) == 1 and "\u3400" <= token <= "\u9fff"]
    bigrams = [left + right for left, right in zip(chinese, chinese[1:], strict=False)]
    return tuple((*raw, *bigrams))


@dataclass(frozen=True)
class SearchHit:
    document: dict[str, Any]
    score: float


class BM25Retriever:
    """In-memory BM25 with optional exact-match metadata filtering."""

    def __init__(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        text_fields: tuple[str, ...] = ("title", "text"),
        id_field: str = "chunk_id",
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not documents or not text_fields or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Documents, text fields and valid BM25 parameters are required")
        self.documents = tuple(json_copy(document) for document in documents)
        if any(not isinstance(document, dict) for document in self.documents):
            raise TypeError("Retriever documents must be JSON objects")
        ids = [document.get(id_field) for document in self.documents]
        if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(
            set(ids)
        ):
            raise ValueError("Retriever documents need unique non-empty IDs")
        self.text_fields = text_fields
        self.id_field = id_field
        self.k1 = k1
        self.b = b
        self.tokens = tuple(
            tokenize(" ".join(str(document.get(field, "")) for field in text_fields))
            for document in self.documents
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[SearchHit, ...]:
        if not query.strip() or top_k <= 0:
            raise ValueError("A non-empty query and positive top_k are required")
        selected = [
            index
            for index, document in enumerate(self.documents)
            if all(document.get(key) == value for key, value in (filters or {}).items())
        ]
        if not selected:
            return ()
        query_terms = set(tokenize(query))
        lengths = [len(self.tokens[index]) for index in selected]
        average_length = sum(lengths) / len(lengths) or 1
        frequencies = {index: Counter(self.tokens[index]) for index in selected}
        scored: list[SearchHit] = []
        for index in selected:
            score = 0.0
            for term in query_terms:
                document_frequency = sum(term in frequencies[item] for item in selected)
                if not document_frequency:
                    continue
                frequency = frequencies[index][term]
                if not frequency:
                    continue
                inverse_frequency = math.log(
                    1 + (len(selected) - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                normalizer = frequency + self.k1 * (
                    1 - self.b + self.b * len(self.tokens[index]) / average_length
                )
                score += inverse_frequency * frequency * (self.k1 + 1) / normalizer
            if score > 0:
                scored.append(SearchHit(json_copy(self.documents[index]), round(score, 6)))
        scored.sort(key=lambda hit: (-hit.score, hit.document[self.id_field]))
        return tuple(scored[:top_k])
