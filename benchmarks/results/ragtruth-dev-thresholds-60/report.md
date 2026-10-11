# Development Threshold Diagnostic

Run date: 2026-10-11. **60 development responses, 60 real Qwen3.5-Flash Judge calls**,
20 per task with balanced original labels. No Repair is enabled. No eval IDs are used to select
thresholds. Known consumption is 205,326 tokens; all calls report usage.

First judgments: 29 PASS and 31 FAIL, 49/60 correct (81.67%). Of the PASS responses,
24 are clean and five are hallucinated according to original RAGTruth annotations.

All 29 PASS scores are **1.0**. Thresholds from 0 through 1 therefore release exactly the same
29 originals: 48.33% coverage and 24/29 = 82.76% original-label precision.
Raising the threshold does **not** solve misclassification in this observed run.

The score is not a calibrated probability or a reliable additional safety signal here. The
experiment deliberately selects no new default threshold. Calibrated confidence, rubric-based
dimension scores or a different Judge would require a separate development experiment and frozen
held-out verification; a 60-case diagnostic cannot establish a rare-error safety guarantee.

```bash
uv run --locked --extra llm python examples/ragtruth/evaluate.py \
  --split dev --limit-per-task 20 --max-model-calls 1 --max-repair-rounds 0 \
  --concurrency 6 --output runs/new-dev-thresholds
uv run --locked python scripts/calibrate_threshold.py --results runs/new-dev-thresholds
```

`thresholds.json` is computed from original human labels, raw first verdicts and first-round gate
reports. The calibration tool rejects eval IDs, duplicate records, label drift and incomplete runs.
These are development diagnostics, not a second test-set accuracy claim.
