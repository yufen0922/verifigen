"""Extend a contract with a non-repairable business rule."""

import asyncio
from dataclasses import replace

from verifigen import Harness, RuleVerifier
from verifigen.domains.report import make_report_contract


async def main():
    base = make_report_contract()
    # Simulated data-quality rule: manual review for an unexpectedly large jump.
    rule = RuleVerifier(
        "growth_needs_review",
        lambda draft, ctx: draft["delta"] <= 1000,
        target="/delta",
        message="Large count changes need a data-quality review",
    )
    contract = replace(base, verifiers=(*base.verifiers, rule))
    candidate = {
        "current": 3000,
        "previous": 100,
        "delta": 2900,
        "direction": "up",
        "sentence": "本期订单3000笔，上期100笔，增加2900笔。",
    }
    result = await Harness(contract).run(
        source={"current": 3000, "previous": 100}, initial=candidate
    )
    print(result.status, result.reason, result.text)
    assert result.status == "fallback"  # Do not silently clip a business value.


if __name__ == "__main__":
    asyncio.run(main())
