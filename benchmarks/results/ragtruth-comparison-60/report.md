# RAGTruth Paired Pilot: Results and Failure Analysis

Run date: 2026-10-11. **60 eval responses, 54 source groups, four arms and 240 records**.
Each task contributes 20 responses, half clean and half hallucinated. These are a deterministic
subset of the already evaluated 420-case cohort, not a new untouched holdout or production traffic.
All material is retained. Qwen3.5-Flash executes the arms; Qwen-Plus reviews anonymous outputs.
The protocol, source/code hashes and per-case records are published alongside this report.
The recorded runtime is preserved in Git revision `597a032`. Later prompt corrections do not
retroactively change this baseline or its proxy percentages.

## Observed Automatic Proxies

| Arm | Released | Coverage | Proxy grounded / released | Proxy usable / all cases | Runtime calls | Known runtime tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct original | 60/60 | 100.00% | 25/60 = 41.67% | 24/60 = 40.00% | 0 | 0 | <0.01 |
| Judge only | 25/60 | 41.67% | 18/25 = 72.00% | 18/60 = 30.00% | 60 | 196,367 | 16.25 |
| Ordinary self-refine | 60/60 | 100.00% | 53/60 = 88.33% | 53/60 = 88.33% | 120 | 336,479 | 26.30 |
| Full quality loop | 54/60 | 90.00% | 44/54 = 81.48% | 44/60 = 73.33% | 134 | 463,269 | 62.93 |

Every arm shares the same ceiling, not the same actual expenditure. Self-refine uses two plain
revision calls; the loop uses up to two repairs plus re-judgments. Review failures count as
unverified, not positive. Runtime usage is unknown for one Judge-only call and four loop calls,
so those token totals are lower bounds. Latency excludes queueing and external evaluator time.
Total: **314 runtime calls + 148 external review calls = 462 calls**.
External evaluation separately consumes 331,796 known tokens with no unknown-usage calls.

**This pilot does not support a claim that the loop outperforms ordinary self-refinement.**
Self-refinement has higher proxy yield and lower measured cost here. This unfavorable result is
retained rather than replacing the baseline, excluding failures or changing the denominator.
The loop's configurable gates and bounded release behavior are engineering capabilities, not
evidence that its present semantic Judge is better than alternatives.

## Evaluator Reliability

The external evaluator agrees with original RAGTruth labels on **41/60 = 68.33%** of originals.
Four original reviews fail protocol validation; 15 valid judgments disagree with human labels.
Across all 148 unique packets, four reviews are unavailable; identical candidates can share one
unavailable review across arms. Qwen models can share family bias.
Grounding versus implicit-truth definitions and subjective aggregation may also differ.
Automatic disagreements are not definitive proof that the corpus label is wrong.

Therefore, the percentages above are **automatic proxy diagnostics**, not human-confirmed final
correctness or repair success. Real two-person blind review remains pending. Small paired samples,
source correlation, model randomness and different actual costs prevent a significance or
equal-cost superiority claim.

## Concrete Failure Cases

### Missing evidence incorrectly becomes negative evidence: Data2txt 8242

The original incorrectly adds delivery availability. The runtime Judge requests removing the
unsupported delivery assertion. Repair changes it to **"does not provide delivery"**, and the
runtime re-Judge accepts it at 1.0. The source has no delivery field; lack of evidence does not
establish the opposite assertion. The external reviewer flags this new unsupported negative.
This is a plausible repair regression requiring human confirmation, not a reused original span.

Improvement direction: explicitly preserve unknown/missing values, reject unsupported positive
and negative claims alike, and test repairs that invert a claim rather than omit it. The original
source and both candidates are available in `records.jsonl` and the frozen corpus.
The subsequent [targeted recheck](../ragtruth-regression-8242/report.md) documents a prompt
correction and the remaining evaluator disagreement, without changing this baseline.

### Evaluator disagrees with clean originals: Data2txt 8076 and 9587

Both originals have no actionable human hallucination spans and remain unchanged after a runtime
PASS. The external evaluator nevertheless rejects category/service inference, frequency claims,
and review aggregation. These are evaluator/corpus disagreements, **not observed repair damage**.
This is why changing the Judge model is not a substitute for human adjudication.

### Ordinary self-refinement also changes clean originals

Self-refine changes 29/30 clean originals and five of those changed releases receive grounding
FAIL from the external reviewer. The full loop changes six clean originals and two receive FAIL.
These are proxy regression counts, not human-confirmed new-error counts. A revision-only baseline
can achieve good overall proxies while unnecessarily rewriting already good input.

## Reproduce and Audit

```bash
uv run --locked --extra llm python examples/ragtruth/compare.py \
  --per-task 20 --reviewer-model qwen-plus --concurrency 6 --output runs/new-paired-pilot
uv run --locked python scripts/audit_comparison.py
```

The second command recomputes cohort, mappings, budgets and metrics from saved records without
calling a model. Re-running the first command consumes quota and need not reproduce exact text
because provider aliases and serving randomness can change.
See [protocol and human review](../../../docs/comparative_evaluation.md).
