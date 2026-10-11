# Known Failure Recheck: Missing Evidence Is Not Negative Evidence

2026-10-11, RAGTruth Data2txt response **8242**. This is a targeted recheck of an already observed
failure, **not** a new holdout, new accuracy measurement or an independent human correctness label.
The baseline runtime and its original percentages remain frozen at Git revision `597a032`.

The previous released draft asserts that the business does not provide delivery or parking.
The source has no delivery attribute; parking includes `street: null`. Neither supports a blanket
negative. The current Judge/Repair instructions now explicitly distinguish missing source
attributes from false values and restrict review to configured criteria.

## Actual Live Outcome

- Qwen3.5-Flash first returns FAIL and identifies unsupported delivery and blanket parking claims.
- Repair removes those claims while retaining explicit false reservations and `WiFi: no` facts.
- Re-Judge returns PASS: **three runtime calls and one repair**.
- The published `run.json` includes input, source/agent hashes, both verdicts, revision and usage.
- One additional Qwen-Plus review returns FAIL, but excludes customer reviews on the erroneous
  premise that the task only permits non-review fields. The actual prompt explicitly says to
  include information mentioned in customer reviews, which are inside `source_info.review_info`.

The targeted unsupported-negative issue is removed in the observed output. The external evaluator
disagreement is preserved, not discarded to improve a result. Human review is still pending;
neither the runtime PASS nor one corrected defect proves that the whole output is correct.
No RAGTruth repair success percentage is updated from this one-case recheck.

```bash
uv run --locked --extra llm python examples/ragtruth/recheck.py \
  --case-id 8242 --output runs/new-8242-recheck.json
```

The command starts from the previously released bad candidate, not a hand-picked new draft.
It consumes real quota and refuses to overwrite previous evidence. The source case was already
examined during debugging, so future effectiveness needs separate frozen evaluation data.
