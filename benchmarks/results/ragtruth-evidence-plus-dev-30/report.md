# Provider-Unavailable Development Attempt

2026-10-11, frozen runtime/runner `5a55d9a`. This attempted the same 30 development cases using
Qwen3.5-Plus for all runtime roles, an 8,192-token runtime completion ceiling, claim assessments,
explicit fulfillment checks and source-first preliminary revision. Qwen-Plus review remains at
4,096 tokens. All ordinary baselines were rerun, under the same five-call, two-edit, 120-second and
24,000-observed-token ceilings. Model/capacity changes are not an orchestration-only ablation.

**This attempt cannot support a semantic performance comparison.** Provider-wide HTTP failures
occurred toward the end of runtime execution and throughout automatic review. All 150 arm records
and 97 attempted reviews are retained, including failures. Only 12 of 97 reviews are available;
85 reviews failed. Counts derived from unavailable reviews must not be interpreted as accuracy.

| Arm | Released | Runtime calls | Known token lower bound | Unknown-usage calls |
| --- | ---: | ---: | ---: | ---: |
| Direct | 30 | 0 | 0 | 0 |
| Judge only | 7 | 30 | 90,547 | 3 |
| Self-refine | 26 | 57 | 96,512 | 4 |
| Quality loop | 23 | 69 | 202,892 | 6 |
| Refine then verify | 25 | 68 | 180,513 | 4 |

224 runtime plus 97 review attempts = 321 calls. Review usage is 29,408 known tokens; unavailable
billing is not treated as zero. Original-output reviews are unavailable for 25/30 cases. Any apparent
differences mix semantic results with provider availability and must not be ranked.

After diagnosis, the runner gained tiny availability probes and an account-error queue guard.
Queued work stops after an account-blocking error; already-started attempts finish and are recorded.
Once service was restored, a new directory reran **all** arms and anonymous reviews, rather than
replacing failed rows in this attempt. This directory remains an auditable negative operational result.
No human post-repair review has been completed.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-evidence-plus-dev-30
```
