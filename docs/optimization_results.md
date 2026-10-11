# Quality Loop Optimization Record

This records engineering changes and real-model experiments, including unsuccessful approaches.
It is not an accuracy guarantee. All RAGTruth inputs retain their original source material.

## Diagnosis and Changes

1. Judge feedback could reject a supported claim or invent an omission outside the task criteria.
   Judge now checks explicit criteria and distinguishes missing evidence from contradictory facts;
   Repair must independently check source support rather than obey every Judge assertion.
2. Structured JSON and thinking-mode responses could disagree. Current configured examples and
   workbench use non-thinking mode; thinking remains opt-in, and the legacy factory preserves its
   compatibility default. The choice is recorded in every new experiment.
3. Invalid agent responses previously lost known billing. Parsing/provider failures retain known
   usage. A corrective protocol retry is allowed only for eligible parse failures with known usage,
   and must reserve the same call, token and deadline budgets. Semantic FAIL/UNKNOWN and incomplete
   provider completions are not retried through this mechanism. Unknown in-flight billing is explicit.
4. Experimental quote fields leaked into the plain Judge schema. Plain mode no longer requests
   them. Literal quote verification is opt-in and rejects invented spans; it cannot prove entailment
   and did not improve development yield, so it is not the default.
5. A hybrid optionally performs one evidence-based self-revision before Judge, then at most one
   targeted repair under a two-edit ceiling. This preliminary call is charged, not a free extra
   attempt. Unchanged self-revision still reaches Judge. No candidate bypasses final release gates.
6. Generation/repair and Judge can use separate model aliases. This is a configuration extension,
   not proof that a larger Judge improves the whole system. Fresh judging can hide prior decisions
   while preserving Repair feedback and audit history.
7. An opt-in claim-level Judge assesses facts and explicit criteria, then code aggregates the
   verdict. Unresolved individual claims are repairable; task-level evidence unavailability still
   stops the loop. Empty claim tables cannot publish, and every assessment is retained. Coverage
   and evidence interpretation remain model judgments. The aggregated score is binary, not a
   calibrated probability or gradual progress measure. Source-first revision and explicit task
   fulfillment are separate recorded switches.
8. Rich assessment responses can exceed completion capacity or violate the JSON protocol. The
   per-call output ceiling is configurable and equal across runtime arms; known failed usage is
   retained. More capacity/model changes alter both capability and cost. Availability probes and
   account-error queue guards stop waste after provider-wide failures, without discarding in-flight
   attempts or selectively replacing unsuccessful rows.

## Experiment Ledger

The four development trials reuse the same 30 responses from 30 source groups. They are diagnostics,
not independent tests. The 60-case validation excludes all 54 source groups from the original pilot,
but comes from the historically evaluated 420-case pool, not a globally untouched holdout.

| Experiment | Cases | Runtime + review calls | Self-refine usable proxy | Loop usable proxy | Hybrid usable proxy |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Initial optimized development](../benchmarks/results/ragtruth-optimized-dev-30/report.md) | 30 dev | 226 + 99 | 26/30 | 23/30 | 24/30 |
| [Literal quotes + thinking](../benchmarks/results/ragtruth-quoted-dev-30/report.md) | 30 dev | 263 + 90 | 26/30 | 16/30 | 22/30 |
| [Non-thinking JSON diagnostic](../benchmarks/results/ragtruth-json-dev-30/report.md) | 30 dev | 227 + 101 | 25/30 | 24/30 | 26/30 |
| [Frozen Flash validation](../benchmarks/results/ragtruth-optimized-eval-60/report.md) | 60 eval | 452 + 196 | 50/60 | 40/60 | 46/60 |
| [Separate Plus Judge](../benchmarks/results/ragtruth-plus-judge-dev-30/report.md) | 30 dev | 240 + 106 | 25/30 | 23/30 | 24/30 |
| [Initial claim assessment](../benchmarks/results/ragtruth-evidence-dev-30/report.md) | 30 dev | 267 + 92 | 26/30 | 15/30 | 18/30 |
| [Source-first with verdict Judge](../benchmarks/results/ragtruth-source-first-dev-30/report.md) | 30 dev | 236 + 103 | 26/30 | 25/30 | 24/30 |
| [Revised claim assessment](../benchmarks/results/ragtruth-evidence-v2-dev-30/report.md) | 30 dev | 251 + 101 | 26/30 | 22/30 | 24/30 |
| [Plus attempt with unavailable review](../benchmarks/results/ragtruth-evidence-plus-dev-30/report.md) | 30 dev | 224 + 97 | Not comparable | Not comparable | Not comparable |
| [Complete Plus development rerun](../benchmarks/results/ragtruth-evidence-plus-restored-dev-30/report.md) | 30 dev | 237 + 107 | 25/30 | 23/30 | 26/30 |

The first five optimization experiments total 2,000 model calls; the four subsequent attempts
add 1,371 calls. The complete Plus rerun adds 344. This excludes separately recorded development debug probes, availability probes
and workbench smoke calls. Frozen code/configuration hashes and individual records are
included in every result directory. Earlier trials are never overwritten after fixing the code.
This is not a sum of unique cases: development inputs repeat, and all five arms share each case.

Usable proxy means external grounding PASS and task-fulfillment PASS divided by **all** cases.
Fallback, unknown and unavailable review do not count as successes. Equal budget ceilings are
not equal actual consumption. Post-repair labels are from anonymous automatic Qwen-Plus review,
not people; its original-label agreement is only 71.67% in the frozen validation. Original
RAGTruth human labels apply to original responses only. Human post-repair review remains pending.

## Supported Conclusions

The hybrid is better than the original loop on this frozen paired validation, but ordinary
self-refinement still has higher useful yield and lower cost. Development's one-case hybrid
lead did not generalize. A more capable Judge did not establish superiority either. Do not
advertise these changes as a new human-confirmed repair success rate or universal improvement.

The framework's supported value is an explicit release policy: shared budgets, structured feedback,
schema/business gates, uncertain-result fallback, cancellation and inspectable decisions. Reliable
deterministic domain gates are a separate source of control; an LLM score is not a calibrated
probability. For broad open-text grounding where only an LLM Judge is available, the observed
quality/cost trade-off remains unfavorable versus this self-refinement baseline.

Next evidence needed: completed dual-human review, independent model-family evaluation, real
matched-token baselines and task-specific cost/coverage requirements. Do not keep trying settings
on the evaluation cohort until a favorable headline appears.

The later complete Plus development rerun shows a one-case hybrid lead (26 versus 25 usable proxy
outputs), but a large token/latency increase. The original loop still trails. This is a hypothesis
for source-disjoint frozen validation, not a validated improvement. The first all-Plus attempt's
85/97 unavailable reviews preclude semantic ranking; both the interrupted and full rerun artifacts
are preserved. The evaluator agrees with original human labels on only 22/30 cases in the rerun.

## Recompute Without API Calls

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-optimized-eval-60
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-plus-judge-dev-30
```

The audit reconstructs cohort selection, labels, anonymous packets, mappings and aggregate metrics;
checks duplicate/missing records, release-candidate equality and call/revision accounting. This
validates the recorded protocol and arithmetic, not the semantic truth of the reviewer judgments.
The workbench displays both successful and failed experiments with their model/mode configuration.
