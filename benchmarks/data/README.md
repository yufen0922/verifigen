# VerifiBench v0.1 corpus card

| Item | Description |
|---|---|
| Origin | Wholly synthetic; no employer, customer or user records |
| License | MIT, like the repository |
| Languages | Chinese controlled output, English JSON fields |
| Size | dev: 54; test: 60; total: 114 |
| Unit | One source snapshot and candidate response plan |
| Split | Disjoint source-scenario families; shared schema and text templates |
| Gold | Explicit scenario state/amount annotations plus exact expected fields |
| Evidence-invalid examples | Stale/future snapshots, wrong order/request receipt, refund over remaining balance, missing receipt field |
| Intended use | Mechanics, integration tests and initial paired repair experiments |
| Excluded claims | Natural failure prevalence, arbitrary prose quality, production accuracy |

Each valid family has nine candidates: clean; coherent wrong payment; coherent
wrong order status; false commitment; confusing paid and refund amount; extra
unsupported text; entity substitution; combined errors; missing schema field.

`evaluation_time` intentionally anchors fixture replay. Source snapshots expire
under the normal live clock. Use the benchmark loader for historical fixtures;
use `examples/customer_support/make_input.py` for current demo snapshots.

Regenerate with `python scripts/build_fixtures.py`; review the resulting diff.
The builder and gold scorer must remain independent of production verifiers.
Additional models, human audit, richer policy states and diverse paraphrases
are required before using the corpus for broader research claims.
