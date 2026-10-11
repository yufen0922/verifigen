# Development Diagnostic: Source-First Revision with Original Judge

2026-10-11, frozen runtime/runner `cfcf32e`. Same 30 development responses from 30 source groups.
Qwen3.5-Flash runs all runtime roles; Qwen-Plus anonymously reviews outputs. This profile uses
the original verdict Judge, an explicit fulfillment criterion and source-first preliminary revision
only for the hybrid. The baseline self-refinement and review prompts remain unchanged. Full source
material and common five-call, two-edit, 120-second, 24,000-observed-token ceilings are retained.

| Arm | Released | Usable proxy / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 10 | 9 | 30 | 77,033 | 4.47 |
| Self-refine | 30 | 26 | 60 | 104,120 | 5.82 |
| Quality loop | 27 | 25 | 78 | 203,188 | 18.75 |
| Refine then verify | 27 | 24 | 68 | 153,887 | 10.83 |

236 runtime plus 103 review calls = 339. Runtime usage is known for all attempts. Review usage:
223,524 known tokens; one original-output review is unavailable. Original grounding-label agreement
is 23/30 (76.67%) including that unavailable review. Human post-repair review remains pending.

The simpler source-first hybrid does not beat the natural two-edit self-refinement baseline on this
paired development cohort. Its three fallbacks remain in the denominator. The two configurations
in this and the claim-assessed experiments differ in the Judge protocol, not the baseline prompt;
their separately collected calls and reviewer variation prevent a clean causal comparison.
The overall runtime Judge also checks fulfillment and is not a pure hallucination classifier.
Do not use repeated development scores as validated improvements or claim a repair success rate.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-source-first-dev-30
```
