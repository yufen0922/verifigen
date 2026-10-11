# Development Diagnostic: Separately Configured Judge

2026-10-11. The same 30 development responses and 30 source groups as the preceding development
trials. Frozen runtime `7266ef6`; generation, repair and ordinary self-refinement use
Qwen3.5-Flash, Judge uses Qwen3.5-Plus, and anonymized automatic review uses Qwen-Plus.
Thinking and literal-quote validation are disabled. Fresh judging, corrective protocol retry,
unaltered baseline/reviewer prompts and common ceilings are retained. Full source evidence is used.

| Arm | Released | Proxy grounded / released | Proxy usable / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 12/30 = 40.00% | 11/30 = 36.67% | 0 | 0 | <0.01 |
| Judge only | 9 | 9/9 = 100.00% | 8/30 = 26.67% | 30 | 76,104 | 8.45 |
| Self-refine | 30 | 25/30 = 83.33% | 25/30 = 83.33% | 60 | 104,078 | 6.22 |
| Quality loop | 29 | 25/29 = 86.21% | 23/30 = 76.67% | 79 | 202,718 | 20.36 |
| Refine then verify | 27 | 24/27 = 88.89% | 24/30 = 80.00% | 71 | 155,466 | 14.14 |

240 runtime calls plus 106 automatic review calls = 346. Runtime usage is known for every
attempt. Review usage totals 231,402 known tokens; two original-output reviews fail and remain
unavailable. No failed review is replaced with a favorable label. The original human-label
agreement of the reviewer is 22/30 (73.33%), including those unavailable originals.

The first Judge-only decision matches original RAGTruth labels on 24/30 (80%): none of the
15 hallucinated originals passes, while six clean originals are rejected. This small, repeatedly
used development cohort does not establish a production false-release rate. It does not label
rewritten answers. Original labels and annotations are withheld from the runtime and reviewer.

## Decision

Changing the Judge alias does not make the loop outperform ordinary self-refinement on usable
output yield or cost in this diagnostic. Better conditional grounding among released answers
must not hide fallback or fulfillment failures. The quality loop has one model-budget fallback;
the hybrid has one no-progress and two repair-budget fallbacks. All remain in the denominator.

No further evaluation cohort is consumed for this unpromising development profile. This is a
negative development result, not a validated recommended default or an isolated model-capacity
ablation: provider aliases, new calls and reviewer variation remain confounders. Human review is
pending. Keep this record alongside the frozen Flash validation rather than selectively publishing
the more flattering precision denominator.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-plus-judge-dev-30
```
