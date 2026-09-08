.PHONY: demo test quality benchmark build

demo:
	python -m verifigen.cli demo

test:
	python -m pytest -q

quality:
	ruff check .
	ruff format --check .
	mypy
	python -m pytest --cov=verifigen --cov-fail-under=85

benchmark:
	python -m verifigen.cli benchmark --dataset benchmarks/data/test.jsonl --output runs/offline-test

build:
	python -m build
