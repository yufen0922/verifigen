# Development Diagnostic: Revised Claim Assessment

2026-10-11, frozen runtime/runner `cfcf32e`. Same 30 development responses and source groups.
Qwen3.5-Flash runs every runtime role with a 4,096-token completion ceiling; Qwen-Plus performs
anonymous automatic review. Unknown individual claims now require targeted repair, while unknown
task-level criteria still force fallback. Empty claim lists cannot publish. The hybrid's preliminary
revision is source-first, and Judge explicitly checks task fulfillment. Baseline and review prompts
are unchanged. All arms retain full sources and the common five-call, two-edit, 120-second,
24,000-observed-token ceilings.

| Arm | Released | Usable proxy / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 9 | 8 | 31 | 100,630 | 12.51 |
| Self-refine | 30 | 26 | 60 | 103,714 | 5.73 |
| Quality loop | 25 | 22 | 88 | 291,432 | 46.54 |
| Refine then verify | 25 | 24 | 72 | 193,382 | 30.22 |

251 runtime plus 101 review calls = 352. All runtime usage is known. Reviews consume 223,089 known
tokens, with one unavailable original-output review. Original grounding-label agreement is 23/30
(76.67%), including that failure. Five loop fallbacks are Judge errors; the hybrid has three Judge
errors, one repeated candidate and one exhausted repair budget. Invalid or incomplete structured
responses remain failures, not replacements or omitted samples.

The revised handling fixes a protocol defect but does not beat ordinary self-refinement on usable
yield. More detailed assessments increase output size, calls and latency. These repeated development
results cannot establish generalization. Claim coverage and evidence interpretation remain model
judgments; consistent aggregation does not prove factual truth. Post-repair human review is pending.
The overall Judge includes fulfillment, so it is not a pure original hallucination classifier.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-evidence-v2-dev-30
```
