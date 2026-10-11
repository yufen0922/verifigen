# Frozen Validation: JSON-Compatible Flash Profiles

2026-10-11. Runtime snapshot `7266ef6`, frozen after development diagnostics. 60 eval responses,
59 source groups, 20 cases per task, half clean and half hallucinated. All 54 source groups from
the original pilot are excluded. These cases still belong to the historically evaluated 420-case
pool, not a completely untouched holdout. No source material is shortened.

Qwen3.5-Flash executes all roles with thinking disabled; Qwen-Plus reviews anonymized outputs.
The baseline self-refine prompt and external review prompt remain unchanged. Fresh Judge calls
hide prior verdicts. Five calls, two edits, 120 seconds and 24,000 observed tokens are common
ceilings, not equal actual expenditure. The optional initial edit consumes a revision and call.

| Arm | Released | Proxy grounded / released | Proxy usable / 60 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct | 60 | 21/60 = 35.00% | 18/60 = 30.00% | 0 | 0 | <0.01 |
| Judge only | 23 | 15/23 = 65.22% | 13/60 = 21.67% | 60 | 147,580 | 4.67 |
| Self-refine | 60 | 50/60 = 83.33% | 50/60 = 83.33% | 120 | 198,724 | 6.04 |
| Quality loop | 56 | 43/56 = 76.79% | 40/60 = 66.67% | 140 | 337,325 | 14.19 |
| Refine then verify | 57 | 49/57 = 85.96% | 46/60 = 76.67% | 132 | 279,006 | 9.85 |

452 runtime calls plus 196 external review calls = 648. External review uses 418,213 known
tokens. Every runtime attempt and external review has known billing; all released outputs have
valid external reviews. Two runtime completions are rejected as incomplete, including their
known usage. No malformed-agent protocol retry is observed in this run. An incomplete response
is not silently accepted or retried outside the common ceilings.

## Interpretation

The hybrid beats the original loop on this paired cohort, but **does not beat ordinary
self-refinement on useful output yield or runtime cost**. Development's one-case hybrid lead did
not generalize. Its conditional grounded release rate is higher, but three fallbacks and task
fulfillment failures matter. Do not select only the favorable denominator or relabel this as
human-confirmed safety. The loop remains weaker than self-refine in this setting.

The first Judge-only classifier matches the original grounding labels on 47/60 (78.33%): three
bad drafts pass, ten clean drafts fail, and no first-call protocol errors occur. These human
labels validate **original** drafts only, never revised candidates.

The automatic reviewer agrees with original labels on 43/60 (71.67%). Consequently all
post-repair results above are model-based proxies; human two-person review is pending. Runtime
aliases and sampling variation remain limitations. The original 60-case pilot used different
sources and thinking settings; its percentages cannot be directly subtracted from these.

## Next Diagnostic

The remaining semantic gap motivates a separately configured Judge, selected on development
cases first. A more capable Judge changes model capacity and cost, not just orchestration.
Any subsequent validation must exclude both pilot source sets, retain every failed attempt and
re-execute its baselines on the same new cases. This report stays frozen regardless of outcome.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-optimized-eval-60
```
