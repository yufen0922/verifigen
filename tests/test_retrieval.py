import json
from pathlib import Path

import pytest

from verifigen.retrieval import BM25Retriever, tokenize

ROOT = Path(__file__).resolve().parents[1]


def policy_documents():
    return [
        json.loads(line)
        for line in (ROOT / "examples/rag_qa/policies.jsonl").read_text().splitlines()
    ]


def test_bm25_retrieves_all_headphone_policy_claims_ahead_of_other_categories():
    hits = BM25Retriever(policy_documents()).search(
        "耳机拆封后能否七天无理由退货，退货运费由谁承担？",
        top_k=3,
        filters={"product_category": "headphones"},
    )
    assert len(hits) == 3
    assert {hit.document["chunk_id"] for hit in hits} == {
        "KB-HEADPHONE-RETURN-7D",
        "KB-HEADPHONE-OPENED",
        "KB-HEADPHONE-FEE",
    }
    assert all("fact" not in hit.document and "value" not in hit.document for hit in hits)
    assert all(hit.document["product_category"] == "headphones" for hit in hits)
    assert all(hit.score > 0 for hit in hits)


def test_bm25_filter_without_matches_returns_no_evidence():
    hits = BM25Retriever(policy_documents()).search(
        "退货政策",
        filters={"product_category": "not-in-corpus"},
    )
    assert hits == ()


def test_retriever_rejects_duplicate_ids_and_bad_query_limits():
    documents = policy_documents()
    with pytest.raises(ValueError, match="unique"):
        BM25Retriever([documents[0], documents[0]])
    retriever = BM25Retriever(documents)
    with pytest.raises(ValueError, match="non-empty"):
        retriever.search("", top_k=0)


def test_tokenizer_supports_chinese_bigrams_and_latin_words():
    tokens = tokenize("Qwen3 耳机退货")
    assert "qwen3" in tokens and "耳机" in tokens and "退货" in tokens
