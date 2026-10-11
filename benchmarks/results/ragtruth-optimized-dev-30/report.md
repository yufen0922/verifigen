# Optimization Diagnostic: Feedback and Initial Refinement

2026-10-11. Development-only: 30 responses, 30 source groups, ten cases per task,
half clean and half hallucinated. Runtime snapshot: `a13f9f1`; full evidence and labels
remain separated. Qwen3.5-Flash, thinking enabled (1,024 budget), Qwen-Plus anonymous reviewer.

| Arm | Released | Proxy usable / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 13 | 10 | 30 | 102,963 | 14.63 |
| Self-refine | 30 | 26 | 60 | 165,759 | 26.19 |
| Quality loop | 28 | 23 | 72 | 256,522 | 68.99 |
| Refine then verify | 27 | 24 | 64 | 202,005 | 51.95 |

226 runtime calls plus 99 review calls. Reviewer known usage: 215,904 tokens; three unique
review errors remain unavailable. Original-label agreement: 23/30 (76.67%), including one
unavailable original review. These are automatic proxies, not human-confirmed accuracy.

Two runtime completions are rejected as incomplete. Their known usage is retained rather than
replaced with zero/unknown. A development example also produces a FAIL whose explanation
recognizes the purported issue as supported. This motivates compact final-only feedback and
an experimental literal-quotation contract, not more repair rounds or a higher score threshold.

This trial does not establish superiority over self-refinement. Its unfavorable results stay
published. Model aliases, source correlation and repeated development inspection limit inference.
Later protocol changes do not alter these records.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-optimized-dev-30
```
