# Development Diagnostic: Complete Plus Rerun

2026-10-11, frozen runtime/runner `34cc0cb`. This is a full rerun of all five arms on the same 30
development responses, not selective replacement of the provider-unavailable attempt. All runtime
roles use Qwen3.5-Plus, non-thinking JSON, an 8,192-token output ceiling, fresh claim-level judging
and explicit fulfillment checks. The hybrid starts with one source-first revision. Qwen-Plus
anonymous review retains its unchanged prompt and 4,096-token ceiling. Every arm receives full
sources and the same five-call, two-edit, 120-second, 24,000-observed-token ceilings. Baseline
self-refinement remains two natural edits. Model/capacity changes are not an orchestration-only
ablation; comparison is paired within this run.

| Arm | Released | Usable proxy / 30 | Grounded / released | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 11/30 | 0 | 0 | <0.01 |
| Judge only | 9 | 7 | 7/9 | 30 | 97,973 | 23.56 |
| Self-refine | 30 | 25 | 25/30 | 60 | 104,787 | 12.17 |
| Quality loop | 29 | 23 | 24/29 | 76 | 239,174 | 52.99 |
| Refine then verify | 28 | 26 | 26/28 | 71 | 191,702 | 50.01 |

237 runtime plus 107 review attempts = 344 calls, with all runtime usage known. Two additional
availability probes consume 223 known tokens and are recorded separately. Review usage is 231,439
known tokens, with two unavailable original-output reviews. Original grounding-label agreement is
22/30 (73.33%), including unavailable reviews. Identical per-case candidates share reviews. All
fallback and unavailable results remain in metric denominators. Human post-repair review is pending.

The hybrid has one more usable proxy output than ordinary self-refinement, but uses 11 more calls,
86,915 more known runtime tokens and substantially greater latency. It has two fallbacks (one
repeated candidate, one exhausted repair budget) and two released grounding failures. The original
loop still has lower usable yield. A one-case development lead is not evidence of superiority or
statistical significance, particularly given evaluator disagreement with original human labels.

This configuration is frozen for a separate 60-case evaluation excluding the union of source groups
from both preceding 60-case pilots. That evaluation must not be tuned until a favorable headline
appears. The repeated development cohort is diagnostic only. The overall Judge includes fulfillment
and must not be treated as a pure classifier against original grounding-only labels.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-evidence-plus-restored-dev-30
```
