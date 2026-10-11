# Development Diagnostic: Initial Claim-Assessed Profile

2026-10-11, frozen code `e8b0035`. The same 30 development responses and source groups as earlier
diagnostics. Qwen3.5-Flash performs every runtime role; Qwen-Plus reviews anonymous candidates.
This profile adds explicit fulfillment checking, a source-first preliminary revision for the
hybrid, and per-claim/per-criterion assessments with code-aggregated verdicts. Baseline and external
review prompts are unchanged. Five calls, two edits, 120 seconds and 24,000 observed tokens remain
common ceilings. Inputs are full-length, without original human labels in model requests.

| Arm | Released | Usable proxy / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 6 | 5 | 38 | 133,938 | 35.37 |
| Self-refine | 30 | 26 | 60 | 104,394 | 5.64 |
| Quality loop | 16 | 15 | 90 | 278,499 | 45.74 |
| Refine then verify | 20 | 18 | 79 | 218,765 | 31.54 |

267 runtime plus 92 review calls = 359. Every runtime call has known usage. Review consumption is
197,810 known tokens, without failed reviews. Original grounding-label agreement is 24/30 (80%).
Revised-output labels remain automatic proxies, with human review pending. Judge now checks both
grounding and fulfillment, so its overall verdict is not a pure original hallucination classifier.

## Negative Result and Protocol Diagnosis

The initial claim-assessed profile loses usable yield. Literal fact decomposition by itself does
not ensure accurate checks. This profile also incorrectly equates a single unresolved claim with
globally unavailable task evidence, blocking repairs of optional unsupported details. Empty claim
lists cause parsing failure even when explicit criteria already fail; some completions are
incomplete. The experiment records all these failures rather than replacing them after a fix.

A development probe on 3987 confirms an empty claim list with 2,108 known tokens. Three additional
probes on failed hybrid candidates (4986, 5798, 6269) return valid assessments with 2,799, 3,828 and
3,779 tokens. These four debug calls are not benchmark replacements, and their variability does
not prove those cases are now robust. The follow-up configuration keeps unresolved claim checks
as actionable repair feedback while reserving global UNKNOWN for criteria that cannot be assessed;
empty claims can never publish, but a failed task remains repairable. No unknown claim is accepted
as true. A simpler source-first profile is also tested separately rather than bundling every change.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-evidence-dev-30
```
