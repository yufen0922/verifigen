# Contributing

Start with a reproducible model failure, a source snapshot, explicit review
criteria and the intended business meaning. Use synthetic or properly anonymized data. Do not commit credentials,
employer documents, real orders or raw production traces.

## Setup and checks

```bash
python -m pip install uv==0.11.33
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev mypy
uv run --locked --extra dev pytest --cov=verifigen --cov-fail-under=85
```

The equivalent editable setup is `python -m pip install -e ".[dev]"`; use the uv
lock for reproducible dependency versions. Format with `ruff format .`.

## Pull requests

Explain the faulty behavior, why it matters, the changed behavior and the
verification performed. Keep a behavioral regression test for reliability
changes. If review criteria or prompts change, update examples, independent
labels and evaluation notes together.

Do not edit gold labels merely to make a failing implementation pass. Keep
fixture generation and final scoring independent of production verifiers.
Do not claim LLM performance improvements from injected deterministic errors.

New domains belong under `domains/` or in the integrating application, not as
business conditions inside the generic runtime. Judge and Repair must receive
the complete task context. Custom agents must preserve `unknown`, support
cancellation for async work, and avoid hidden billable retries.

## Dependency updates

Change `pyproject.toml` deliberately, regenerate `uv.lock` against public PyPI,
and run the checks. Document any minimum-Python change. The initial CI matrix
covers 3.11–3.13; local verification alone is not a matrix result.
