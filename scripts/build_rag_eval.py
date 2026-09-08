"""Deterministically build the RAG Judge/Repair evaluation corpus.

The generator depends only on policy text and explicit scenario rules. It must
not import runtime or model code. The scorer lives in ``verifigen.rag_eval`` and
uses only the labels emitted here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "rag_qa" / "eval_cases.jsonl"
FAKE_CHUNK = "KB-FAKE-888"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "headphones",
        "category": "headphones",
        "noun": "耳机",
        "condition_after": "拆封后",
        "window_id": "KB-HEADPHONE-RETURN-7D",
        "condition_id": "KB-HEADPHONE-OPENED",
        "fee_id": "KB-HEADPHONE-FEE",
        "window_sentence": "符合退货条件的耳机，可以在收货后七天内申请退货。",
        "condition_sentence": "非质量问题下，耳机拆封后不适用七天无理由退货。",
        "condition_bad": "耳机拆封后仍可七天无理由退货。",
        "fee_sentence": "非质量问题的耳机退货运费由客户承担。",
        "fee_bad": "非质量问题的耳机退货运费由商家承担。",
        "window_pass": ["七天", "七天内", "7天", "7天内"],
        "window_days": "七天",
        "condition_pass": ["拆封后不适用", "拆封后不能", "拆封后不可", "拆封后不支持"],
        "condition_fail": ["拆封后仍可", "拆封后可以", "拆封后适用", "拆封后能退"],
        "fee_kind": "customer",
    },
    {
        "id": "laptops",
        "category": "laptops",
        "noun": "笔记本电脑",
        "condition_after": "联网激活后",
        "window_id": "KB-LAPTOP-RETURN-15D",
        "condition_id": "KB-LAPTOP-OPENED",
        "fee_id": "KB-LAPTOP-FEE",
        "window_sentence": "符合退货条件的笔记本电脑，可以在收货后十五天内申请退货。",
        "condition_sentence": "笔记本电脑联网激活后不适用无理由退货。",
        "condition_bad": "笔记本电脑联网激活后仍可无理由退货。",
        "fee_sentence": "质量问题导致的笔记本电脑退货运费由商家承担。",
        "fee_bad": "质量问题导致的笔记本电脑退货运费由客户承担。",
        "window_pass": ["十五天", "十五天内", "15天", "15天内"],
        "window_days": "十五天",
        "condition_pass": ["激活后不适用", "激活后不能", "激活后不可", "激活后不支持"],
        "condition_fail": ["激活后仍可", "激活后可以", "激活后适用", "激活后能退"],
        "fee_kind": "merchant",
    },
    {
        "id": "clothing",
        "category": "clothing",
        "noun": "服装",
        "condition_after": "试穿后",
        "window_id": "KB-CLOTHING-RETURN-30D",
        "condition_id": "KB-CLOTHING-OPENED",
        "fee_id": "KB-CLOTHING-FEE",
        "window_sentence": "符合退货条件的服装，可以在收货后三十天内申请退货。",
        "condition_sentence": "保持吊牌完整且无使用痕迹时，试穿不影响无理由退货。",
        "condition_bad": "服装无论是否保留吊牌都可以无理由退货。",
        "fee_sentence": "服装退货运费根据退货原因和会员权益确认。",
        "fee_bad": "服装退货运费一律由商家承担。",
        "window_pass": ["三十天", "三十天内", "30天", "30天内"],
        "window_days": "三十天",
        "condition_pass": ["试穿不影响", "吊牌完整", "无使用痕迹"],
        "condition_fail": ["无论是否保留吊牌", "不保留吊牌", "没有吊牌也能退", "都可以无理由退货"],
        "fee_kind": "case_by_case",
    },
    {
        "id": "speakers",
        "category": "speakers",
        "noun": "音箱",
        "condition_after": "拆封后",
        "window_id": "KB-SPEAKER-RETURN-7D",
        "condition_id": "KB-SPEAKER-OPENED",
        "fee_id": "KB-SPEAKER-FEE",
        "window_sentence": "符合退货条件的音箱，可以在收货后七天内申请退货。",
        "condition_sentence": "非质量问题下，音箱拆封后不适用七天无理由退货。",
        "condition_bad": "音箱拆封后仍可七天无理由退货。",
        "fee_sentence": "非质量问题的音箱退货运费由客户承担。",
        "fee_bad": "非质量问题的音箱退货运费由商家承担。",
        "window_pass": ["七天", "七天内", "7天", "7天内"],
        "window_days": "七天",
        "condition_pass": ["拆封后不适用", "拆封后不能", "拆封后不可", "拆封后不支持"],
        "condition_fail": ["拆封后仍可", "拆封后可以", "拆封后适用", "拆封后能退"],
        "fee_kind": "customer",
    },
    {
        "id": "tablets",
        "category": "tablets",
        "noun": "平板电脑",
        "condition_after": "联网激活后",
        "window_id": "KB-TABLET-RETURN-15D",
        "condition_id": "KB-TABLET-ACTIVATED",
        "fee_id": "KB-TABLET-FEE",
        "window_sentence": "符合退货条件的平板电脑，可以在收货后十五天内申请退货。",
        "condition_sentence": "平板电脑联网激活后不适用无理由退货。",
        "condition_bad": "平板电脑联网激活后仍可无理由退货。",
        "fee_sentence": "质量问题导致的平板电脑退货运费由商家承担。",
        "fee_bad": "质量问题导致的平板电脑退货运费由客户承担。",
        "window_pass": ["十五天", "十五天内", "15天", "15天内"],
        "window_days": "十五天",
        "condition_pass": ["激活后不适用", "激活后不能", "激活后不可", "激活后不支持"],
        "condition_fail": ["激活后仍可", "激活后可以", "激活后适用", "激活后能退"],
        "fee_kind": "merchant",
    },
    {
        "id": "shoes",
        "category": "shoes",
        "noun": "运动鞋",
        "condition_after": "试穿后",
        "window_id": "KB-SHOE-RETURN-30D",
        "condition_id": "KB-SHOE-TRYON",
        "fee_id": "KB-SHOE-FEE",
        "window_sentence": "符合退货条件的运动鞋，可以在收货后三十天内申请退货。",
        "condition_sentence": "保持鞋盒与吊牌完整且无穿着痕迹时，试穿不影响无理由退货。",
        "condition_bad": "运动鞋无论是否保留鞋盒和吊牌都可以无理由退货。",
        "fee_sentence": "运动鞋退货运费根据退货原因和会员权益确认。",
        "fee_bad": "运动鞋退货运费一律由商家承担。",
        "window_pass": ["三十天", "三十天内", "30天", "30天内"],
        "window_days": "三十天",
        "condition_pass": ["试穿不影响", "鞋盒与吊牌完整", "无穿着痕迹"],
        "condition_fail": ["无论是否保留鞋盒", "不保留鞋盒", "没有鞋盒也能退", "都可以无理由退货"],
        "fee_kind": "case_by_case",
    },
]

MUTATIONS = (
    "clean",
    "cross_category",
    "wrong_window",
    "condition_inverted",
    "wrong_fee",
    "missing_fee",
    "missing_condition",
    "no_citations",
    "fabricated_citation",
    "unsupported_promise",
)

QUESTION_TEMPLATES = (
    "{noun}在收货后多久内可以申请退货？{condition_after}还能无理由退货吗？退货运费由谁承担？",
    "想问一下{noun}的退货政策：退货期限、{condition_after}的退货资格、运费规则分别是什么？",
    "{noun}支持几天无理由退货？如果已经{condition_without}，还能退吗？运费怎么算？",
)


def _ids(product: dict[str, Any]) -> tuple[str, str, str]:
    return product["window_id"], product["condition_id"], product["fee_id"]


def _clean_answer(product: dict[str, Any]) -> tuple[str, list[str]]:
    window_id, condition_id, fee_id = _ids(product)
    parts = [
        f"{product['window_sentence']} [{window_id}]",
        f"{product['condition_sentence']} [{condition_id}]",
        f"{product['fee_sentence']} [{fee_id}]",
    ]
    return " ".join(parts), [window_id, condition_id, fee_id]


def _clean_candidate(product: dict[str, Any]) -> dict[str, Any]:
    answer, citations = _clean_answer(product)
    return {"answer": answer, "citations": citations}


def _different_window(product: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in PRODUCTS if item["window_days"] != product["window_days"])


def _different_product(product: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in PRODUCTS if item["id"] != product["id"])


def _mutated_candidate(product: dict[str, Any], mutation: str) -> dict[str, Any]:
    window_id, condition_id, fee_id = _ids(product)
    clean_answer, clean_citations = _clean_answer(product)
    if mutation == "clean":
        return _clean_candidate(product)
    if mutation == "cross_category":
        other = _different_product(product)
        return _clean_candidate(other)
    if mutation == "wrong_window":
        other = _different_window(product)
        wrong = (
            f"符合退货条件的{product['noun']}，可以在收货后{other['window_days']}天内申请退货。"
            f" [{window_id}]"
        )
        return {
            "answer": " ".join(
                [
                    wrong,
                    f"{product['condition_sentence']} [{condition_id}]",
                    f"{product['fee_sentence']} [{fee_id}]",
                ]
            ),
            "citations": clean_citations,
        }
    if mutation == "condition_inverted":
        return {
            "answer": " ".join(
                [
                    f"{product['window_sentence']} [{window_id}]",
                    f"{product['condition_bad']} [{condition_id}]",
                    f"{product['fee_sentence']} [{fee_id}]",
                ]
            ),
            "citations": clean_citations,
        }
    if mutation == "wrong_fee":
        return {
            "answer": " ".join(
                [
                    f"{product['window_sentence']} [{window_id}]",
                    f"{product['condition_sentence']} [{condition_id}]",
                    f"{product['fee_bad']} [{fee_id}]",
                ]
            ),
            "citations": clean_citations,
        }
    if mutation == "missing_fee":
        text = " ".join(
            [
                f"{product['window_sentence']} [{window_id}]",
                f"{product['condition_sentence']} [{condition_id}]",
            ]
        )
        return {"answer": text, "citations": [window_id, condition_id]}
    if mutation == "missing_condition":
        text = " ".join(
            [
                f"{product['window_sentence']} [{window_id}]",
                f"{product['fee_sentence']} [{fee_id}]",
            ]
        )
        return {"answer": text, "citations": [window_id, fee_id]}
    if mutation == "no_citations":
        text = clean_answer.replace(" [", "").replace("]", "")
        return {"answer": text, "citations": []}
    if mutation == "fabricated_citation":
        return {
            "answer": clean_answer + f"补充依据见 [{FAKE_CHUNK}]。",
            "citations": [*clean_citations, FAKE_CHUNK],
        }
    if mutation == "unsupported_promise":
        return {
            "answer": clean_answer + "我们会立即为您办理退款并赠送优惠券，预计24小时内到账。",
            "citations": clean_citations,
        }
    raise ValueError(f"Unknown mutation: {mutation}")


def _required_claims(product: dict[str, Any]) -> list[dict[str, Any]]:
    own_window_pass = set(product["window_pass"])
    other_windows = [
        term
        for item in PRODUCTS
        if item["id"] != product["id"]
        for term in item["window_pass"]
        if term not in own_window_pass
    ]
    window_fail = list(dict.fromkeys(other_windows))
    if product["fee_kind"] == "customer":
        fee_pass = ["客户承担", "消费者承担", "买家承担", "用户承担"]
        fee_fail = ["商家承担", "卖家承担"]
    elif product["fee_kind"] == "merchant":
        fee_pass = ["商家承担", "卖家承担"]
        fee_fail = ["客户承担", "消费者承担", "买家承担", "用户承担"]
    else:
        fee_pass = ["退货原因", "会员权益", "根据实际情况", "具体情况"]
        fee_fail = ["一律由商家", "固定由商家", "一律由客户", "固定由客户"]
    window_id, condition_id, fee_id = _ids(product)
    condition_groups = {
        "headphones": [["拆封", "不适用"]],
        "speakers": [["拆封", "不适用"]],
        "laptops": [["激活", "不适用"]],
        "tablets": [["激活", "不适用"]],
        "clothing": [["试穿", "不影响"], ["吊牌完整", "无使用痕迹"]],
        "shoes": [["试穿", "不影响"], ["鞋盒", "吊牌完整", "无穿着痕迹"]],
    }
    return [
        {
            "label": "window",
            "chunk_id": window_id,
            "pass_terms": product["window_pass"],
            "fail_terms": window_fail,
        },
        {
            "label": "condition",
            "chunk_id": condition_id,
            "pass_terms": product["condition_pass"],
            "pass_all_terms": condition_groups[product["id"]],
            "fail_terms": product["condition_fail"],
        },
        {
            "label": "fee",
            "chunk_id": fee_id,
            "pass_terms": fee_pass,
            "fail_terms": fee_fail,
        },
    ]


def _forbidden_chunks(product: dict[str, Any]) -> list[str]:
    own = set(_ids(product))
    all_ids = {chunk_id for item in PRODUCTS for chunk_id in _ids(item)}
    return sorted(all_ids - own) + [FAKE_CHUNK]


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for product in PRODUCTS:
        for mutation_index, mutation in enumerate(MUTATIONS):
            template = QUESTION_TEMPLATES[mutation_index % len(QUESTION_TEMPLATES)]
            condition_after = product["condition_after"]
            condition_without = condition_after[:-1]
            question = template.format(
                noun=product["noun"],
                condition_after=condition_after,
                condition_without=condition_without,
            )
            forbidden_phrases = (
                ["立即为您办理退款", "24小时内到账", "赠送优惠券"]
                if mutation == "unsupported_promise"
                else []
            )
            cases.append(
                {
                    "id": f"{product['id']}--{mutation}",
                    "category": product["category"],
                    "question": question,
                    "initial": _mutated_candidate(product, mutation),
                    "initial_should_pass": mutation == "clean",
                    "required_claims": _required_claims(product),
                    "forbidden_chunks": _forbidden_chunks(product),
                    "forbidden_phrases": forbidden_phrases,
                }
            )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the RAG Judge/Repair evaluation cases")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    cases = build_cases()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases),
        encoding="utf-8",
    )
    print(
        f"wrote {len(cases)} cases to {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}"
    )


if __name__ == "__main__":
    main()
