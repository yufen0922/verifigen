# RAGTruth Live Evaluation

Run: **2026-10-11**, `qwen3.5-flash`, thinking budget 1024, concurrency 6.
The fixed RAGTruth-600 cohort reserves 180 development responses; this run evaluates all
**420 held-out responses**, 140 per task, from **277 sources**. Each task has 70 clean and
70 hallucinated responses. Original human labels never enter model prompts.

## First-Judge Results

| Task | Cases | Exact accuracy | Hallucination recall | Clean false-alarm rate | Detection precision | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QA | 140 | 80.71% | 94.29% | 32.86% | 74.16% | 83.02% |
| Summary | 140 | 80.00% | 85.71% | 22.86% | 78.95% | 82.19% |
| Data2txt | 140 | 75.00% | 77.14% | 27.14% | 73.97% | 75.52% |
| Overall | 420 | **78.57%** | **85.71%** | **27.62%** | **75.63%** | **80.36%** |

330 correct first judgments; 180 true detections, 150 correctly accepted originals, 58 false
alarms, 28 hallucinated originals incorrectly accepted, and 4 first-call errors. Errors and
abstentions never count as correct detections. The all-case denominators include call failures.

Source-cluster bootstrap (1,000 resamples, seed 600) gives a 95% accuracy interval of
74.53-82.13% and recall interval of 81.22-89.96%. Sources are resampled with all their
responses together rather than treating same-source model answers as independent.

## Execution Costs

958 model calls; **3,319,524 known tokens**. Six records contain unknown usage after a call
failure, so the token total is a lower bound, not exact billing. Per-run average wall time is
30.93 seconds; P50 37.79 seconds; P95 69.05 seconds, excluding the local concurrency queue.
32/420 runs fall back (7.62%). Each run allows two repairs, five calls and 120 seconds.

## What This Does Not Prove

The 388 model-approved final outputs have **not** been independently reviewed. No public-data
repair success rate, final correctness or post-repair wrong-release rate is claimed. Original
span annotations cannot be reused after rewriting: facts and offsets may change, and new
errors may appear. `repair_success_rate` is deliberately `null` in the summary.

Directly publishing all originals gives 50% hallucination by construction. Accepting only
first-Judge `pass` responses would release 178/420 originals, including 28 labeled hallucinated
ones: 42.38% coverage and 84.27% release-label precision. This is a first-verdict diagnostic,
not a runtime-gate simulation or an equal-cost comparison. A full-loop superiority claim also
requires new independent repair labels and an equal-budget self-repair baseline.

The Judge enforces strict source support while human labels exempt `implicit_true` spans;
this mismatch is one possible false-alarm source, not an established explanation for all 58
cases. Model aliases can change upstream, so exact text reproduction is not guaranteed.
Balanced sampling and the selected quality filter limit production generalization.

See `config.json`, `summary.json`, and `records.jsonl` for every selected ID, frozen dataset hash,
budget, original/repaired candidates, verdicts, hard-gate reports, usage and decision trace.
The source corpus, pinned downloader and rebuilding protocol are documented in
[the dataset card](../../data/ragtruth-600/README.md) and
[evaluation protocol](../../../docs/ragtruth_evaluation.md).
