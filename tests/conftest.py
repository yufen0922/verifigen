from datetime import datetime
from pathlib import Path

import pytest

from verifigen.benchmark import load_cases
from verifigen.types import Context

ROOT = Path(__file__).resolve().parents[1]
CASES = load_cases(ROOT / "benchmarks/data/dev.jsonl") + load_cases(
    ROOT / "benchmarks/data/test.jsonl"
)


@pytest.fixture(params=CASES, ids=lambda case: case["id"])
def case(request):
    return request.param


@pytest.fixture
def context_for():
    return lambda case: Context.create(
        case["source"], datetime.fromisoformat(case["evaluation_time"])
    )
