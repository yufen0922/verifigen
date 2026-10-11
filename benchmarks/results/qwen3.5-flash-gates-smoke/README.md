# Live Gates Smoke Test

Run date: 2026-10-11. Model: `qwen3.5-flash`; thinking budget: 1024; concurrency: 2.
Six synthetic cases: a clean and an erroneous draft for each RAG, support and report scenario.
JSON Schema, RAG citation and structured business-fact gates enabled. Original case IDs and
dataset hashes, configuration, every verdict, gate report and decision trace are in `run.json`.

```bash
python examples/multi_scenario/evaluate.py --mode qwen --limit-per-scenario 2 \
  --business-gates --citation-gate --thinking-budget 1024 --concurrency 2 \
  --output runs/live-six-gates.json
```

13 real calls; 5 published outputs all passed the independent scenario oracle. One erroneous
report stopped with `no_progress` and did not publish its candidate. This is a functional smoke
test, **not** a statistically meaningful accuracy claim or an ablation against the historical
180-case run. The failed repair remains in the record rather than being discarded.
