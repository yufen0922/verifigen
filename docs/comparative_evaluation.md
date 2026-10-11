# Paired Baselines and Post-Output Review

This protocol separates runtime decisions, original human labels and evaluation of rewritten
outputs. It does not turn model approval into ground truth.

## Paired Arms

Every selected RAGTruth response enters all four arms with its full original evidence:

| Arm | Behavior | Additional model calls |
| --- | --- | --- |
| `direct` | Publish the unmodified original | 0 |
| `judge_only` | Run the actual score/Schema release gate without repairs | Normally 1; at most 2 with protocol retry |
| `self_refine` | Two ordinary evidence-based self-revision calls, no separate Judge | At most 2 |
| `quality_loop` | Judge, structured repair feedback, re-Judge and fail-closed output | At most 5 |

The ceiling is five calls, two revisions, 120 seconds and 24,000 observed tokens per arm.
The arms do **not** consume equal actual resources; the weaker baselines deliberately implement
their natural algorithms. Report the cost/coverage/quality trade-off, not an equal-cost superiority
claim. A matched-token or best-of-N baseline remains additional work. Generation is excluded:
the original corpus response is the same starting point for every arm.

```bash
uv run --locked --extra llm python examples/ragtruth/compare.py \
  --per-task 20 --reviewer-model qwen-plus --concurrency 6 \
  --output runs/ragtruth-comparison-60
# The same command plus --resume avoids repeating completed arm/review calls.
```

Sampling is deterministic, eval-only and balanced within task and original label. The default
60-case pilot is not the full 420-case evaluation. The run freezes input hashes, selected IDs,
runtime and runner hashes, prompts, model aliases and ceilings. Resume rejects different code,
models or configuration; aliases still do not identify immutable provider weights.

## Anonymous Automatic Review

### Optimization Protocol

`--optimized` adds `refine_verify`: one ordinary evidence-based revision, Judge, and optionally
one targeted repair followed by a fresh Judge. Both edits share the existing two-revision ceiling;
there is no free preliminary call. Normal execution uses two or four calls; protocol retries must
still fit the common five-call ceiling. It is a hybrid strategy, not the original loop renamed.

Use `--split dev --per-task 10` for a 30-case development diagnostic. Freeze prompts and runtime
before collecting evaluation records. `--exclude-records PATH` excludes **all source groups** in
the referenced experiment, not just response IDs. This keeps the optimization validation cohort
separate from the previously investigated pilot. It is still drawn from the historical 420-case
evaluation cohort, so it must not be described as a completely untouched holdout.

```bash
uv run --locked --extra llm python examples/ragtruth/compare.py \
  --split dev --per-task 10 --optimized --judge-history none \
  --output runs/optimized-dev-30
uv run --locked --extra llm python examples/ragtruth/compare.py \
  --per-task 20 --optimized --judge-history none \
  --exclude-records benchmarks/results/ragtruth-comparison-60/records.jsonl \
  --output runs/optimized-eval-60
```

The original pilot remains frozen and auditable. The second run re-executes **every baseline**
on the same new cases; percentages across different cohorts are not paired improvements.
Fresh judging hides previous verdicts in this profile, while Repair and audit keep feedback.
One budgeted protocol retry is enabled, with known failed-call usage retained. Neither switch
by itself proves improved semantic accuracy. Automatic review instructions are unchanged.

Current calls default to non-thinking JSON mode. `--enable-thinking` restores the historical mode;
`--validate-judge-quotes` adds an experimental literal-quotation contract. Both are saved in the
configuration. `--judge-model MODEL` permits a separately configured Judge; the reviewer must
differ from both runtime model aliases. Changing models changes the system and its cost, not just
the loop. Never attribute a combined profile's result to one switch without an ablation.

`--judge-strategy claims` is an opt-in experimental assessment protocol. Each fact and criterion
has its own result; code aggregates the overall verdict and saves every check in the runtime rounds.
An unresolved claim requires repair; an unavailable task-level criterion still forces fallback.
Every check must pass before release. Empty claim tables cannot produce a passing result. This
enforces internal aggregation consistency, not complete factual coverage or correct entailment.
`--refinement-mode source_first` changes only the hybrid's optional preliminary edit.
`--check-fulfillment` explicitly adds task fulfillment to Judge criteria, without changing the
ordinary baseline or external review prompts. Its overall verdict must not be scored directly
as a pure hallucination classifier using original RAGTruth grounding labels. All switches are
frozen in the experiment configuration; none is promoted to default solely from repeated dev trials.

`--exclude-records` accepts multiple completed record files and excludes the union of their source
groups. For any follow-up validation after the two 60-case pilots, supply both record files rather
than excluding only response IDs. `--max-output-tokens` sets and freezes the same completion ceiling
for all runtime roles, including ordinary self-refinement; evaluator capacity is recorded separately.
Changing the runtime model or completion ceiling changes capacity/cost, not just orchestration.

The frozen all-Plus follow-up uses all three switches and excludes both previous pilot source sets:

```bash
DASHSCOPE_MODEL=qwen3.5-plus uv run --locked --extra llm python examples/ragtruth/compare.py \
  --per-task 20 --optimized --judge-history none --judge-strategy claims \
  --refinement-mode source_first --check-fulfillment --max-output-tokens 8192 \
  --exclude-records benchmarks/results/ragtruth-comparison-60/records.jsonl \
    benchmarks/results/ragtruth-optimized-eval-60/records.jsonl \
  --output runs/plus-eval-60
```

These records are 60 responses from 55 source groups, excluding 113 prior pilot groups. They
remain part of the historically evaluated pool. Use a fresh output directory; do not overwrite
published artifacts. Upstream aliases and nondeterministic provider execution can change text.

Before pending work, the runner sends one tiny JSON availability probe per required model alias.
Probe attempts and known usage are recorded separately in `provider-probes.jsonl`, not charged to
any arm. A failed probe prevents starting the batch. During runtime or review, an account-blocking
provider error stops queued work; already-started requests finish and their records remain. Temporary
rate limits do not trigger this account guard. Errors retain only allowlisted provider metadata, never
raw response bodies or credentials. An interrupted batch does not publish a complete summary.
`--resume` retains failed completed attempts as failures and requires the exact frozen code/config;
it is not a selective retry mechanism. For a fresh comparison after an outage, use a new directory
and rerun every baseline and review, preserving the interrupted directory.

Review packets contain only the original task, evidence and one candidate. They omit the arm,
original hallucination label, span annotations, runtime verdict, score and repair history.
Identical outputs within one case are deduplicated so they receive the same review.
Packet identifiers are not sent to the model. The mapping stays outside reviewer inputs.

The reviewer separately evaluates grounding and fulfillment. This prevents an empty answer or
unjustified refusal from appearing successful just because it contains no false claim. Failures
must have specific claims and source evidence. Invalid reviews and unknown verdicts cannot count
as positive outcomes. Qwen-Plus is a different model from Qwen3.5-Flash, but both are Qwen-family
models and may share biases. This is an **automatic proxy**, not independent human ground truth.

Review the evaluator itself: compare its judgments on unchanged original responses against
RAGTruth labels. Low agreement makes post-repair proxy estimates less trustworthy. It does not
become human-confirmed after changing to a more expensive model.

Different model aliases do not establish evaluator independence or immutable weight identity.
Both models remain in the Qwen family. Prefer explicit provider snapshots for future experiments
when available, and still retain response/configuration hashes and evaluator-agreement checks.
The provider documents snapshot mappings on its [Qwen3.5-Plus model page](https://help.aliyun.com/en/model-studio/qwen3-5-plus).
Existing alias-based experiments are not retroactively relabeled as pinned-snapshot runs.
Source-group exclusion prevents overlap between local trial cohorts, not possible exposure to
public benchmark data during model training. This project has not measured training contamination;
do not claim that the frozen follow-up is unseen by the underlying models or a production guarantee.

## Metric Denominators

- Release coverage: released outputs / all cases, including failures and fallback.
- Proxy grounded release rate: outputs with evaluator grounding PASS / all released outputs;
  unavailable and unknown reviews do not count as PASS.
- Proxy verified yield: grounding PASS **and** fulfillment PASS / all cases.
- Proxy bad-initial rescue: originally hallucinated, changed and usable released outputs /
  all originally hallucinated cases. Original errors that are released unchanged are not repairs.
- Proxy regression: original clean outputs changed and released but evaluator grounding FAIL.
- Tokens: known usage only, with unknown-usage counts. Evaluator consumption is separate from
  production-arm consumption; evaluator calls are not a runtime dependency.
- Latency: per-arm wall time excluding local queue, not end-user production response time.

None of these automatic metrics replaces a human-confirmed repair success rate. Pilot differences
are descriptive; do not infer statistical significance or production prevalence from them.

## Human Review and Adjudication

```bash
uv run --locked python scripts/human_review.py export \
  --records benchmarks/results/ragtruth-qwen3.5-flash/records.jsonl \
  --output runs/human-review-420
```

Give each reviewer `packets.jsonl`, the annotation schema and their unfilled template. Do **not**
give them the mapping, automatic labels, runtime trace or original human spans. Reviewers should
work separately, using anonymous handles rather than personal information. Assess grounding and
task fulfillment and cite evidence for failures. Templates with `review: null` are not labels.

```bash
uv run --locked python scripts/human_review.py reconcile \
  --packets runs/human-review-420/packets.jsonl \
  --annotations runs/reviewer-a.jsonl runs/reviewer-b.jsonl \
  --adjudications runs/adjudicator.jsonl --output runs/human-labels.json
```

Reconciliation requires at least two distinct reviewer handles per packet. A conflicting pair
needs a distinct adjudicator; unresolved disagreement stays unresolved. Source/candidate digests
reject annotations for modified packets. Agreement of UNKNOWN remains UNKNOWN, not correct.
Handles enforce file consistency, not proof of reviewer independence or identity. The project
cannot perform real human review automatically; completed annotations must come from people.
To score completed annotations, also pass `--records` and `--mapping private-mapping.jsonl` to
`reconcile`. Human effect rates remain null until every released output in an arm has resolved,
non-UNKNOWN labels. Output hashes also prevent applying a label to a changed candidate.

## Development Threshold Diagnostic

Use `examples/ragtruth/evaluate.py --split dev --max-model-calls 1 --max-repair-rounds 0`
to collect real first judgments, then `scripts/calibrate_threshold.py --results DIR` to examine
the precision/coverage curve. The tool checks dataset hashes, completeness, development-only IDs
and original labels. It does not tune on eval records or automatically select a threshold.
The published 60-case development run has all PASS scores at 1.0: raising the threshold does not
help in that run. A score threshold is not a substitute for a better classifier.

## Confirmation-Bias Ablation

`QualityLoop(judge_history="none", ...)` hides earlier verdicts from subsequent Judge calls while
Repair retains its actionable feedback and traces retain the audit history. The default remains
`full` for compatibility. Compare both modes on frozen development inputs before deciding whether
to change the default. This is a supported ablation, not a measured accuracy improvement.
