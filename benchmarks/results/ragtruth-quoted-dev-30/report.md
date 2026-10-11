# Development Ablation: Strict Quotations With Thinking

2026-10-11. The same 30 development responses and 30 source groups as the preceding diagnostic.
Runtime snapshot: `498ecf0`. Literal candidate/source quotations are validated locally;
feedback has size bounds. Thinking remains enabled. Other shared ceilings remain five calls,
two revisions, 120 seconds and 24,000 observed tokens. All baselines are re-executed.

| Arm | Released | Proxy usable / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 8 | 7 | 36 | 136,595 | 26.72 |
| Self-refine | 30 | 26 | 60 | 165,990 | 26.03 |
| Quality loop | 16 | 16 | 91 | 346,580 | 70.20 |
| Refine then verify | 23 | 22 | 76 | 264,547 | 72.30 |

263 runtime calls plus 90 anonymous review calls. Reviewer known usage: 192,248 tokens, no
review failures. Original-label agreement: 24/30 (80%). One runtime call has unknown billing;
runtime token totals are lower bounds. Human review remains pending.

The loop's 16/16 proxy-grounded releases must not be presented as universal correctness:
14/30 inputs fall back. Stricter protocols consume attempts and reduce useful coverage.
This configuration is not selected as the default. The test is retained to document a failed
optimization, not discarded because a stricter gate looks impressive on released answers only.

Quote presence prevents nonexistent excerpts, not a wrong interpretation of a real excerpt.
The model may still miss claims. Later fixes distinguish quotation failure categories and
change the retry instructions, but do not retroactively fix this trial.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-quoted-dev-30
```
